"""End-to-end: the real server as a stdio subprocess, launched like a host would."""

import sys
from mcp.client.stdio import stdio_client
from mcp import Client, StdioServerParameters

from sources import NOISE_FIB, PY_A, PY_CLONE


async def test_stdio_roundtrip(tmp_path):
    (tmp_path / "orders.py").write_text(PY_A)
    (tmp_path / "fulfilment.py").write_text(PY_CLONE)
    (tmp_path / "numbers.py").write_text(NOISE_FIB)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "clone_catcher"],
        env={
            "CLONE_CATCHER_ROOT": str(tmp_path),
            "CLONE_CATCHER_TRACE_PATH": str(tmp_path / "trace.jsonl"),
        },
    )
    async with Client(stdio_client(params)) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert "find_structural_clones" in names

        result = await client.call_tool(
            "find_structural_clones", {"file_path": "orders.py"}
        )
        assert result.is_error is False
        payload = result.structured_content
        assert [m["path"] for m in payload["matches"]] == ["fulfilment.py"]

        diff = await client.call_tool(
            "get_diff_summary",
            {"file_a": "orders.py", "file_b": "fulfilment.py"},
        )
        assert diff.structured_content["identical_structure"] is True
