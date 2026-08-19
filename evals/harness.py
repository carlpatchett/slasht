"""A/B effectiveness harness for clone-catcher.

Runs the same "find the duplicated logic" task twice against the planted
fixture repo:

  * baseline   — generic tools only (list_files / read_file / search_files)
  * augmented  — the same tools PLUS clone-catcher over real stdio MCP

and compares token usage, LLM turns, tool calls, wall time, and answer
quality (pairwise precision/recall/F1 against evals/ground_truth.json).

Models: a real Anthropic model when ``--model <name>`` and
ANTHROPIC_API_KEY are available; otherwise a deterministic scripted model
that exercises the full plumbing (report is explicitly marked ``scripted``
— scripted numbers are NOT an effectiveness claim).
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE = Path(__file__).resolve().parent / "messy_codebase"
GROUND_TRUTH = Path(__file__).resolve().parent / "ground_truth.json"

SYSTEM_PROMPT = (
    "You are a meticulous code analyst. Use the provided tools to inspect the "
    "repository; do not guess file contents."
)
TASK_PROMPT = (
    "Find every group of files in this repository that contain duplicated "
    "logic — code that was copy-pasted and then renamed or lightly tweaked "
    "(identical structure with different names/strings counts as duplicated). "
    "Ignore coincidental similarity of trivial one-liners. For each group give "
    "the repo-relative file paths and a one-line description of the shared "
    "logic. Respond with ONLY a JSON object of the form "
    '{"groups": [{"files": ["...", "..."], "description": "..."}]}'
)

MAX_READ_CHARS = 12_000
SERVER_TOOL_SPANS = (
    "find_structural_clones",
    "find_duplicate_groups",
    "get_diff_summary",
    "reindex_workspace",
    "clone_catcher.index.build",
    "clone_catcher.index.query",
    "clone_catcher.index.groups",
)

# ----------------------------------------------------------------------
# Tools


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: object  # async callable: (args: dict) -> str

    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


def make_baseline_tools(root: Path) -> list[Tool]:
    def safe(path_text: str) -> Path:
        candidate = (root / path_text).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"path escapes repository: {path_text}")
        return candidate

    def list_files(_args: dict) -> str:
        entries = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )
        return "\n".join(entries)

    def read_file(args: dict) -> str:
        target = safe(args["path"])
        if not target.is_file():
            raise ValueError(f"no such file: {args['path']}")
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + "\n... [truncated]"
        return text

    def search_files(args: dict) -> str:
        pattern = re.compile(args["pattern"])
        matches: list[str] = []
        files = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts and path.stat().st_size < 200_000
        )
        for path in files[:400]:
            try:
                for lineno, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    if pattern.search(line):
                        matches.append(
                            f"{path.relative_to(root).as_posix()}:{lineno}:{line.strip()[:160]}"
                        )
                        if len(matches) >= 100:
                            return "\n".join(matches)
            except OSError:
                continue
        return "\n".join(matches) if matches else "no matches"

    return [
        Tool(
            name="list_files",
            description="List every file in the repository (repo-relative paths).",
            schema={"type": "object", "properties": {}, "required": []},
            fn=list_files,
        ),
        Tool(
            name="read_file",
            description="Read one file's full text.",
            schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            fn=read_file,
        ),
        Tool(
            name="search_files",
            description="Search a regex across all files; returns file:line:match lines (max 100).",
            schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "description": "optional subpath to narrow scope"},
                },
                "required": ["pattern"],
            },
            fn=search_files,
        ),
    ]


async def make_mcp_tools(trace_path: Path) -> list[Tool]:
    from mcp import Client, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "clone_catcher"],
        env={
            "CLONE_CATCHER_ROOT": str(FIXTURE),
            "CLONE_CATCHER_TRACE_PATH": str(trace_path),
        },
    )
    client = Client(stdio_client(params))

    async def _adapt(tool_def, call_client):
        async def execute(args: dict) -> str:
            result = await call_client.call_tool(tool_def.name, args)
            if result.structured_content is not None:
                return json.dumps(result.structured_content)
            parts = [
                block.text for block in result.content if isinstance(block, TextContent)
            ]
            return "\n".join(parts) if parts else "(empty result)"

        return Tool(
            name=tool_def.name,
            description=tool_def.description or tool_def.name,
            schema=tool_def.input_schema,
            fn=execute,
        )

    class _Connected:
        def __init__(self):
            self._client = None
            self.tools: list[Tool] = []

        async def __aenter__(self):
            self._client = await client.__aenter__()
            listed = await self._client.list_tools()
            self.tools = [await _adapt(t, self._client) for t in listed.tools]
            return self

        async def __aexit__(self, *exc):
            return await client.__aexit__(*exc)

    return _Connected()


# ----------------------------------------------------------------------
# Models


@dataclass
class Reply:
    text: str
    tool_calls: list[dict]
    usage: dict


class ScriptedModel:
    """Deterministic model replaying a canned step list (plumbing verification)."""

    mode = "scripted"

    def __init__(self, name: str, steps: list[dict]):
        self.name = name
        self._steps = list(steps)
        self._turn = 0

    async def chat(self, system: str, history: list[dict], tools: list[dict]) -> Reply:
        self._turn += 1
        step = self._steps.pop(0) if self._steps else {"final": "{}"}
        usage = {
            "input_tokens": 1200 + 40 * self._turn,
            "output_tokens": 80 + 20 * self._turn,
        }
        if "final" in step:
            return Reply(text=step["final"], tool_calls=[], usage=usage)
        return Reply(
            text="",
            tool_calls=[
                {
                    "id": f"call_{self._turn}",
                    "name": step["tool"],
                    "args": step.get("args", {}),
                }
            ],
            usage=usage,
        )


class AnthropicModel:
    """Live Anthropic tool-use loop (requires ANTHROPIC_API_KEY)."""

    mode = "live"

    def __init__(self, model: str):
        import anthropic

        self.name = model
        self._client = anthropic.AsyncAnthropic()

    async def chat(self, system: str, history: list[dict], tools: list[dict]) -> Reply:
        response = await self._client.messages.create(
            model=self.name,
            system=system,
            max_tokens=4096,
            messages=history,
            tools=tools,
        )
        tool_calls = [
            {"id": block.id, "name": block.name, "args": dict(block.input)}
            for block in response.content
            if block.type == "tool_use"
        ]
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return Reply(text=text, tool_calls=tool_calls, usage=usage)


# ----------------------------------------------------------------------
# Agent loop


@dataclass
class ArmRun:
    arm: str
    final_text: str = ""
    parsed_ok: bool = False
    groups: list[dict] = field(default_factory=list)
    turns: int = 0
    tool_calls: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    wall_seconds: float = 0.0
    stopped_reason: str = "final"


async def run_agent(model, tools: list[Tool], max_turns: int) -> ArmRun:
    run = ArmRun(arm="")  # filled by caller
    dispatch = {tool.name: tool for tool in tools}
    history: list[dict] = [{"role": "user", "content": TASK_PROMPT}]
    calls: Counter = Counter()
    started = time.perf_counter()

    for turn in range(1, max_turns + 1):
        run.turns = turn
        reply = await model.chat(
            SYSTEM_PROMPT, history, [tool.definition() for tool in tools]
        )
        run.input_tokens += reply.usage.get("input_tokens", 0)
        run.output_tokens += reply.usage.get("output_tokens", 0)
        if not reply.tool_calls:
            run.final_text = reply.text
            run.stopped_reason = "final"
            break
        history.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["name"],
                        "input": call["args"],
                    }
                    for call in reply.tool_calls
                ],
            }
        )
        results = []
        for call in reply.tool_calls:
            calls[call["name"]] += 1
            tool = dispatch.get(call["name"])
            try:
                if tool is None:
                    raise ValueError(f"unknown tool: {call['name']}")
                output = await tool.fn(call["args"])
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": str(output),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - tool errors feed the model
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": f"error: {exc}",
                        "is_error": True,
                    }
                )
        history.append({"role": "user", "content": results})
    else:
        run.stopped_reason = "max_turns"

    run.wall_seconds = round(time.perf_counter() - started, 3)
    run.tool_calls = dict(sorted(calls.items()))
    return run


# ----------------------------------------------------------------------
# Scoring


def _normalize_path(text: str, root: Path) -> str | None:
    cleaned = text.strip().strip("`").lstrip("./")
    prefix = f"{root.name}/"
    if cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix) :]
    return cleaned


def predicted_pairs(groups: list[dict], root: Path = FIXTURE) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    for group in groups:
        files = [
            normalized
            for entry in group.get("files", [])
            if (normalized := _normalize_path(entry, root))
            and (root / normalized).is_file()
        ]
        for a, b in itertools.combinations(sorted(set(files)), 2):
            pairs.add(frozenset((a, b)))
    return pairs


def parse_final_answer(text: str) -> tuple[list[dict], bool]:
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    blobs = candidates or ([text[text.find("{") : text.rfind("}") + 1]] if "{" in text else [])
    for blob in blobs:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("groups"), list):
            return parsed["groups"], True
    return [], False


def score(groups: list[dict], truth: set[frozenset[str]], root: Path = FIXTURE) -> dict:
    predicted = predicted_pairs(groups, root)
    hits = len(predicted & truth)
    precision = hits / len(predicted) if predicted else 0.0
    recall = hits / len(truth) if truth else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "groups_found": len(groups),
        "predicted_pairs": len(predicted),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def truth_pairs(ground_truth: dict) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    for group in ground_truth["groups"]:
        for a, b in itertools.combinations(sorted(group["files"]), 2):
            pairs.add(frozenset((a, b)))
    return pairs


def server_tool_stats(trace_path: Path) -> dict | None:
    if not trace_path.exists():
        return None
    by_name: dict[str, list[float]] = {}
    for line in trace_path.read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("name") in SERVER_TOOL_SPANS:
            by_name.setdefault(record["name"], []).append(record["duration_ms"])
    return {
        name: {
            "calls": len(durations),
            "mean_ms": round(sum(durations) / len(durations), 3),
            "max_ms": round(max(durations), 3),
        }
        for name, durations in sorted(by_name.items())
    }


# ----------------------------------------------------------------------
# Scripted scenarios (plumbing verification only)

BASELINE_STEPS = [
    {"tool": "list_files", "args": {}},
    {"tool": "read_file", "args": {"path": "legacy_app/payments/retry.py"}},
    {"tool": "read_file", "args": {"path": "legacy_app/notifications/backoff.py"}},
    {"tool": "search_files", "args": {"pattern": "def .*"}},
    {
        "final": json.dumps(
            {
                "groups": [
                    {
                        "files": [
                            "legacy_app/payments/retry.py",
                            "legacy_app/notifications/backoff.py",
                        ],
                        "description": "retry loop with sleep-based backoff",
                    },
                    {
                        "files": [
                            "legacy_app/core/visitor_base.py",
                            "legacy_app/search/tree_walker.py",
                        ],
                        "description": "tree walking logic",
                    },
                ]
            }
        )
    },
]

AUGMENTED_STEPS = [
    {"tool": "list_files", "args": {}},
    {"tool": "find_structural_clones", "args": {"file_path": "legacy_app/payments/retry.py"}},
    {
        "tool": "find_structural_clones",
        "args": {"file_path": "legacy_app/reports/csv_export.py", "threshold": 0.7},
    },
    {
        "tool": "get_diff_summary",
        "args": {
            "file_a": "legacy_app/payments/retry.py",
            "file_b": "legacy_app/notifications/backoff.py",
        },
    },
    {
        "final": json.dumps(
            {
                "groups": [
                    {
                        "files": [
                            "legacy_app/payments/retry.py",
                            "legacy_app/notifications/backoff.py",
                        ],
                        "description": "retry loop with sleep-based backoff",
                    },
                    {
                        "files": [
                            "legacy_app/reports/csv_export.py",
                            "legacy_app/billing/invoice_writer.py",
                            "legacy_app/analytics/usage_report.py",
                        ],
                        "description": "delimiter-joined table rendering",
                    },
                    {
                        "files": [
                            "legacy_app/utils/lru_cache.py",
                            "legacy_app/services/cache_manager.py",
                        ],
                        "description": "bounded OrderedDict cache",
                    },
                    {"files": ["tools/backup.go", "tools/cleanup.go"], "description": "go filter-and-tag slice loop"},
                    {"files": ["tools/Mailer.cs", "tools/Notifier.cs"], "description": "csharp string builder renderer"},
                ]
            }
        )
    },
]


# ----------------------------------------------------------------------
# Orchestration


async def run_eval(
    model: str = "scripted",
    out_dir: Path | None = None,
    max_turns: int = 24,
) -> dict:
    out_dir = out_dir or (REPO_ROOT / "evals" / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ground_truth = json.loads(GROUND_TRUTH.read_text())
    truth = truth_pairs(ground_truth)

    if model == "scripted":
        baseline_model = ScriptedModel("scripted-baseline", BASELINE_STEPS)
        augmented_model = ScriptedModel("scripted-augmented", AUGMENTED_STEPS)
        mode = "scripted"
    else:
        baseline_model = AnthropicModel(model)
        augmented_model = AnthropicModel(model)
        mode = "live"

    baseline_tools = make_baseline_tools(FIXTURE)
    baseline_run = await run_agent(baseline_model, baseline_tools, max_turns)
    baseline_run.arm = "baseline"
    baseline_run.groups, baseline_run.parsed_ok = parse_final_answer(
        baseline_run.final_text
    )

    trace_path = out_dir / f"trace_augmented_{int(time.time())}.jsonl"
    connected = await make_mcp_tools(trace_path)
    async with connected:
        augmented_tools = baseline_tools + connected.tools
        augmented_run = await run_agent(augmented_model, augmented_tools, max_turns)
    augmented_run.arm = "augmented"
    augmented_run.groups, augmented_run.parsed_ok = parse_final_answer(
        augmented_run.final_text
    )

    def arm_payload(run: ArmRun) -> dict:
        return {
            "model": getattr(baseline_model if run.arm == "baseline" else augmented_model, "name", model),
            "turns": run.turns,
            "tool_calls": run.tool_calls,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "wall_seconds": run.wall_seconds,
            "parsed_ok": run.parsed_ok,
            **score(run.groups, truth),
        }

    report = {
        "mode": mode,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture": str(FIXTURE),
        "truth_pairs": len(truth),
        "arms": {
            "baseline": arm_payload(baseline_run),
            "augmented": arm_payload(augmented_run),
        },
        "server_tools": server_tool_stats(trace_path),
        "notes": (
            ["mode=scripted: token/turn numbers are synthetic; report verifies "
             "harness plumbing only, not clone-catcher effectiveness."]
            if mode == "scripted"
            else []
        ),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"report_{stamp}.json"
    md_path = out_dir / f"report_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(render_markdown(report))
    report["_report_paths"] = [str(json_path), str(md_path)]
    return report


def render_markdown(report: dict) -> str:
    lines = [
        "# clone-catcher A/B eval",
        "",
        f"- generated: {report['generated_at']}",
        f"- mode: **{report['mode']}** (model: {report['model']})",
        f"- fixture: `{report['fixture']}` ({report['truth_pairs']} truth pairs)",
        "",
        "| arm | input tok | output tok | turns | tool calls | wall s | groups | pairs | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm_name, arm in report["arms"].items():
        total_calls = sum(arm["tool_calls"].values())
        lines.append(
            f"| {arm_name} | {arm['input_tokens']} | {arm['output_tokens']} "
            f"| {arm['turns']} | {total_calls} | {arm['wall_seconds']} "
            f"| {arm['groups_found']} | {arm['predicted_pairs']} "
            f"| {arm['precision']:.2f} | {arm['recall']:.2f} | {arm['f1']:.2f} |"
        )
    if report.get("server_tools"):
        lines += [
            "",
            "## Server-side tool latency (OpenTelemetry spans)",
            "",
            "| span | calls | mean ms | max ms |",
            "|---|---:|---:|---:|",
        ]
        for name, stats in report["server_tools"].items():
            lines.append(
                f"| `{name}` | {stats['calls']} | {stats['mean_ms']} | {stats['max_ms']} |"
            )
    for note in report.get("notes", []):
        lines += ["", f"> {note}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default="scripted",
        help="'scripted' (default) or an Anthropic model name for a live run",
    )
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = asyncio.run(run_eval(args.model, args.out, args.max_turns))
    print(render_markdown(report))
    for path in report.get("_report_paths", []):
        print(f"report written: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
