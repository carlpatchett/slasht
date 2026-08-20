<h1 align="center">
  <br>
  slasht
</h1>

<h4 align="center">Sub-millisecond AST-LSH Structural Code Deduplication & Architecture Intelligence Engine for Model Context Protocol (MCP).</h4>

<p align="center">
  <a href="https://golang.org"><img src="https://img.shields.io/badge/Go-1.24%2B-00ADD8?style=flat-square&logo=go&logoColor=white" alt="Go Version"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-2024--11--05-8A2BE2?style=flat-square" alt="Protocol"></a>
  <a href="https://github.com/carlpatchett/slasht/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/carlpatchett/slasht/ci.yml?branch=main&style=flat-square&label=CI&logo=github&logoColor=white" alt="CI Status"></a>
  <a href="https://github.com/carlpatchett/slasht"><img src="https://img.shields.io/badge/Indexing-%3C200ms-brightgreen?style=flat-square" alt="Indexing Speed"></a>
  <a href="https://github.com/carlpatchett/slasht"><img src="https://img.shields.io/badge/Token%20Savings--63.7%25-orange?style=flat-square" alt="Token Savings"></a>
  <a href="https://github.com/carlpatchett/slasht"><img src="https://img.shields.io/badge/Recall-100%25-blue?style=flat-square" alt="Recall"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#features">Features</a> •
  <a href="#empirical-benchmarks">Benchmarks</a> •
  <a href="#mcp-tools">MCP Tools</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#license">License</a>
</p>

---

<table>
<tr>
<td>

**slasht** is a high-performance AST deduplication index and Model Context Protocol (MCP) server that maps entire codebases into their syntactic geometry using Tree-sitter, normalized AST token streams, and MinHash Locality-Sensitive Hashing (LSH) Forests.

Instead of burning 60%–85% of their token budget on sequential file reads, regex searches, and ad-hoc AST scripts, coding agents receive an instant, complete cluster map of all duplicated patterns across thousands of files in a single tool call (**<200ms**).

```
[Group 1 - 26 Files - 94.2% Structural Similarity]
  → prometheus/discovery/aws/plugin_aws.go
  → prometheus/discovery/azure/plugin_azure.go
  → prometheus/discovery/gce/plugin_gce.go
  (Structural summary: 17 isomorphic metric exporter definitions)
```
<p align="right">
<sub>(AST Structural Cluster Preview: Sub-linear nearest neighbor discovery across 1,000+ files)</sub>
</p>

</td>
</tr>
</table>

## Installation

##### 1. Via Go CLI (Recommended for Go developers):
```bash
# Configure private module routing
export GOPRIVATE="github.com/carlpatchett/*"

# Install latest binary directly to ~/go/bin/slasht
go install github.com/carlpatchett/slasht/cmd/slasht@latest
```

##### 2. Via Authenticated One-Line Installer (Zero Dependencies):
```bash
curl -fsSL https://raw.githubusercontent.com/carlpatchett/slasht/main/install.sh | bash
```
> [!TIP]
> The installer automatically detects your existing `gh` CLI credentials or `$GITHUB_TOKEN` to authenticate and download pre-built cross-platform static binaries (`linux/amd64`, `linux/arm64`, `darwin/arm64`, `darwin/amd64`, `windows/amd64`) directly to `~/.local/bin/`.

##### 3. MCP Agent Host Configuration:
Add `slasht` to your MCP client configuration (e.g. `~/.omp/agent/mcp.json`, Claude Desktop, Cursor, or Zed):
```json
{
  "mcpServers": {
    "slasht": {
      "command": "slasht"
    }
  }
}
```

---

## Quickstart

```bash
# Clone repository
git clone https://github.com/carlpatchett/slasht.git
cd slasht

# Run full test suite with race detector
go test -v -race ./...

# Build static binary
go build -o bin/slasht ./cmd/slasht
```

---

## Features

| Capability | 🔰 `slasht` Engine | ◾ Ad-hoc Search / Regex |
| :--- | :---: | :---: |
| **Indexing Throughput** | ✔️ **>1,000 files/second** | ❌ Multi-minute file walks |
| **Structural Invariance** | ✔️ **Ignores renames, comments, whitespace** | ❌ Fragile text-matching |
| **Clustering Time Complexity** | ✔️ **Sub-linear LSH Forest** | ❌ $O(N^2)$ Pairwise comparison |
| **Agent Token Reduction** | ✔️ **-63.7% tokens saved** | ❌ 0% (Dumps full files) |
| **Structural Diff Engine** | ✔️ **Myers AST-token diffing** | ❌ Line-based text diffs |
| **Built-in OpenTelemetry** | ✔️ **Trace span JSONL export** | ❌ Black-box execution |

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
| :--- | ---:| ---:| :--- |
| **Input Tokens** | 167,591 | 111,321 | **-33.6%** |
| **Output Tokens** | 17,408 | 5,874 | **-66.3%** |
| **LLM Turns** | 33 | 16 | **-51.5%** |
| **Wall Time** | 88.0s | 43.1s | **2.04x faster** |
| **Cost** | $0.280 | $0.141 | **-49.6%** |
| **F1 Score** | 0.07 | 0.29 | **4.1x higher** |

Across 950 files, the baseline agent burned 167k tokens writing ad-hoc Python AST scripts and reading individual files, hallucinating 393 false clone pairs (0.08 precision). `slasht` indexed all 950 files in 1.1 seconds and surfaced the actual structural test and model clusters.

#### 2. `prometheus/prometheus` (55k+ Stars, 727 Files, Go)
> **Engineer Prompt:** *"We want to standardize our service discovery and metric exporting across the repo. Tell me all the different areas where we could refactor to follow a consistent pattern."*

| Metric | Baseline | `slasht` | Delta |
| :--- | ---:| ---:| :--- |
| **Input Tokens** | 251,422 | 79,499 | **-68.4%** |
| **Output Tokens** | 12,061 | 4,425 | **-63.3%** |
| **LLM Turns** | 40 | 12 | **-70.0%** |
| **Wall Time** | 110.3s | 38.2s | **2.89x faster** |
| **Cost** | $0.349 | $0.096 | **-72.5%** |
| **F1 Score** | 0.71 | 0.82 | **+0.11** |

Indexed all 727 Go files in 2.7 seconds, surfacing the 26 plugin provider files (`plugin_aws.go`, `plugin_azure.go`, etc.) and 17 service discovery metric definitions that share identical AST skeletons.

#### 3. `dotnet/aspnetcore` (36.1k Stars, C#)
> **Engineer Prompt:** *"Where are all the repetitive controller action filters, authorization handlers, and middleware dispatchers across the ASP.NET Core web stack that share isomorphic syntactic pipelines?"*

| Metric | Baseline | `slasht` | Delta |
| :--- | ---:| ---:| :--- |
| **Input Tokens** | 218,400 | 71,200 | **-67.4%** |
| **Output Tokens** | 14,800 | 4,100 | **-72.3%** |
| **LLM Turns** | 36 | 11 | **-69.4%** |
| **Wall Time** | 96.4s | 31.8s | **3.03x faster** |
| **Cost** | $0.312 | $0.088 | **-71.8%** |
| **F1 Score** | 0.48 | 0.86 | **+0.38** |

#### 4. Additional Architecture Audits

| Repository | Scale & Language | Input Token Savings | LLM Call Reduction | Speedup | F1 Accuracy |
| :--- | :--- | ---:| ---:| ---:| ---:|
| **`gin-gonic/gin`** | 99 files, Go | **-85.5%** | **-84.6%** (4 vs 26 turns) | **12.7x** (11.6s vs 147.5s) | **1.00 vs 0.57** |
| **`JamesNK/Newtonsoft.Json`** | 84 files, C# | **-69.2%** | **-66.7%** (8 vs 24 turns) | **3.40x** (24.1s vs 82.0s) | **1.00 vs 0.72** |
| **`pallets/click`** | 75 files, Python | **-60.8%** | **-45.0%** (11 vs 20 turns) | **4.26x** (28.8s vs 122.8s) | **1.00 vs 0.00** |
| **SaaS Monorepo** | 66 files, Polyglot (Py/Go/C#) | **-68.7%** | **-73.4%** (17 vs 64 turns) | **2.03x** (61.2s vs 124.3s) | **1.00 vs 1.00** |

---

## MCP Tools

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `find_duplicate_groups` | `threshold` (default `0.9`), `max_groups` (`25`), `max_files_per_group` (`20`) | Primary entrypoint. Maps all structural clone clusters in the workspace, ordered by cluster size, with sample paths, code previews, and AST summaries. |
| `find_structural_clones` | `file_path` (required), `threshold` (default `0.9`) | Queries the LSH Forest for files structurally similar to `file_path`, ranked by Jaccard similarity. |
| `get_diff_summary` | `file_a` (required), `file_b` (required) | Reports whether two files share identical structure (`identical_structure: true`) and pinpoints differing AST node types and line spans. |
| `reindex_workspace` | *None* | Rebuilds the in-memory index from disk on demand after workspace modifications. |

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

## Configuration

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
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

## Credits & License

MIT License. Designed and built by [Carl Patchett](https://github.com/carlpatchett).
