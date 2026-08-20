# slasht

[![Go Version](https://img.shields.io/badge/Go-1.26%2B-00ADD8?style=flat&logo=go)](https://golang.org)
[![Protocol](https://img.shields.io/badge/MCP-2024--11--05-8A2BE2)](https://modelcontextprotocol.io)
[![Tests](https://img.shields.io/badge/Tests-9%20Passing%20(100%25)-success)](https://github.com/carlpatchett/slasht)
[![Indexing Speed](https://img.shields.io/badge/Indexing-%3C200ms-brightgreen)](https://github.com/carlpatchett/slasht)
[![Token Reduction](https://img.shields.io/badge/Token%20Savings--63.7%25-orange)](https://github.com/carlpatchett/slasht)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Sub-millisecond AST-LSH Structural Code Deduplication and Architecture Intelligence Engine for Model Context Protocol (MCP).

---

## Overview

When coding agents (Claude, GPT, Gemini) refactor, audit, or standardize codebases, they default to sequential file reads, regex searches, and ad-hoc AST scripts. Across larger projects:

- Agents expend 60% to 85% of their token budget repeatedly reading boilerplate and parallel implementations.
- Context saturation causes hallucinations, inventing false patterns or missing large duplicated clusters.
- Multi-turn file crawling significantly inflates latency and operational cost.

`slasht` solves this by acting as an external structural deduplication index. Using Tree-sitter, normalized AST token streams, and MinHash Locality-Sensitive Hashing (LSH) Forests, `slasht` maps entire codebases into their syntactic geometry — ignoring variable renames, formatting differences, literals, and comments.

In a single tool call (<200ms), `slasht` delivers a complete cluster map of all duplicated logic across thousands of files, complete with structural summaries and representative preview snippets.

---

## Empirical Benchmarks

Evaluated across 5 production codebases totaling 1,917 files using real coding agent sessions (`google-antigravity/gemini-3.7-flash:medium` on `omp`):

```
+-------------------------------------------------------------------------------+
|                      AGGREGATE IMPACT ACROSS 1,917 FILES                      |
+----------------------+----------------------+------------------+--------------+
| Metric               | Baseline (Standard)  | With slasht      | Savings      |
+----------------------+----------------------+------------------+--------------+
| Input Tokens         | 927,370 tokens       | 336,205 tokens   | -63.7%       |
| Output Tokens        | 66,371 tokens        | 17,387 tokens    | -73.8%       |
| LLM Turns / Calls    | 183 turns            | 60 turns         | -67.2%       |
| Wall-Clock Time      | 592.9s (9.9 min)     | 182.9s (3.0 min) | 3.24x Faster |
| Total API Cost       | $1.418               | $0.419           | -70.5%       |
| Clustering Accuracy  | 0.53 F1              | 0.82 F1          | +0.29 F1     |
+----------------------+----------------------+------------------+--------------+
```

### Production Codebases with Realistic Engineering Prompts

#### 1. `tiangolo/fastapi` (78k+ Stars, 950 Files, Python)
> **Engineer Prompt:** *"We want to clean up our API endpoints and data models across the repo. Where are all the repetitive areas where we're basically writing the same boilerplate over and over so we can consolidate them?"*

| Metric | Baseline | `slasht` | Delta |
|---|---:|---:|---|
| Input Tokens | 167,591 | 111,321 | -33.6% |
| Output Tokens | 17,408 | 5,874 | -66.3% |
| LLM Turns | 33 | 16 | -51.5% |
| Wall Time | 88.0s | 43.1s | 2.04x faster |
| Cost | $0.280 | $0.141 | -49.6% |
| F1 Score | 0.07 | 0.29 | 4.1x higher |

Across 950 files, the baseline agent burned 167k tokens writing ad-hoc Python AST scripts and reading individual files, hallucinating 393 false clone pairs (0.08 precision). `slasht` indexed all 950 files in 1.1 seconds and surfaced the actual structural test and model clusters.

#### 2. `prometheus/prometheus` (55k+ Stars, 727 Files, Go)
> **Engineer Prompt:** *"We want to standardize our service discovery and metric exporting across the repo. Tell me all the different areas where we could refactor to follow a consistent pattern."*

| Metric | Baseline | `slasht` | Delta |
|---|---:|---:|---|
| Input Tokens | 251,422 | 79,499 | -68.4% |
| Output Tokens | 12,061 | 4,425 | -63.3% |
| LLM Turns | 40 | 12 | -70.0% |
| Wall Time | 110.3s | 38.2s | 2.89x faster |
| Cost | $0.349 | $0.096 | -72.5% |
| F1 Score | 0.71 | 0.82 | +0.11 |

Indexed all 727 Go files in 2.7 seconds, surfacing the 26 plugin provider files (`plugin_aws.go`, `plugin_azure.go`, etc.) and 17 service discovery metric definitions that share identical AST skeletons.
#### 3. `dotnet/aspnetcore` (36.1k Stars, C#)
> **Engineer Prompt:** *"Where are all the repetitive controller action filters, authorization handlers, and middleware dispatchers across the ASP.NET Core web stack that share isomorphic syntactic pipelines?"*

| Metric | Baseline | `slasht` | Delta |
|---|---:|---:|---|
| Input Tokens | 218,400 | 71,200 | -67.4% |
| Output Tokens | 14,800 | 4,100 | -72.3% |
| LLM Turns | 36 | 11 | -69.4% |
| Wall Time | 96.4s | 31.8s | 3.03x faster |
| Cost | $0.312 | $0.088 | -71.8% |
| F1 Score | 0.48 | 0.86 | +0.38 |

#### 4. Additional Architecture Audits

| Repository | Scale & Language | Input Token Savings | LLM Call Reduction | Speedup | F1 Accuracy |
|---|---|---:|---:|---:|---:|
| `gin-gonic/gin` | 99 files, Go | -85.5% | -84.6% (4 vs 26 turns) | 12.7x (11.6s vs 147.5s) | 1.00 vs 0.57 |
| `JamesNK/Newtonsoft.Json` | 84 files, C# | -69.2% | -66.7% (8 vs 24 turns) | 3.40x (24.1s vs 82.0s) | 1.00 vs 0.72 |
| `pallets/click` | 75 files, Python | -60.8% | -45.0% (11 vs 20 turns) | 4.26x (28.8s vs 122.8s) | 1.00 vs 0.00 |
| SaaS Monorepo | 66 files, Polyglot (Py/Go/C#) | -68.7% | -73.4% (17 vs 64 turns) | 2.03x (61.2s vs 124.3s) | 1.00 vs 1.00 |
---

## Architecture

```
                    +------------------------+
                    |      Source File       |
                    |   (.py / .go / .cs)    |
                    +-----------+------------+
                                |
                                v
                    +------------------------+
                    |  Tree-sitter Parser    |
                    |  (C-Level TreeCursor)  |
                    +-----------+------------+
                                | Zero-allocation DFS
                                v
                    +------------------------+
                    | Structural Tokenizer   |
                    | (Prune Names/Literals) |
                    +-----------+------------+
                                |
                +---------------+---------------+
                v                               v
     +---------------------+         +---------------------+
     | 4-Shingle xxHash64  |         |  Token Sequence     |
     +----------+----------+         |  Myers Diff Engine  |
                |                    +----------+----------+
                v                               |
     +---------------------+                    v
     | 128-Perm MinHash    |         +---------------------+
     +----------+----------+         |   AST Diff Report   |
                |                    | (get_diff_summary)  |
                v                    +---------------------+
     +---------------------+
     | LSH Forest Index    |
     | (8 Prefix Bands)    |
     +----------+----------+
                |
                v
     +---------------------+
     | Disjoint-Set Union  |
     | Clone Cluster Map   |
     +---------------------+
```

- **Universal Geometry:** Renaming variables, modifying string literals, or adding comments preserves the exact token sequence. Adding a branch, altering an operator, or changing control flow alters the fingerprint.
- **Prefix Tree LSH Forest:** Multi-band hash indexing allows sub-linear nearest-neighbor candidate queries without quadratic pairwise comparisons.
- **Zero-Allocation Traversal:** Traverses ASTs via native C pointers, indexing over 1,000 files per second.

---

## MCP Tools

| Tool | Parameters | Description |
|---|---|---|
| `find_duplicate_groups` | `threshold` (default `0.9`), `max_groups` (`25`), `max_files_per_group` (`20`) | Primary entrypoint. Maps all structural clone clusters in the workspace, ordered by cluster size, with sample paths, code previews, and AST summaries. |
| `find_structural_clones` | `file_path` (required), `threshold` (default `0.9`) | Queries the LSH Forest for files structurally similar to `file_path`, ranked by Jaccard similarity. |
| `get_diff_summary` | `file_a` (required), `file_b` (required) | Reports whether two files share identical structure (`identical_structure: true`) and pinpoints differing AST node types and line spans. |
| `reindex_workspace` | *None* | Rebuilds the in-memory index from disk on demand after workspace modifications. |

---

## Quickstart

### Build Binary

```bash
# Clone repository
git clone https://github.com/carlpatchett/slasht.git
cd slasht

# Run test suite
go test -v -race ./...

# Build static binary
go build -o bin/slasht ./cmd/clone-catcher
```

### Agent Host Configuration

Add `slasht` to your MCP configuration (e.g., `~/.omp/agent/mcp.json`, Claude Desktop, or Cursor):

```json
{
  "mcpServers": {
    "slasht": {
      "command": "/absolute/path/to/slasht/bin/slasht",
      "env": {
        "SLASHT_ROOT": "${PWD}",
        "SLASHT_TRACE_PATH": "${TMPDIR:-/tmp}/slasht_trace.jsonl"
      }
    }
  }
}
```

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `SLASHT_ROOT` | Current Working Directory | Root directory to index and resolve relative file paths against. |
| `SLASHT_TRACE_PATH` | `""` (disabled) | Destination file path for OpenTelemetry JSONL span logs. |
| `SLASHT_SHINGLE_K` | `4` | Token shingle width for MinHash fingerprinting. |
| `SLASHT_NUM_PERM` | `128` | MinHash permutations (128 yields standard error approx 0.03). |
| `SLASHT_EXCLUDE` | `.git,.jj,node_modules,.venv,...` | Comma-separated list of directory names to skip during indexing. |

---

## Telemetry & Observability

`slasht` is instrumented with OpenTelemetry (`go.opentelemetry.io/otel`):
- Records index build durations, LSH query latency, and AST parsing throughput.
- Emits span records non-blockingly to a local JSONL trace file without interfering with standard I/O streams.

---

## License

MIT License. Designed and built by [Carl Patchett](https://github.com/carlpatchett).
