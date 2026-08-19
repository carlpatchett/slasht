"""MinHash signatures over structural shingles + LSH Forest clone index.

Follows the datasketch 2.0 documented pattern for MinHashLSHForest
(https://ekzhu.com/datasketch/lshforest.html): add keys, call ``index()``,
query with a generous top-k, then re-rank candidates by MinHash Jaccard and
keep those >= threshold. With the default ``l=8`` the retrieval curve returns
neighbours above ~0.8 similarity near-certainly, which covers threshold 0.9
queries comfortably.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from datasketch import MinHash, MinHashLSHForest

from .config import Settings
from .parsing import detect_language, ensure_languages, parse_source
from .structural import structural_tokens, token_types
from .telemetry import NullTelemetry

SEPARATOR = "\x1f"


def shingles(types: list[str], k: int) -> set[bytes]:
    """k-gram shingles of a token-type stream; short streams become one shingle."""
    if not types:
        return set()
    if len(types) < k:
        return {SEPARATOR.join(types).encode("utf-8")}
    return {
        SEPARATOR.join(types[i : i + k]).encode("utf-8")
        for i in range(len(types) - k + 1)
    }


def minhash_for(types: list[str], k: int, num_perm: int) -> MinHash:
    """Deterministic MinHash signature (default seed) of a token stream."""
    signature = MinHash(num_perm=num_perm)
    for shingle in shingles(types, k):
        signature.update(shingle)
    return signature


@dataclass(frozen=True)
class FileMeta:
    language: str
    line_count: int
    token_count: int


@dataclass(frozen=True)
class _Record:
    key: str
    minhash: MinHash
    meta: FileMeta


class CloneIndex:
    """LSH-indexed collection of structural signatures for a workspace."""

    def __init__(self, settings: Settings, telemetry=None):
        self._settings = settings
        self._telemetry = telemetry if telemetry is not None else NullTelemetry()
        self._records: dict[str, _Record] = {}
        self._forest: MinHashLSHForest | None = None

    # ------------------------------------------------------------------
    # Building

    def build(self) -> dict:
        """(Re)build the index from disk. Returns stats about what was indexed."""
        ensure_languages()
        started = time.perf_counter()
        self._records.clear()
        skipped: list[str] = []
        with self._telemetry.span(
            "clone_catcher.index.build", root=str(self._settings.root)
        ):
            for path in self._iter_files():
                record = self._record_for(path)
                if record is None:
                    skipped.append(self._key(path))
                    continue
                self._records[record.key] = record
            self._forest = MinHashLSHForest(
                num_perm=self._settings.num_perm, l=8
            )
            for key, record in self._records.items():
                self._forest.add(key, record.minhash)
            self._forest.index()
        duration_ms = (time.perf_counter() - started) * 1000.0
        languages = Counter(r.meta.language for r in self._records.values())
        return {
            "files": sorted(self._records),
            "skipped": sorted(skipped),
            "languages": dict(sorted(languages.items())),
            "duration_ms": round(duration_ms, 3),
        }

    def _iter_files(self) -> list[Path]:
        exclude = set(self._settings.exclude_dirs)
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(
            self._settings.root, topdown=True
        ):
            dirnames[:] = sorted(d for d in dirnames if d not in exclude)
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if detect_language(path) is None:
                    continue
                try:
                    if path.stat().st_size > self._settings.max_file_bytes:
                        continue
                except OSError:
                    continue
                found.append(path)
        return found

    def _key(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self._settings.root).as_posix()
        except ValueError:
            return str(path)

    def _record_for(self, path: Path) -> _Record | None:
        language = detect_language(path)
        if language is None:
            return None
        source = path.read_bytes()
        tree = parse_source(language, source)
        tokens = structural_tokens(tree.root_node)
        types = token_types(tokens)
        if not types:
            return None
        meta = FileMeta(
            language=language,
            line_count=source.count(b"\n") + 1,
            token_count=len(types),
        )
        return _Record(
            key=self._key(path),
            minhash=minhash_for(types, self._settings.shingle_k, self._settings.num_perm),
            meta=meta,
        )

    def _ensure_built(self) -> None:
        if self._forest is None:
            self.build()

    # ------------------------------------------------------------------
    # Queries

    def find_clones(self, file_path: str | Path, threshold: float = 0.9) -> list[dict]:
        """Files whose structural similarity to ``file_path`` is >= threshold.

        Results are ordered by descending similarity and never include the
        query file itself.
        """
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold}")
        self._ensure_built()
        path = self._locate(file_path)
        if path is None:
            raise ValueError(f"File not found or unsupported: {file_path}")
        key = self._key(path)
        record = self._records[key] if key in self._records else self._record_for(path)
        if record is None:
            return []  # empty skeleton: nothing can be structurally similar

        with self._telemetry.span(
            "clone_catcher.index.query", file=key, threshold=threshold
        ) as span:
            candidates = self._query_forest(record.minhash)
            matches = []
            for candidate in candidates:
                if candidate == key:
                    continue
                indexed = self._records[candidate]
                similarity = record.minhash.jaccard(indexed.minhash)
                if similarity >= threshold:
                    matches.append(
                        {
                            "path": candidate,
                            "similarity": round(similarity, 4),
                            "language": indexed.meta.language,
                            "lines": indexed.meta.line_count,
                            "skeleton_tokens": indexed.meta.token_count,
                        }
                    )
            matches.sort(key=lambda m: m["similarity"], reverse=True)
            if span is not None:
                span.set_attribute("candidates", len(candidates))
                span.set_attribute("matches", len(matches))
        return matches

    def duplicate_groups(
        self,
        threshold: float = 0.9,
        max_groups: int = 25,
        max_files_per_group: int = 20,
    ) -> dict:
        """All groups of mutually similar files (connected components).

        One call replaces per-file queries: builds the similarity graph at
        ``threshold`` and returns its connected components, largest group
        first, with per-group similarity stats.
        """
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold}")
        self._ensure_built()
        keys = sorted(self._records)
        parent = {key: key for key in keys}

        def find(key: str) -> str:
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        edges: dict[frozenset[str], float] = {}
        with self._telemetry.span(
            "clone_catcher.index.groups", threshold=threshold, files=len(keys)
        ) as span:
            for key in keys:
                signature = self._records[key].minhash
                for candidate in self._query_forest(signature):
                    if candidate <= key:
                        continue
                    similarity = signature.jaccard(self._records[candidate].minhash)
                    if similarity >= threshold:
                        edges[frozenset((key, candidate))] = similarity
                        root_a, root_b = find(key), find(candidate)
                        if root_a != root_b:
                            parent[root_b] = root_a

            components: dict[str, list[str]] = {}
            for key in keys:
                components.setdefault(find(key), []).append(key)

            groups = []
            for members in components.values():
                if len(members) < 2:
                    continue
                member_set = frozenset(members)
                sims = [sim for pair, sim in edges.items() if pair <= member_set]
                languages = Counter(
                    self._records[member].meta.language for member in members
                )
                groups.append(
                    {
                        "files": sorted(members)[:max_files_per_group],
                        "files_truncated": max(
                            0, len(members) - max_files_per_group
                        ),
                        "size": len(members),
                        "min_similarity": round(min(sims), 4),
                        "mean_similarity": round(sum(sims) / len(sims), 4),
                        "language": languages.most_common(1)[0][0],
                    }
                )
            groups.sort(
                key=lambda group: (
                    -group["size"],
                    -group["mean_similarity"],
                    group["files"],
                )
            )
            if span is not None:
                span.set_attribute("groups", len(groups))
            return {
                "groups": groups[:max_groups],
                "group_count": len(groups),
                "truncated": len(groups) > max_groups,
                "threshold": threshold,
                "indexed_files": len(keys),
            }

    def _query_forest(self, minhash: MinHash) -> list[str]:
        if not self._records:
            return []
        k = min(self._settings.max_query_k, len(self._records))
        return self._forest.query(minhash, k)

    def similarity(self, file_a: str | Path, file_b: str | Path) -> float:
        """MinHash Jaccard estimate between two files (indexed or on disk)."""
        return self._signature(file_a).jaccard(self._signature(file_b))

    def _signature(self, file_path: str | Path) -> MinHash:
        self._ensure_built()
        path = self._locate(file_path)
        if path is None:
            raise ValueError(f"File not found or unsupported: {file_path}")
        key = self._key(path)
        record = self._records[key] if key in self._records else self._record_for(path)
        if record is None:
            raise ValueError(f"File has no parseable structure: {file_path}")
        return record.minhash

    def _locate(self, file_path: str | Path) -> Path | None:
        """Resolve a query path against the root; None when not a file."""
        path = Path(file_path)
        if not path.is_absolute():
            under_root = self._settings.root / path
            path = under_root if under_root.exists() else path
        return path if path.is_file() else None
