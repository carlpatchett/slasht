"""Environment-driven configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".jj",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    "target",
)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings for the index and server."""

    root: Path
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDES
    shingle_k: int = 4
    num_perm: int = 128
    trace_path: Path = Path("clone_catcher_trace.jsonl")
    max_query_k: int = 50
    max_file_bytes: int = 2_000_000


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from ``env`` (defaults to the process environment)."""
    env = os.environ if env is None else env
    root = Path(env.get("CLONE_CATCHER_ROOT", Path.cwd())).resolve()

    raw_excludes = env.get("CLONE_CATCHER_EXCLUDE", "")
    excludes = tuple(s.strip() for s in raw_excludes.split(",") if s.strip())
    if not excludes:
        excludes = DEFAULT_EXCLUDES

    trace_raw = env.get("CLONE_CATCHER_TRACE_PATH", "")
    trace_path = Path(trace_raw).resolve() if trace_raw else Path("clone_catcher_trace.jsonl")

    return Settings(
        root=root,
        exclude_dirs=excludes,
        shingle_k=int(env.get("CLONE_CATCHER_SHINGLE_K", "4")),
        num_perm=int(env.get("CLONE_CATCHER_NUM_PERM", "128")),
        trace_path=trace_path,
        max_query_k=int(env.get("CLONE_CATCHER_MAX_K", "50")),
    )
