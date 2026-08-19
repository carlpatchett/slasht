"""Server contract over the in-memory MCP client (SDK testing pattern).

Each test reloads the server module with a fresh CLONE_CATCHER_ROOT so the
lazy index builds against an isolated workspace.
"""

import importlib
import json

import pytest
from mcp import Client
from sources import NOISE_FIB, PY_A, PY_CLONE


@pytest.fixture
def server(tmp_path, monkeypatch):
    (tmp_path / "orders.py").write_text(PY_A)
    (tmp_path / "fulfilment.py").write_text(PY_CLONE)
    (tmp_path / "numbers.py").write_text(NOISE_FIB)
    monkeypatch.setenv("CLONE_CATCHER_ROOT", str(tmp_path))
    monkeypatch.setenv("CLONE_CATCHER_TRACE_PATH", str(tmp_path / "trace.jsonl"))
    from slasht import server as srv

    return importlib.reload(srv)


class TestToolSurface:
    async def test_advertises_expected_tools(self, server):
        async with Client(server.mcp) as client:
            result = await client.list_tools()
        names = {tool.name for tool in result.tools}
        assert {
            "find_structural_clones",
            "find_duplicate_groups",
            "get_diff_summary",
            "reindex_workspace",
        } <= names


class TestFindStructuralClones:
    async def test_finds_renamed_twin(self, server):
        async with Client(server.mcp) as client:
            result = await client.call_tool(
                "find_structural_clones", {"file_path": "orders.py"}
            )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["file"] == "orders.py"
        assert [m["path"] for m in payload["matches"]] == ["fulfilment.py"]
        assert payload["matches"][0]["similarity"] >= 0.9

    async def test_missing_file_is_tool_error(self, server):
        async with Client(server.mcp) as client:
            result = await client.call_tool(
                "find_structural_clones", {"file_path": "ghost.py"}
            )
        assert result.is_error is True


class TestFindDuplicateGroups:
    async def test_returns_group_over_structured_content(self, server):
        async with Client(server.mcp) as client:
            result = await client.call_tool("find_duplicate_groups", {})
        assert result.is_error is False
        payload = result.structured_content
        assert payload["group_count"] == 1
        group = payload["groups"][0]
        assert set(group["files"]) == {"orders.py", "fulfilment.py"}
        assert group["mean_similarity"] >= 0.9


class TestGetDiffSummary:
    async def test_identical_structure_reported(self, server):
        async with Client(server.mcp) as client:
            result = await client.call_tool(
                "get_diff_summary", {"file_a": "orders.py", "file_b": "fulfilment.py"}
            )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["identical_structure"] is True
        assert payload["structural_similarity"] == 1.0


class TestReindex:
    async def test_reindex_reports_indexed_files(self, server):
        async with Client(server.mcp) as client:
            result = await client.call_tool("reindex_workspace", {})
        assert result.is_error is False
        payload = result.structured_content
        assert set(payload["files"]) == {"orders.py", "fulfilment.py", "numbers.py"}
        assert payload["count"] == 3


class TestTelemetry:
    async def test_tool_calls_write_jsonl_spans(self, server, tmp_path):
        async with Client(server.mcp) as client:
            await client.call_tool("find_structural_clones", {"file_path": "orders.py"})
        trace_path = tmp_path / "trace.jsonl"
        assert trace_path.exists(), "telemetry must record spans on disk"
        records = [json.loads(line) for line in trace_path.read_text().splitlines()]
        assert records, "trace file must contain at least one span"
        names = {record["name"] for record in records}
        assert "find_structural_clones" in names
        for record in records:
            assert "duration_ms" in record
            assert record["duration_ms"] >= 0
