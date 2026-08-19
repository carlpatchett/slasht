"""slasht MCP server.

Tools:
  find_structural_clones(file_path, threshold=0.9)
  get_diff_summary(file_a, file_b)
  reindex_workspace()

SDK: MCP Python SDK v2 (https://py.sdk.modelcontextprotocol.io/) — type hints
become the tool schemas; dicts come back to callers as structured_content.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from mcp.server import MCPServer

from .config import load_settings
from .difftool import diff_summary as _diff_summary
from .parsing import ensure_languages
from .signature import CloneIndex
from .telemetry import setup as setup_telemetry


class CloneMatch(TypedDict):
    path: str
    similarity: float
    language: str
    lines: int
    skeleton_tokens: int


class FindClonesResult(TypedDict):
    file: str
    threshold: float
    match_count: int
    matches: list[CloneMatch]
    hint: str


class DiffRegion(TypedDict):
    kind: str
    a_lines: list[int] | None
    b_lines: list[int] | None
    node_types: list[str]


class DiffSummaryResult(TypedDict):
    file_a: str
    file_b: str
    languages: dict[str, str]
    identical_structure: bool
    structural_similarity: float
    text_lines_changed: int
    regions: list[DiffRegion]
    regions_truncated: int
    summary: str


class ReindexResult(TypedDict):
    count: int
    files: list[str]
    skipped: list[str]
    languages: dict[str, int]
    duration_ms: float


class DuplicateGroup(TypedDict, total=False):
    files: list[str]
    files_truncated: int
    size: int
    min_similarity: float
    mean_similarity: float
    language: str
    sample_file: str
    sample_snippet: str
    structural_summary: str


class DuplicateGroupsResult(TypedDict):
    groups: list[DuplicateGroup]
    group_count: int
    truncated: bool
    threshold: float
    indexed_files: int


settings = load_settings()
TEL = setup_telemetry(settings)
_index = CloneIndex(settings, telemetry=TEL)

mcp = MCPServer(
    "slasht",
    instructions=(
        "Structural clone detection for Python, Go, and C#. START by calling "
        "find_duplicate_groups once: it lists every group of files sharing "
        "the same code skeleton (renames and literal changes are ignored), "
        "largest group first — use it to decide which files are worth "
        "reading at all. find_structural_clones does the same lookup for a "
        "single file; get_diff_summary tells you whether two files differ "
        "only in naming/literals before you read both. Call "
        "reindex_workspace after files change."
    ),
)


def _resolve(file_path: str) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        path = settings.root / path
    if not path.is_file():
        raise ValueError(f"File not found: {file_path}")
    return path


@mcp.tool()
def find_structural_clones(file_path: str, threshold: float = 0.9) -> FindClonesResult:
    """Find files structurally similar to file_path.

    Structural similarity ignores identifier names, literals, comments, and
    formatting: two files whose logic has the same shape (e.g. copy-pasted
    then renamed) score 1.0. Returns matches with similarity >= threshold,
    most similar first, with paths relative to the indexed root.
    """
    resolved = _resolve(file_path)
    with TEL.span(
        "find_structural_clones", file_path=str(resolved), threshold=threshold
    ):
        matches = _index.find_clones(resolved, threshold=threshold)
    return {
        "file": _display(resolved),
        "threshold": threshold,
        "match_count": len(matches),
        "matches": matches,
        "hint": (
            "Matches share the query's code skeleton; only naming/literals "
            "differ. Use get_diff_summary to confirm before skipping a read."
        )
        if matches
        else "No structural clones at this threshold.",
    }


@mcp.tool()
def find_duplicate_groups(threshold: float = 0.9) -> DuplicateGroupsResult:
    """⚡ INSTANT REPO-WIDE CLONE MAP. CALL THIS FIRST BEFORE READING ANY FILES.

    Replaces 50+ sequential file reads by instantly clustering duplicate
    Python, Go, and C# code across the entire workspace in ~100ms.
    Returns connected groups of files sharing the same code skeleton (renames
    and literal changes are ignored), largest group first, with similarity
    stats, sample code snippets, and structural summaries.
    """
    with TEL.span("find_duplicate_groups", threshold=threshold):
        return _index.duplicate_groups(threshold=threshold)


@mcp.tool()
def get_diff_summary(file_a: str, file_b: str) -> DiffSummaryResult:
    """Summarize AST-level differences between two files.

    Reports whether the two files have identical structure (differences are
    naming/literals/formatting only) and, when they do not, the differing
    node types with line ranges in each file.
    """
    resolved_a = _resolve(file_a)
    resolved_b = _resolve(file_b)
    with TEL.span("get_diff_summary", file_a=str(resolved_a), file_b=str(resolved_b)):
        return _diff_summary(
            str(resolved_a), str(resolved_b), shingle_k=settings.shingle_k
        )


@mcp.tool()
def reindex_workspace() -> ReindexResult:
    """Rebuild the structural clone index from disk.

    Call after creating, editing, or deleting files so clone queries reflect
    the current workspace.
    """
    with TEL.span("reindex_workspace"):
        stats = _index.build()
    return {
        "count": len(stats["files"]),
        "files": stats["files"],
        "skipped": stats["skipped"],
        "languages": stats["languages"],
        "duration_ms": stats["duration_ms"],
    }


def _display(path: Path) -> str:
    """Show a path relative to the indexed root when possible."""
    try:
        return str(path.relative_to(settings.root))
    except ValueError:
        return str(path)


def main() -> None:
    # Grammars prefetch up front (first run downloads once, then cached);
    # the index builds lazily on the first query so startup stays instant
    # even in large repositories.
    ensure_languages()
    mcp.run()


if __name__ == "__main__":
    main()
