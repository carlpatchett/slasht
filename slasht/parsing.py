"""Tree-sitter parsing for the supported languages.

Uses tree-sitter-language-pack (371 grammars; parsers download on first use
and are cached). Language keys verified empirically: python, go, csharp.
Docs: https://docs.tree-sitter-language-pack.xberg.io
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import tree_sitter_language_pack as _pack
from tree_sitter import Parser, Tree

# File suffix -> tree-sitter language key.
LANGUAGES: dict[str, str] = {".py": "python", ".go": "go", ".cs": "csharp"}


@cache
def parser_for(language: str) -> Parser:
    """Return a cached parser for a supported language key."""
    return _pack.get_parser(language)


def detect_language(path: str | Path) -> str | None:
    """Map a file path to its language key, or ``None`` if unsupported."""
    return LANGUAGES.get(Path(path).suffix.lower())


def parse_source(language: str, data: bytes) -> Tree:
    """Parse source bytes into a tree-sitter syntax tree."""
    return parser_for(language).parse(data)


def ensure_languages() -> None:
    """Prefetch all bundled grammars so later parses never hit the network.

    Best-effort: ``get_parser`` downloads on demand anyway; this just front-loads
    the cost to startup.
    """
    try:
        _pack.prefetch(sorted(set(LANGUAGES.values())))
    except Exception:  # noqa: BLE001, S110 - pragma: no cover - prefetch is an optimisation
        pass
