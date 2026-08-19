"""AST-level diff summary: which skeleton regions actually differ."""

from __future__ import annotations

import difflib
from collections import Counter
from pathlib import Path

from .parsing import detect_language, parse_source
from .signature import shingles
from .structural import structural_tokens, token_types

MAX_REGIONS = 25
MAX_NODE_TYPES_PER_REGION = 8


class _Side:
    def __init__(self, label: str, path: Path):
        if not path.is_file():
            raise ValueError(f"File not found: {label} ({path})")
        language = detect_language(path)
        if language is None:
            raise ValueError(f"Unsupported file type: {label} ({path})")
        self.path = path
        self.language = language
        self.source = path.read_text(encoding="utf-8", errors="replace")
        self.lines = self.source.splitlines()
        tree = parse_source(language, self.source.encode("utf-8"))
        self.tokens = structural_tokens(tree.root_node)
        self.types = token_types(self.tokens)


def _line_range(tokens) -> list[int] | None:
    if not tokens:
        return None
    starts = [token.start_line for token in tokens]
    ends = [token.end_line for token in tokens]
    return [min(starts), max(ends)]


def _region_node_types(a_types: list[str], b_types: list[str]) -> list[str]:
    counts = Counter(a_types + b_types)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [f"{name} x{count}" for name, count in ranked[:MAX_NODE_TYPES_PER_REGION]]


def diff_summary(file_a: str, file_b: str, shingle_k: int = 4) -> dict:
    """Summarize structural differences between two files.

    Identical skeletons (renames/literals only) report
    ``identical_structure: true`` with exact similarity 1.0. Otherwise the
    differing token regions are reported with node types and line spans.
    """
    side_a = _Side("file_a", Path(file_a))
    side_b = _Side("file_b", Path(file_b))

    matcher = difflib.SequenceMatcher(None, side_a.types, side_b.types, autojunk=False)
    regions = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        regions.append(
            {
                "kind": tag,
                "a_lines": _line_range(side_a.tokens[i1:i2]),
                "b_lines": _line_range(side_b.tokens[j1:j2]),
                "node_types": _region_node_types(
                    side_a.types[i1:i2], side_b.types[j1:j2]
                ),
            }
        )

    set_a = shingles(side_a.types, shingle_k)
    set_b = shingles(side_b.types, shingle_k)
    if set_a or set_b:
        similarity = len(set_a & set_b) / len(set_a | set_b)
    else:
        similarity = 1.0

    changed_text_lines = sum(
        1
        for line in difflib.unified_diff(side_a.lines, side_b.lines, n=0)
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )

    return {
        "file_a": str(side_a.path),
        "file_b": str(side_b.path),
        "languages": {"file_a": side_a.language, "file_b": side_b.language},
        "identical_structure": not regions,
        "structural_similarity": round(similarity, 4),
        "text_lines_changed": changed_text_lines,
        "regions": regions[:MAX_REGIONS],
        "regions_truncated": max(0, len(regions) - MAX_REGIONS),
        "summary": (
            "Structure is identical: differences are naming, literals, or "
            "formatting only."
            if not regions
            else f"{len(regions)} structural region(s) differ."
        ),
    }
