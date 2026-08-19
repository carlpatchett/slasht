"""omp-runner plumbing proven with a fake omp binary — no model quota spent.

The fake omp emits canned NDJSON events (usage, tool calls, final answer) and,
for the augmented arm, writes a synthetic OpenTelemetry span as the real
server would. This validates fixture preparation, user-config swapping, event
parsing, scoring, trace ingestion, and report generation end to end.
"""

import json
import os
import stat
from pathlib import Path

from evals.omp_eval import isolated_user_mcp, run_eval

ALL_GROUPS = {
    "groups": [
        {
            "files": [
                "legacy_app/payments/retry.py",
                "legacy_app/notifications/backoff.py",
            ],
            "description": "retry with backoff",
        },
        {
            "files": [
                "legacy_app/reports/csv_export.py",
                "legacy_app/billing/invoice_writer.py",
                "legacy_app/analytics/usage_report.py",
            ],
            "description": "table rendering",
        },
        {
            "files": [
                "legacy_app/utils/lru_cache.py",
                "legacy_app/services/cache_manager.py",
            ],
            "description": "bounded cache",
        },
        {"files": ["tools/backup.go", "tools/cleanup.go"], "description": "go loop"},
        {"files": ["tools/Mailer.cs", "tools/Notifier.cs"], "description": "cs builder"},
    ]
}

PARTIAL_GROUPS = {
    "groups": [
        {
            "files": [
                "legacy_app/payments/retry.py",
                "legacy_app/notifications/backoff.py",
            ],
            "description": "retry with backoff",
        },
        {
            "files": [
                "legacy_app/core/visitor_base.py",
                "legacy_app/search/tree_walker.py",
            ],
            "description": "tree walking (false positive)",
        },
    ]
}

FAKE_OMP = """#!{python}
import json, os, sys
cwd = sys.argv[sys.argv.index("--cwd") + 1]
augmented = "augmented_repo" in cwd
events = []
def emit(event):
    events.append(json.dumps(event))
emit({{"type": "agent_start"}})
emit({{"type": "message_end", "message": {{"role": "assistant",
    "content": [{{"type": "text", "text": ""}}],
    "usage": {{"input": 25000, "output": 120, "cost": {{"total": 0.02}}}}}}}})
tool = "mcp__clone_catcher_find_structural_clones" if augmented else "read"
emit({{"type": "tool_execution_start", "tool": tool}})
final = {final_all} if augmented else {final_partial}
text = "```json\\n" + json.dumps(final) + "\\n```"
emit({{"type": "message_end", "message": {{"role": "assistant",
    "content": [{{"type": "text", "text": text}}],
    "usage": {{"input": 30000, "output": 400, "cost": {{"total": 0.03}}}}}}}})
emit({{"type": "agent_end", "messages": []}})
print("\\n".join(events))
if augmented:
    cfg = json.load(open(os.path.join(cwd, ".omp", "mcp.json")))
    trace = cfg["mcpServers"]["clone-catcher"]["env"]["CLONE_CATCHER_TRACE_PATH"]
    with open(trace, "a") as handle:
        handle.write(json.dumps({{"name": "find_structural_clones", "duration_ms": 12.5}}) + "\\n")
"""


def make_fake_omp(directory: Path) -> str:
    script = FAKE_OMP.format(
        python=os.sys.executable,
        final_all=json.dumps(ALL_GROUPS),
        final_partial=json.dumps(PARTIAL_GROUPS),
    )
    path = directory / "omp"
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


async def test_fake_omp_run_produces_scored_report(tmp_path):
    omp_bin = make_fake_omp(tmp_path)
    report = await _run(omp_bin, tmp_path)

    assert report["mode"] == "live"
    assert report["truth_pairs"] == 7
    baseline, augmented = report["arms"]["baseline"], report["arms"]["augmented"]

    # Usage summed across per-call events.
    assert baseline["input_tokens"] == 55_000
    assert baseline["output_tokens"] == 520
    assert baseline["llm_calls"] == 2
    assert baseline["cost_usd"] == 0.05

    # Baseline: one true group + one false positive; augmented: all planted.
    assert baseline["parsed_ok"] is True
    assert augmented["parsed_ok"] is True
    assert augmented["f1"] > baseline["f1"]
    assert augmented["precision"] == 1.0
    assert augmented["recall"] == 1.0
    assert baseline["precision"] == 0.5

    # Tool accounting distinguishes the arms.
    assert baseline["tool_calls"] == {"read": 1}
    assert augmented["tool_calls"] == {"mcp__clone_catcher_find_structural_clones": 1}

    # The synthetic server span landed and was aggregated.
    assert report["server_tools"]["find_structural_clones"]["calls"] == 1

    for path in report["_report_paths"]:
        assert Path(path).is_file()
    markdown = Path(report["_report_paths"][1]).read_text()
    assert "omp runner" in markdown


async def _run(omp_bin, tmp_path):
    return run_eval(
        model="fake/model:test",
        max_time="1m",
        out_dir=tmp_path / "results",
        omp_bin=omp_bin,
        swap_user_config=False,
    )


def test_isolated_user_mcp_swaps_and_restores(tmp_path):
    home = tmp_path / "home"
    (home / ".omp" / "agent").mkdir(parents=True)
    config = home / ".omp" / "agent" / "mcp.json"
    config.write_text("{}")

    with isolated_user_mcp(home) as moved:
        assert moved is True
        assert not config.exists()
    assert config.read_text() == "{}"

    # No user config: swap is a no-op that does not create anything.
    empty_home = tmp_path / "empty-home"
    (empty_home / ".omp" / "agent").mkdir(parents=True)
    with isolated_user_mcp(empty_home) as moved:
        assert moved is False
