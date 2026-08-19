"""Offline verification of the A/B harness with the scripted model.

Proves the plumbing end to end: both arms run, the augmented arm drives the
real MCP server over stdio, telemetry spans land on disk, scoring matches the
planted ground truth, and reports are written. Scripted token numbers are
synthetic — this test never claims effectiveness, only that the measurement
machinery works.
"""

from pathlib import Path

from evals.harness import run_eval


async def test_scripted_ab_run_produces_report(tmp_path):
    report = await run_eval(model="scripted", out_dir=tmp_path)

    assert report["mode"] == "scripted"
    assert report["truth_pairs"] == 7

    baseline = report["arms"]["baseline"]
    augmented = report["arms"]["augmented"]

    # Scripted scenario: baseline finds one true group plus a false positive;
    # augmented recovers all planted groups.
    assert baseline["parsed_ok"] is True
    assert augmented["parsed_ok"] is True
    assert augmented["f1"] > baseline["f1"]
    assert augmented["precision"] == 1.0
    assert augmented["recall"] == 1.0
    assert baseline["recall"] < 1.0

    # The augmented arm really used the MCP tools and left spans behind.
    assert augmented["tool_calls"]["find_structural_clones"] == 2
    assert augmented["tool_calls"]["get_diff_summary"] == 1
    server = report["server_tools"]
    assert server is not None
    assert server["find_structural_clones"]["calls"] == 2
    assert server["find_structural_clones"]["mean_ms"] >= 0

    # Reports exist on disk.
    for path in report["_report_paths"]:
        assert Path(path).is_file()
    markdown = Path(report["_report_paths"][1]).read_text()
    assert "slasht A/B eval" in markdown
    assert "mode: **scripted**" in markdown
