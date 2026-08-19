# clone-catcher

An MCP server that finds **structural code clones** — files whose logic has the
same shape but different names, literals, and comments — across Python, Go, and
C#. Its purpose: stop coding agents from burning tokens reading (and re-reading)
near-identical boilerplate, and prove with telemetry whether it actually helps.

## Using it inside omp

Build the single static binary:
```bash
go build -o bin/clone-catcher ./cmd/clone-catcher
```

Register in `~/.omp/agent/mcp.json`:

```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
  "mcpServers": {
    "clone-catcher": {
      "command": "/home/carlpatchett/repos/clone-catcher/bin/clone-catcher",
      "env": {
        "CLONE_CATCHER_ROOT": "${PWD}",
        "CLONE_CATCHER_TRACE_PATH": "${TMPDIR:-/tmp}/clone_catcher_trace.jsonl"
      }
    }
  }
}
```

`${PWD}` expands at discovery time to the directory omp was launched in, so
each session indexes the repo you're actually working in (lazily, on the first
tool call). Register with `/mcp add` or edit the file directly, then
`/mcp reload` in a live session and `/mcp test clone-catcher`. Tools appear as
`mcp__clone_catcher_find_duplicate_groups` etc.
## How it works

```
source file ──tree-sitter──▶ AST ──skeleton extract──▶ token stream
   (if_statement, call, return, +, and, ...)   names/literals/comments pruned
        │
        ├──k-shingle──▶ MinHash (128 perms) ──▶ MinHashLSHForest index
        └──SequenceMatcher──▶ AST diff regions (get_diff_summary)
```

Two files score 1.0 when their skeletons are identical — rename every
identifier and change every string, they still match. Add a branch or swap an
operator and they don't.

## Tools

| tool | what it does |
|---|---|
| `find_duplicate_groups(threshold=0.9)` | List every group of structurally duplicated files in the workspace, largest first, with per-group similarity stats. Call this BEFORE reading files to decide what is worth reading at all. |
| `find_structural_clones(file_path, threshold=0.9)` | Files structurally similar to `file_path` (paths relative to the indexed root, similarity desc). |
| `get_diff_summary(file_a, file_b)` | Whether two files differ only in naming/literals (`identical_structure: true`), and if not, which AST node types/line ranges differ. |
| `reindex_workspace()` | Rebuild the index after files change (indexing is otherwise lazy: on the first query). |

## Quickstart

```bash
go test -v -race ./...       # run all unit and integration tests
go build -o bin/clone-catcher ./cmd/clone-catcher # compile standalone binary
```

Register with an MCP host (stdio JSON-RPC transport):

```json
{
  "mcpServers": {
    "clone-catcher": {
      "command": "/abs/path/to/bin/clone-catcher",
      "env": { "CLONE_CATCHER_ROOT": "/path/to/repo/to/index" }
    }
  }
}
```

## Configuration (environment)

| variable | default | meaning |
|---|---|---|
| `CLONE_CATCHER_ROOT` | cwd | workspace to index/resolve relative paths against |
| `CLONE_CATCHER_EXCLUDE` | `.git,.jj,node_modules,.venv,__pycache__,dist,build,target,...` | comma-separated directory names to skip |
| `CLONE_CATCHER_SHINGLE_K` | `4` | shingle width over skeleton tokens |
| `CLONE_CATCHER_NUM_PERM` | `128` | MinHash permutations (128 ⇒ similarity std ≈ 0.03 at J=0.9) |
| `CLONE_CATCHER_TRACE_PATH` | `./clone_catcher_trace.jsonl` | OpenTelemetry span file |
| `CLONE_CATCHER_MAX_K` | `50` | LSH forest candidates per query before exact re-rank |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | if set (with the `[otlp]` extra), spans also go to an OTLP/HTTP collector |

## Telemetry

Every tool call and index operation emits an OTel span (`opentelemetry-api`
/`-sdk`). The default exporter appends JSON lines — `name`, `trace_id`,
`duration_ms`, `clone_catcher.*` attributes — so latency is measurable without
any collector. Install `clone-catcher[otlp]` and set
`OTEL_EXPORTER_OTLP_ENDPOINT` to additionally ship spans to a collector. The
provider is intentionally not the process-global one: stdout stays clean (it's
the MCP wire) and tests/reloads can't corrupt tracing state.

## Proving it works: the A/B eval harness

`evals/` contains the effectiveness experiment:

- **Fixture** (`evals/messy_codebase/`): a synthetic "legacy" repo with five
  planted clone groups (3× Python, 1× Go, 1× C#), one deliberately
  structurally-similar-but-not-a-clone negative pair, and neutral noise.
- **Ground truth** (`evals/ground_truth.json`): expected groups with minimum
  similarities. `tests/test_fixture_calibration.py` pins the fixture: planted
  pairs must measure above their floor, negatives and cross-group pairs below
  0.85, and every group must be recoverable via `find_structural_clones`.
- **Harness** (`evals/harness.py`): runs the same "find all duplicated logic"
  task twice — **baseline** (list/read/search tools only) vs **augmented**
  (same tools + clone-catcher over real stdio MCP) — then reports input/output
  tokens, LLM turns, tool calls, wall time, pairwise precision/recall/F1, and
  server-side per-tool latency from the OTel spans.

```bash
# offline: verifies plumbing end to end (synthetic numbers, explicitly marked)
uv run python evals/harness.py

# live A/B run (real model, real token counts — the actual claim)
export ANTHROPIC_API_KEY=...
uv run --group eval python evals/harness.py --model claude-sonnet-4-5
```

Reports land in `evals/results/` as markdown + JSON.

> **Honesty rule:** `mode=scripted` reports carry a disclaimer in the output —
> they prove the harness works, not that clone-catcher helps. Only live-mode
> runs are evidence of effectiveness.

### Running the A/B through omp (live model)

`evals/omp_eval.py` runs both arms as real `omp -p` sessions against two
isolated fixture copies — the augmented copy registers clone-catcher via a
project-level `.omp/mcp.json`, and the user-level `~/.omp/agent/mcp.json` is
swapped aside for the run so the baseline can never see it. Token/cost metrics
come from omp's own per-call usage telemetry; tool calls from the event
stream; server latency from the OTel spans.

```bash
# Small synthetic fixture (16 files)
uv run python evals/omp_eval.py --model google-antigravity/gemini-3.7-flash:medium

# Large synthetic "growth-stage SaaS" fixture (~65 beefy files, 6k LOC)
uv run python evals/omp_eval.py --fixture large --model google-antigravity/gemini-3.7-flash:medium

# Public repo (cost metrics only; clones depth-1 and uses find_duplicate_groups as reference)
uv run python evals/omp_eval.py --repo https://github.com/ansible/ansible --max-time 20m
```

If you run public repos, some legendary structural-clone candidates:
- `https://github.com/ansible/ansible` (Python modules)
- `https://github.com/hashicorp/terraform` (Go provider schemas)
- `https://github.com/home-assistant/core` (Python components)

### Empirical A/B Benchmark Results

We evaluated `clone-catcher` using real coding agent sessions (`google-antigravity/gemini-3.7-flash:medium` running on `omp`) across **five distinct codebases** totaling **1,917 files**, including tier-1 repositories with tens of thousands of GitHub stars and both explicit and natural real-world refactoring prompts:

1. [`tiangolo/fastapi`](https://github.com/tiangolo/fastapi) (78k+ stars, 950 files, Python) — *Natural API & Data Model Refactoring Prompt*
2. [`prometheus/prometheus`](https://github.com/prometheus/prometheus) (55k+ stars, 727 files, Go) — *Natural Service Discovery & Plugin Refactoring Prompt*
3. [`gin-gonic/gin`](https://github.com/gin-gonic/gin) (78k+ stars, 99 files, Go) — *Binding & Codec Architecture Analysis*
4. [`pallets/click`](https://github.com/pallets/click) (16k+ stars, 75 files, Python) — *Typing & Interface Duplication Audit*
5. **Synthetic Growth-Stage SaaS Monorepo** (66 files, 6,700 LOC, Polyglot Python + Go + C#) — *130 Ground-Truth Clone Pairs*

---

#### Benchmark 1: Tier-1 Production Codebases with Natural Refactoring Prompts

##### A. `tiangolo/fastapi` (78,000+ stars, 950 files, Python)
> **Engineer Prompt:** *"We are refactoring our API endpoints and request/response data models across the codebase to consolidate repetitive boilerplate into reusable generic patterns. Survey the repository, locate the major clusters of parallel endpoint and model implementations that follow the same structural shape, and identify the exact files in each cluster to consolidate."*

| Arm | Input Tokens | Output Tokens | LLM Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 167,591 | 17,408 | 33 | 88.0s | $0.280 | 0.08 | 0.06 | 0.07 |
| **Augmented** (+ clone-catcher) | 111,321 | 5,874 | 16 | 43.1s | $0.141 | 0.57 | 0.20 | **0.29** |
| **Impact / Savings** | **-33.6%** | **-66.3%** | **-51.5%** | **2.04× faster** | **-49.6%** | **7.1× higher** | **3.3× higher** | **4.1× higher** |

*Note on Scale:* Across 950 files, the baseline agent burned 167k tokens writing 16 Python AST scripts and reading files, hallucinating 393 false pairs (P=0.08). The augmented agent indexed all 950 files in 1.1s and identified the actual structural test and model clusters in half the time and turns.

##### B. `prometheus/prometheus` (55,000+ stars, 727 files, Go)
> **Engineer Prompt:** *"We are standardizing our service discovery and metric exporter integrations across this repository to eliminate copy-pasted boilerplate. Survey the codebase, locate all clusters of parallel plugin/discovery/exporter boilerplate implementations that follow the same structural pattern, and identify the exact files in each cluster to consolidate."*

| Arm | Input Tokens | Output Tokens | LLM Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 251,422 | 12,061 | 40 | 110.3s | $0.349 | 0.57 | 0.94 | 0.71 |
| **Augmented** (+ clone-catcher) | 79,499 | 4,425 | 12 | 38.2s | $0.096 | 0.73 | 0.94 | **0.82** |
| **Impact / Savings** | **-68.4%** | **-63.3%** | **-70.0%** | **2.89× faster** | **-72.5%** | **+0.16** | **Parity** | **+0.11** |

*Note on Scale:* Indexed all 727 Go files in 2.7s. Instantly surfaced the 26 plugin provider files (`plugin_aws.go`, `plugin_azure.go`, etc.) and 17 service discovery metric definitions that share byte-for-byte AST skeletons.

---

#### Benchmark 2: Structural Architecture Audits (Targeted Repositories)

##### C. `gin-gonic/gin` (78,000+ stars, 99 files, Go)
| Arm | Input Tokens | Output Tokens | LLM Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 127,787 | 13,819 | 26 | 147.5s | $0.217 | 0.40 | 1.00 | 0.57 |
| **Augmented** (+ clone-catcher) | 18,575 | 944 | 4 | 11.6s | $0.023 | 1.00 | 1.00 | **1.00** |
| **Impact / Savings** | **-85.5%** | **-93.2%** | **-84.6%** | **12.7× faster** | **-89.4%** | **+0.60** | **Parity** | **+0.43** |

##### D. `pallets/click` (16,000+ stars, 75 files, Python)
| Arm | Input Tokens | Output Tokens | LLM Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 98,915 | 9,239 | 20 | 122.8s | $0.161 | 0.00 | 0.00 | 0.00 |
| **Augmented** (+ clone-catcher) | 38,770 | 1,658 | 11 | 28.8s | $0.051 | 1.00 | 1.00 | **1.00** |
| **Impact / Savings** | **-60.8%** | **-82.1%** | **-45.0%** | **4.26× faster** | **-68.3%** | **+1.00** | **+1.00** | **+1.00** |

##### E. Synthetic Monorepo (66 files, Polyglot Python/Go/C#, 130 Truth Pairs)
| Arm | Input Tokens | Output Tokens | LLM Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 281,655 | 13,844 | 64 | 124.3s | $0.411 | 1.00 | 1.00 | **1.00** |
| **Augmented** (+ clone-catcher) | 88,040 | 4,486 | 17 | 61.2s | $0.108 | 1.00 | 1.00 | **1.00** |
| **Impact / Savings** | **-68.7%** | **-67.6%** | **-73.4%** | **2.03× faster** | **-73.7%** | — | — | **Parity** |

---

### Overall Averaged Savings Across All 5 Repositories (1,917 Files Analyzed)

| Metric | Baseline Total | Augmented Total | Aggregate Savings / Delta |
|---|---:|---:|---|
| **Input Tokens** | **927,370 tokens** | **336,205 tokens** | **-63.7% average savings** (591,165 tokens saved) |
| **Output Tokens** | **66,371 tokens** | **17,387 tokens** | **-73.8% average savings** |
| **LLM Turns / Calls** | **183 turns** | **60 turns** | **-67.2% fewer LLM turns** (3× fewer roundtrips) |
| **Wall-Clock Time** | **592.9s (9.9 min)** | **182.9s (3.0 min)** | **3.24× faster execution** (-69.2% latency) |
| **Total API Cost** | **$1.418** | **$0.419** | **-70.5% cost reduction** ($0.999 saved across 5 runs) |
| **Average F1 Accuracy** | **0.53** | **0.82** | **+0.29 F1 score** (drastically reduces hallucinations on large codebases) |

#### Server-Side Latency (OpenTelemetry Spans)

- **Full Workspace Tree-Sitter Indexing**: ~110ms (36 files) → ~1.1s (950 files) → ~2.7s (727 Go files) → ~1.8s (1,718 files).
- **LSH Forest Duplicate Group Clustering**: ~10ms – 200ms across 1,000+ files.
- **AST Diff Summary Calculation**: <0.5ms per file pair.

```
clone_catcher/        server, tokenizer, signatures, diff, telemetry, config
tests/                unit + in-memory MCP + stdio integration + calibration
evals/                fixture repo, ground truth, A/B harness, results (ignored)
tasks/plan.md         design decisions and risk log
```
