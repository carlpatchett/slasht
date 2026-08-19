# Implementation Plan: clone-catcher

## Overview

An MCP server that detects **structural code clones** (same skeleton, different names/literals)
across Python, Go, and C#, so coding agents skip re-reading boilerplate. Pipeline:
tree-sitter AST → structural token stream (node types only) → k-shingles → MinHash (128 perms)
→ MinHashLSHForest index. Every operation is OpenTelemetry-instrumented (JSONL spans by default,
OTLP optional). An A/B eval harness proves (or disproves) agent-effectiveness: same messy
codebase task, run with baseline search tools vs. + clone-catcher, comparing token counts,
latency, agent loops, and answer quality against a planted ground truth.

## Architecture Decisions

- **MCP SDK v2** (`mcp>=2.0`): `MCPServer`, `@mcp.tool()`, type-hint-derived schemas,
  `structured_content` returns. Source: https://py.sdk.modelcontextprotocol.io/
- **tree-sitter-language-pack** (xberg-io fork, 371 grammars): keys `python`, `go`, `csharp`;
  parsers download on first use → `prefetch()` at startup for hermetic runs.
- **Structural tokenization**: pre-order DFS emitting named node types; prune
  identifier/literal/comment subtrees (exact set + `_identifier`/`_literal`/`_comment`
  suffixes); keep operator/keyword unnamed tokens except grouping punctuation. Renames and
  literal edits leave the stream byte-identical.
- **Shingling**: k=4 consecutive token n-grams (k configurable); short streams → single shingle.
- **Similarity**: MinHash Jaccard (128 perms, std ≈ 0.03 at J=0.9). LSH Forest top-k retrieval
  (k ≤ 50) then exact MinHash re-rank ≥ threshold, per datasketch 2.0 docs
  (https://ekzhu.com/datasketch/lshforest.html — over-retrieve + re-rank).
- **Tools**: `find_structural_clones(file_path, threshold=0.9)`, `get_diff_summary(file_a,
  file_b)`, plus `reindex_workspace()` (index freshness during refactor sessions; LSH Forest
  has no delete → rebuild). Index builds at server start and lazily on first query.
- **Telemetry**: non-global `TracerProvider` owned by a `Telemetry` instance (reload-safe in
  tests, no set-once global conflicts). JSONL span exporter always on (stdout is the MCP wire —
  never print there); OTLP HTTP exporter only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and the
  `[otlp]` extra is installed. Spans: tool calls + index build/query internals with
  `clone_catcher.*` attributes.
- **Eval harness** (`evals/`): planted-clone fixture repo + ground truth JSON; two arms
  (baseline: list/read/search tools; augmented: + clone-catcher over real stdio MCP);
  Anthropic tool-use loop when `ANTHROPIC_API_KEY` is set, deterministic scripted model
  otherwise (offline plumbing verification only — never reported as an effectiveness claim);
  metrics: input/output tokens, LLM turns, tool calls, wall time, server-side span latencies,
  pairwise precision/recall/F1 vs ground truth. (PyPI `mcp-eval` is an abandoned 2KB stub —
  custom harness chosen deliberately.)

## Task List

### Phase 1: Foundation — DONE
- [x] uv scaffold, deps (mcp 2.x, datasketch 2.0, tree-sitter-language-pack, otel api/sdk)
- [x] Empirical language-pack verification (python/go/csharp parse OK, prefetch available)

### Phase 2: Core (TDD — tests written first, red before green)
- [x] Structural tokenization invariants (rename/literal-invariant, operator-sensitive,
      multi-language, parse-error tolerant)
- [x] Signatures + LSH index (clone ≥0.9, unrelated <0.5, threshold/order/determinism)
- [x] Diff summary (identical-structure flag, regions with line ranges, similarity ordering)
- [x] Server tools over in-memory MCP client + telemetry spans on disk
- [x] stdio subprocess round-trip integration test

### Phase 3: Eval
- [x] Fixture repo (planted clone groups incl. Go/C# pairs, near-miss negatives) + ground truth
- [x] Calibration test: planted pairs ≥ expected similarity, negatives < 0.85
- [x] A/B harness + scripted-model offline verification
- [x] README (usage, config, eval methodology + honest reporting rules)

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Unrelated Python files share skeleton shingles | False positives | k=4 shingles; calibration test pins negative pairs < 0.85 |
| MinHash estimate variance near threshold | Boundary flapping | 128 perms (±0.03); threshold default 0.9 keeps margin |
| Grammar download at runtime (offline host) | Server stalls | `prefetch()` at startup; cache warm in venv env |
| LSH Forest recall at low k | Missed clones | k = min(50, index size) + exact re-rank (docs-endorsed) |
| Global OTel provider set-once | Reload/test breakage | Non-global provider instances per Telemetry object |

## Open Questions

- None blocking. Real-LLM eval run awaits `ANTHROPIC_API_KEY` (harness reports clearly when
  running in scripted mode).
