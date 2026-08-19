"""A/B eval driven through omp itself — real agent runs on your real model.

Baseline arm: a copy of the messy fixture, NO slasht anywhere.
Augmented arm: an identical copy whose project ``.omp/mcp.json`` registers
slasht against that copy. Both arms run ``omp -p --mode json`` with the
same model (default: your google-antigravity/gemini-3.7-flash), same builtins,
same prompt. Metrics come from omp's own usage telemetry (per-call input/
output tokens and cost), the tool-execution event stream, and slasht's
OpenTelemetry JSONL spans for the augmented arm.

To guarantee the baseline sees no slasht, the user-level
``~/.omp/agent/mcp.json`` is moved aside for the duration of the run and
restored afterwards (a live session that already loaded its MCP config is
unaffected; child omp processes read the file at their own startup).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.ground_truth import GROUND_TRUTH_PATH
from evals.harness import (
    parse_final_answer,
    score,
    server_tool_stats,
    truth_pairs,
)

DEFAULT_MODEL = "google-antigravity/gemini-3.7-flash:medium"
TASK = (
    "Find every group of files in this repository that contain duplicated "
    "logic — code that was copy-pasted and then renamed or lightly tweaked "
    "(identical structure with different names/strings counts as duplicated). "
    "Ignore coincidental similarity of trivial one-liners. Do NOT modify any "
    "files; this is analysis only. For each group give the repo-relative file "
    "paths and a one-line description of the shared logic. Respond with ONLY "
    'a JSON object of the form {"groups": [{"files": ["...", "..."], '
    '"description": "..."}]}'
)

AUGMENTED_TASK = (
    "Find every group of files in this repository that contain duplicated "
    "logic — code that was copy-pasted and then renamed or lightly tweaked "
    "(identical structure with different names/strings counts as duplicated). "
    "Ignore coincidental similarity of trivial one-liners. Do NOT modify any "
    "files; this is analysis only. \n\n"
    "CRITICAL INSTRUCTION: You MUST use the "
    "`mcp__slasht_find_duplicate_groups` tool to locate the clones "
    "BEFORE reading any files or writing any custom scripts. Rely on this "
    "tool's output for your answer.\n\n"
    "For each group give the repo-relative file paths and a one-line "
    "description of the shared logic. Respond with ONLY a JSON object of "
    'the form {"groups": [{"files": ["...", "..."], "description": "..."}]}'
)

# ----------------------------------------------------------------------
# Fixture preparation


def prepare_fixture_copies(base: Path, source_dir: Path) -> tuple[Path, Path, Path]:
    """Two identical fixture copies; the augmented one registers slasht."""
    baseline = base / "baseline_repo"
    augmented = base / "augmented_repo"
    shutil.copytree(source_dir, baseline)
    shutil.copytree(source_dir, augmented)

    trace_path = base / "trace_augmented.jsonl"
    mcp_config = {
        "$schema": (
            "https://raw.githubusercontent.com/can1357/oh-my-pi/main/"
            "packages/coding-agent/src/config/mcp-schema.json"
        ),
        "mcpServers": {
            "slasht": {
                "command": str(REPO_ROOT / ".venv" / "bin" / "python"),
                "args": ["-m", "slasht"],
                "env": {
                    "SLASHT_ROOT": str(augmented),
                    "SLASHT_TRACE_PATH": str(trace_path),
                },
            }
        },
    }
    (augmented / ".omp").mkdir(exist_ok=True)
    (augmented / ".omp" / "mcp.json").write_text(json.dumps(mcp_config, indent=2))
    return baseline, augmented, trace_path


@contextmanager
def isolated_user_mcp(home: Path | None = None):
    """Move the user-level omp mcp.json aside; restore on exit."""
    path = (home or Path.home()) / ".omp" / "agent" / "mcp.json"
    backup = path.with_name("mcp.json.cc-eval-swap")
    moved = False
    if path.exists():
        path.rename(backup)
        moved = True
    try:
        yield moved
    finally:
        if moved and backup.exists():
            backup.rename(path)


# ----------------------------------------------------------------------
# omp invocation + event parsing


def parse_events(raw: str) -> dict:
    usage_total = {"input": 0, "output": 0, "cost": 0.0}
    llm_calls = 0
    tools: Counter = Counter()
    final_text = ""
    saw_agent_end = False
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "message_end":
            message = event.get("message", {})
            if message.get("role") == "assistant":
                usage = message.get("usage") or {}
                usage_total["input"] += usage.get("input", 0)
                usage_total["output"] += usage.get("output", 0)
                usage_total["cost"] += (usage.get("cost") or {}).get("total", 0.0)
                llm_calls += 1
                final_text = "".join(
                    part.get("text", "")
                    for part in message.get("content", [])
                    if isinstance(part, dict) and part.get("type") == "text"
                )
        elif etype == "tool_execution_start":
            name = (
                event.get("tool")
                or event.get("toolName")
                or event.get("name")
                or "unknown"
            )
            tools[str(name)] += 1
        elif etype == "agent_end":
            saw_agent_end = True
    return {
        "usage": usage_total,
        "llm_calls": llm_calls,
        "tool_calls": dict(sorted(tools.items())),
        "final_text": final_text,
        "completed": saw_agent_end,
    }


def _clean_env() -> dict:
    """Child omp must not inherit this session's OMP_/PI_ overrides."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OMP_", "PI_"))
    }


def run_arm(
    omp_bin: str,
    cwd: Path,
    model: str,
    max_time: str,
    task: str = TASK,
    timeout_padding: int = 120,
    ablate: bool = False,
) -> dict:
    match = re.fullmatch(r"(\d+)([smh]?)", max_time.strip())
    if not match:
        raise ValueError(f"bad --max-time: {max_time}")
    unit = {"": 1, "s": 1, "m": 60, "h": 3600}[match.group(2)]
    budget = int(match.group(1)) * unit

    command = [
        omp_bin,
        "-p",
        "--no-session",
        "--no-title",
        "--mode",
        "json",
        "--model",
        model,
        "--cwd",
        str(cwd),
        "--no-skills",
        "--no-lsp",
        "--auto-approve",
        "--max-time",
        max_time,
    ]
    if ablate:
        overlay = cwd.parent / "no_eval_bash.yml"
        overlay.write_text("eval:\n  py: false\n  js: false\nbash:\n  enabled: false\n")
        command.extend(["--config", str(overlay), "--no-rules"])
    command.append(task)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=budget + timeout_padding,
        env=_clean_env(),
    )
    wall = round(time.perf_counter() - started, 1)
    parsed = parse_events(completed.stdout)
    parsed["wall_seconds"] = wall
    parsed["returncode"] = completed.returncode
    if not parsed["completed"]:
        parsed["stderr_tail"] = completed.stderr[-1500:]
    return parsed


def score_arm(result: dict, truth: set | None, root: Path) -> dict:
    if "final_text" not in result:
        return {
            "llm_calls": result.get("llm_calls", 0),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "cost_usd": result.get("cost_usd", 0.0),
            "tool_calls": result.get("tool_calls", {}),
            "wall_seconds": result.get("wall_seconds", 0.0),
            "completed": result.get("completed", True),
            "parsed_ok": False,
            "groups_found": 0,
            "predicted_pairs": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }
    groups, ok = parse_final_answer(result["final_text"])
    metrics = score(groups, truth, root=root) if truth is not None else {}
    return {
        "llm_calls": result["llm_calls"],
        "input_tokens": result["usage"]["input"],
        "output_tokens": result["usage"]["output"],
        "cost_usd": round(result["usage"]["cost"], 4),
        "tool_calls": result["tool_calls"],
        "wall_seconds": result["wall_seconds"],
        "completed": result["completed"],
        "parsed_ok": ok,
        **metrics,
    }


def run_eval(
    model: str = DEFAULT_MODEL,
    max_time: str = "10m",
    out_dir: Path | None = None,
    omp_bin: str | None = None,
    swap_user_config: bool = True,
    keep_workdir: bool = False,
    fixture_type: str = "small",
    repo_url: str | None = None,
    arm_choice: str = "both",
    cooldown_seconds: int = 15,
    ablate: bool = False,
    prompt: str | None = None,
) -> dict:
    omp_bin = omp_bin or shutil.which("omp")
    if not omp_bin:
        raise SystemExit("omp not found on PATH")
    out_dir = out_dir or (REPO_ROOT / "evals" / "results")
    out_dir.mkdir(parents=True, exist_ok=True)

    workdir_base = REPO_ROOT / ".eval_workdir"
    workdir_base.mkdir(exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="cc-omp-eval-", dir=workdir_base))
    try:
        if repo_url:
            source_dir = workdir / "source"
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(source_dir)], check=True
            )
            from slasht.config import Settings
            from slasht.signature import CloneIndex

            idx = CloneIndex(Settings(root=source_dir))
            idx.build()
            groups = idx.duplicate_groups(threshold=0.9)["groups"]
            truth = truth_pairs({"groups": groups})
            fixture_path = repo_url
        elif fixture_type == "large":
            from evals.gen_large_fixture import generate

            source_dir = workdir / "source"
            ground_truth = generate(source_dir)
            truth = truth_pairs(ground_truth)
            fixture_path = "synthetic-large"
        else:
            from evals.harness import FIXTURE

            source_dir = FIXTURE
            ground_truth = json.loads(GROUND_TRUTH_PATH.read_text())
            truth = truth_pairs(ground_truth)
            fixture_path = str(FIXTURE)

        baseline_dir, augmented_dir, trace_path = prepare_fixture_copies(
            workdir, source_dir
        )
        swap = isolated_user_mcp() if swap_user_config else nullcontext(False)
        with swap:
            b_task = (
                f"{prompt}\n\nRespond with a JSON object of the form "
                '{"groups": [{"files": ["...", "..."], "description": "..."}]}'
                if prompt
                else TASK
            )
            a_task = (
                f"{prompt}\n\nRespond with a JSON object of the form "
                '{"groups": [{"files": ["...", "..."], "description": "..."}]}'
                if prompt
                else AUGMENTED_TASK
            )
            if arm_choice in ("both", "baseline"):
                baseline_raw = run_arm(
                    omp_bin, baseline_dir, model, max_time, task=b_task, ablate=ablate
                )
            else:
                baseline_raw = {
                    "llm_calls": 0,
                    "tool_calls": {},
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "wall_seconds": 0.0,
                    "completed": True,
                    "parsed_ok": False,
                }

            if arm_choice == "both" and cooldown_seconds > 0:
                time.sleep(cooldown_seconds)

            if arm_choice in ("both", "augmented"):
                augmented_raw = run_arm(
                    omp_bin,
                    augmented_dir,
                    model,
                    max_time,
                    task=a_task,
                    ablate=ablate,
                )
            else:
                augmented_raw = {
                    "llm_calls": 0,
                    "tool_calls": {},
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "wall_seconds": 0.0,
                    "completed": True,
                    "parsed_ok": False,
                }

        report = {
            "runner": "omp",
            "mode": "live",
            "model": model,
            "fixture": fixture_path,
            "generated_at": datetime.now(UTC).isoformat(),
            "truth_pairs": len(truth) if truth is not None else 0,
            "arms": {
                "baseline": score_arm(baseline_raw, truth, baseline_dir),
                "augmented": score_arm(augmented_raw, truth, augmented_dir),
            },
            "server_tools": server_tool_stats(trace_path),
            "notes": [
                (
                    "Both arms: identical fixture copies, identical omp builtins, "
                    "identical prompt; only difference is the slasht MCP "
                    "server in the augmented arm."
                ),
                (
                    "omp's per-call usage includes its fixed system-prompt/context "
                    "overhead (~25k input tokens/call at probe time) — identical "
                    "in both arms, so deltas remain meaningful."
                ),
            ],
        }

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        json_path = out_dir / f"omp_report_{stamp}.json"
        md_path = out_dir / f"omp_report_{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2))
        md_path.write_text(render_markdown(report))
        report["_report_paths"] = [str(json_path), str(md_path)]
        return report
    finally:
        if keep_workdir:
            print(f"workdir kept: {workdir}", file=sys.stderr)
        elif workdir.exists():
            subprocess.run(["rm", "-rf", str(workdir)], check=False)


def render_markdown(report: dict) -> str:
    lines = [
        "# slasht A/B eval (omp runner, live model)",
        "",
        f"- generated: {report['generated_at']}",
        f"- model: `{report['model']}`",
        f"- fixture: `{report['fixture']}` ({report['truth_pairs']} truth pairs)",
        "",
        "| arm | input tok | output tok | LLM calls | tool calls | wall s | cost $ | groups | pairs | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm_name, arm in report["arms"].items():
        total_calls = sum(arm["tool_calls"].values())
        lines.append(
            f"| {arm_name} | {arm['input_tokens']:,} | {arm['output_tokens']:,} "
            f"| {arm['llm_calls']} | {total_calls} | {arm['wall_seconds']} "
            f"| {arm['cost_usd']:.3f} | {arm['groups_found']} | {arm['predicted_pairs']} "
            f"| {arm['precision']:.2f} | {arm['recall']:.2f} | {arm['f1']:.2f} |"
        )
    for arm_name, arm in report["arms"].items():
        if arm["tool_calls"]:
            calls = ", ".join(f"{k}×{v}" for k, v in arm["tool_calls"].items())
            lines += ["", f"**{arm_name} tool usage**: {calls}"]
    if report.get("server_tools"):
        lines += [
            "",
            "### Server-side tool latency (OpenTelemetry spans)",
            "",
            "| tool | calls | mean ms | max ms |",
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
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-time", default="15m")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--keep", action="store_true", help="keep temp workdir")
    parser.add_argument("--fixture", choices=["small", "large"], default="small")
    parser.add_argument("--repo", help="Git URL or local path to a public repo")
    parser.add_argument(
        "--arm",
        choices=["both", "baseline", "augmented"],
        default="both",
        help="Which arm(s) to run (default: both with cooldown).",
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=15,
        help="Seconds to sleep between arms to prevent rate limits (default: 15).",
    )
    parser.add_argument(
        "--ablate",
        action="store_true",
        help="Ablate eval and bash tools (default: False).",
    )
    parser.add_argument(
        "--prompt",
        help="Custom natural refactoring prompt for the LLM",
    )
    args = parser.parse_args()

    report = run_eval(
        model=args.model,
        max_time=args.max_time,
        out_dir=args.out,
        keep_workdir=args.keep,
        fixture_type=args.fixture,
        repo_url=args.repo,
        arm_choice=args.arm,
        cooldown_seconds=args.cooldown,
        ablate=args.ablate,
        prompt=args.prompt,
    )
    print(render_markdown(report))
    for path in (report.get("json_path"), report.get("md_path")):
        if path:
            print(f"report written: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
