<div align="center">

# `slasht`

**Sub-millisecond AST-LSH Structural Code Deduplication & Architecture Intelligence Engine**

[![Go Version](https://img.shields.io/badge/Go-1.22+-00ADD8?style=flat&logo=go)](https://go.dev/)
[![Protocol](https://img.shields.io/badge/MCP-Protocol%20v1.0-blueviolet?style=flat)](https://modelcontextprotocol.io/)
[![Tree-sitter](https://img.shields.io/badge/Tree--sitter-Universal%20AST-28A745?style=flat)](https://tree-sitter.github.io/tree-sitter/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Instrumented-F54A00?style=flat&logo=opentelemetry)](https://opentelemetry.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*Find identical logic skeletons across Python, Go, and C# in milliseconds — eliminating LLM boilerplate crawling, hallucinated patterns, and token burn.*

---

[Key Capabilities](#-key-capabilities) • [Architecture](#-architecture) • [Empirical Benchmarks](#-empirical-ab-benchmarks) • [MCP Tools](#-mcp-tools) • [Quickstart](#-quickstart) • [Configuration](#-configuration)

</div>

---

## ⚡ The Problem

When coding agents (Claude, GPT, Gemini) refactor, audit, or standardize codebases, they default to sequential file reads, regex searches, and ad-hoc AST scripts. 

Across enterprise codebases:
- **Agents burn 60–85% of their token budget** repeatedly reading boilerplate and near-duplicate implementations.
- **Context saturation causes hallucinations**, inventing false patterns or missing large duplicated clusters entirely.
- **Wall-clock latency balloons**, turning quick refactorings into multi-minute, high-cost LLM loops.

## 🚀 The Solution: `slasht`

`slasht` is a high-performance **Model Context Protocol (MCP) server** written in Go that acts as a structural deduplication index for AI agents. 

Using **Tree-sitter**, **normalized AST token streams**, and **MinHash Locality-Sensitive Hashing (LSH) Forests**, `slasht` reduces entire codebases to their pure syntactic geometry (ignoring renames, formatting, literals, and comments).

In a **single 200ms tool call**, `slasht` maps every structural clone cluster across thousands of files, providing the agent with file lists, structural summaries, and clean representative code snippets upfront.

---

## 📊 Empirical A/B Benchmarks

We evaluated `slasht` across **5 distinct production codebases** totaling **1,917 files**, comparing standard coding agent workflows against `slasht`-augmented sessions using real model evaluation (`google-antigravity/gemini-3.7-flash:medium` on `omp`):

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                      AGGREGATE IMPACT ACROSS 1,917 FILES                      │
├──────────────────────┬──────────────────────┬──────────────────┬──────────────┤
│ Metric               │ Baseline (Standard)  │ With slasht      │ Savings      │
├──────────────────────┼──────────────────────┼──────────────────┼──────────────┤
│ Input Tokens         │ 927,370 tokens       │ 336,205 tokens   │ -63.7%       │
│ Output Tokens        │ 66,371 tokens        │ 17,387 tokens    │ -73.8%       │
│ LLM Turns / Calls    │ 183 turns            │ 60 turns         │ -67.2%       │
│ Wall-Clock Time      │ 592.9s (9.9 min)     │ 182.9s (3.0 min) │ 3.24× Faster │
│ Total API Cost       │ $1.418               │ $0.419           │ -70.5%       │
│ Clustering Accuracy  │ 0.53 F1              │ 0.82 F1          │ +0.29 F1     │
└──────────────────────┴──────────────────────┴──────────────────┴──────────────┘
```

### 1. Tier-1 Codebases with Natural Engineering Prompts

#### A. `tiangolo/fastapi` (78k+ ⭐, 950 Files, Python)
> **Realistic Prompt:** *"We are refactoring our API endpoints and request/response data models across the codebase to consolidate repetitive boilerplate into reusable generic patterns. Survey the repository, locate the major clusters of parallel endpoint and model implementations that follow the same structural shape, and identify the exact files in each cluster to consolidate."*

| Metric | Baseline | `slasht` | Delta / Impact |
|---|---:|---:|---|
| **Input Tokens** | 167,591 | **111,321** | **-33.6% token savings** |
| **Output Tokens** | 17,408 | **5,874** | **-66.3% fewer generation tokens** |
| **LLM Turns** | 33 | **16** | **-51.5% fewer roundtrips** |
| **Wall Time** | 88.0s | **43.1s** | **2.04× faster** |
| **Cost** | $0.280 | **$0.141** | **-49.6% cost reduction** |
| **F1 Score** | 0.07 | **0.29** | **4.1× higher accuracy** |

*Analysis:* Across 950 files, the baseline agent wrote 16 ad-hoc Python AST scripts, hallucinating 393 false clone pairs ($P=0.08$). `slasht` indexed all 950 files in **1.1 seconds** and surfaced the true structural model and endpoint test clusters.

---

#### B. `prometheus/prometheus` (55k+ ⭐, 727 Files, Go)
> **Realistic Prompt:** *"We are standardizing our service discovery and metric exporter integrations across this repository to eliminate copy-pasted boilerplate. Survey the codebase, locate all clusters of parallel plugin/discovery/exporter boilerplate implementations that follow the same structural pattern, and identify the exact files in each cluster to consolidate."*

| Metric | Baseline | `slasht` | Delta / Impact |
|---|---:|---:|---|
| **Input Tokens** | 251,422 | **79,499** | **-68.4% token savings** (171k saved) |
| **Output Tokens** | 12,061 | **4,425** | **-63.3% fewer output tokens** |
| **LLM Turns** | 40 | **12** | **-70.0% fewer turns** |
| **Wall Time** | 110.3s | **38.2s** | **2.89× faster** |
| **Cost** | $0.349 | **$0.096** | **-72.5% cost reduction** |
| **F1 Score** | 0.71 | **0.82** | **+0.11 accuracy boost** |

*Analysis:* Indexed all 727 Go files in **2.7s**, instantly surfacing 26 plugin provider files (`plugin_aws.go`, `plugin_azure.go`, etc.) and 17 service discovery metric definitions that share byte-for-byte identical AST skeletons.

---

### 2. Multi-Language & Architecture Analysis

| Repository | Scale & Language | Input Token Savings | LLM Call Reduction | Speedup | F1 Accuracy |
|---|---|---:|---:|---:|---:|
| **`gin-gonic/gin`** | 99 files, Go | **-85.5%** | **-84.6%** (4 vs 26 turns) | **12.7×** (11.6s vs 147.5s) | **1.00** vs 0.57 |
| **`pallets/click`** | 75 files, Python | **-60.8%** | **-45.0%** (11 vs 20 turns) | **4.26×** (28.8s vs 122.8s) | **1.00** vs 0.00 |
| **SaaS Monorepo** | 66 files, Polyglot (Py/Go/C#) | **-68.7%** | **-73.4%** (17 vs 64 turns) | **2.03×** (61.2s vs 124.3s) | **1.00** vs 1.00 |

---

## 🛠️ Architecture

```
                    ┌────────────────────────┐
                    │      Source File       │
                    │   (.py / .go / .cs)    │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │  Tree-sitter Parser    │
                    │  (C-Level TreeCursor)  │
                    └───────────┬────────────┘
                                │ Zero-allocation DFS
                                ▼
                    ┌────────────────────────┐
                    │ Structural Tokenizer   │
                    │ (Prune Names/Literals) │
                    └───────────┬────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
     ┌─────────────────────┐         ┌─────────────────────┐
     │ 4-Shingle xxHash64  │         │  Token Sequence     │
     └──────────┬──────────┘         │  Myers Diff Engine  │
                │                    └──────────┬──────────┘
                ▼                               │
     ┌─────────────────────┐                    ▼
     │ 128-Perm MinHash    │         ┌─────────────────────┐
     └──────────┬──────────┘         │   AST Diff Report   │
                │                    │ (get_diff_summary)  │
                ▼                    └─────────────────────┘
     ┌─────────────────────┐
     │ LSH Forest Index    │
     │ (8 Prefix Bands)    │
     └──────────┬──────────┘
                │
                ▼
     ┌─────────────────────┐
     │ Disjoint-Set Union  │
     │ Clone Cluster Map   │
     └─────────────────────┘
```

- **Universal Geometry:** Renaming variables, modifying string literals, or adding comments yields an identical token stream. Adding a branch, changing an operator, or restructuring a loop modifies the fingerprint.
- **Prefix Tree LSH Forest:** Multi-band hash indexing allows sub-linear nearest-neighbor lookup without $O(N^2)$ pairwise comparisons.
- **Zero-Allocation Traversal:** Traverses ASTs via native C pointers, capable of indexing **1,000+ files per second**.

---

## 🧰 MCP Tools

`slasht` exposes four high-efficiency JSON-RPC tools:

| Tool | Parameters | Description |
|---|---|---|
| `find_duplicate_groups` | `threshold` (default `0.9`), `max_groups` (25), `max_files_per_group` (20) | **Call this FIRST.** Maps every structural clone cluster in the repository with sample file paths, 4-line preview snippets, and structural summaries. |
| `find_structural_clones` | `file_path` (required), `threshold` (default `0.9`) | Returns all files in the workspace structurally similar to `file_path` ranked by Jaccard similarity. |
| `get_diff_summary` | `file_a` (required), `file_b` (required) | Reports whether two files share identical structure (`identical_structure: true`) and pinpoints differing AST node types and line spans. |
| `reindex_workspace` | *None* | Rebuilds the in-memory index from disk on demand after files are created, moved, or edited. |

---

## 🚀 Quickstart

### 1. Build the Standalone Binary

```bash
# Clone the repository
git clone https://github.com/carlpatchett/slasht.git
cd slasht

# Run test suite
go test -v -race ./...

# Build single static binary
go build -o bin/slasht ./cmd/clone-catcher
```

### 2. Configure Your Agent Host

Add `slasht` to your MCP configuration (e.g. `~/.omp/agent/mcp.json`, Claude Desktop, or Cursor):

```json
{
  "mcpServers": {
    "slasht": {
      "command": "/absolute/path/to/slasht/bin/slasht",
      "env": {
        "CLONE_CATCHER_ROOT": "${PWD}",
        "CLONE_CATCHER_TRACE_PATH": "${TMPDIR:-/tmp}/slasht_trace.jsonl"
      }
    }
  }
}
```

---

## ⚙️ Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `CLONE_CATCHER_ROOT` | Current Working Dir (`cwd`) | Root directory to index and resolve relative paths against. |
| `CLONE_CATCHER_TRACE_PATH` | `""` (disabled) | Destination file path for OpenTelemetry JSONL span logging. |
| `CLONE_CATCHER_SHINGLE_K` | `4` | Token shingle width for MinHash fingerprinting. |
| `CLONE_CATCHER_NUM_PERM` | `128` | MinHash permutations (128 yields standard error $\approx 0.03$). |
| `CLONE_CATCHER_EXCLUDE` | `.git,.jj,node_modules,.venv,...` | Comma-separated list of directory names to skip during indexing. |

---

## 📈 Observability & OpenTelemetry

`slasht` is fully instrumented with OpenTelemetry (`go.opentelemetry.io/otel`):
- Measures indexing throughput, LSH query latency, and AST parsing durations.
- Emits spans non-blockingly to a local JSONL trace file without interfering with standard I/O streams.
- Provides concrete, verifiable metrics on server-side performance.

---

## 📜 License

MIT License. Designed and built by [Carl Patchett](https://github.com/carlpatchett).
