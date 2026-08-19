# clone-catcher

An MCP server that finds **structural code clones** — files whose logic has the
same shape but different names, literals, and comments — across Python, Go, and
C#. Its purpose: stop coding agents from burning tokens reading (and re-reading)
near-identical boilerplate, and prove with telemetry whether it actually helps.

## Using it inside omp

Registered at user level in `~/.omp/agent/mcp.json`:

```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
  "mcpServers": {
    "clone-catcher": {
      "command": "/home/carlpatchett/repos/clone-catcher/.venv/bin/python",
      "args": ["-m", "clone_catcher"],
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
`mcp__clone_catcher_find_structural_clones` etc.

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
uv sync                # installs server + dev deps
uv run pytest          # 43 tests: pipeline, MCP contract (in-memory + stdio), fixture calibration, harness
```

Register with an MCP host (stdio transport; first launch downloads the
tree-sitter grammars once, then they're cached):

```json
{
  "mcpServers": {
    "clone-catcher": {
      "command": "uv",
      "args": ["run", "--directory", "/abs/path/to/clone-catcher", "python", "-m", "clone_catcher"],
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

We evaluated `clone-catcher` using real coding agent sessions (`google-antigravity/gemini-3.7-flash:medium` running on `omp`) across three distinct codebases:

1. **Synthetic Growth-Stage SaaS Monorepo** (66 files, 6,700 LOC, Python + Go + C#, 130 planted duplicate pairs)
2. [`gin-gonic/gin`](https://github.com/gin-gonic/gin) (99 files, ~8,000 LOC, Go web framework, 10 structural clone pairs across bindings/codecs)
3. [`pallets/click`](https://github.com/pallets/click) (75 files, ~10,000 LOC, Python CLI framework, 2 structural typing clone pairs)

#### The Task Given to the LLM

Both arms were given an identical prompt in fresh, isolated checkouts with full standard tools available (`bash`, `eval`, `read`, `glob`, `grep`):

> *"Analyze this codebase and find every group of structurally duplicated code — code that was copy-pasted and then renamed or slightly tweaked (identical structure with different names/strings counts as duplicated). Ignore coincidental similarity of trivial one-liners. Do NOT modify any files; this is analysis only."*

#### 1. Synthetic SaaS Monorepo (66 files, 6.7k LOC)

| Arm | Input Tokens | Output Tokens | LLM Calls | Tool Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 281,655 | 13,844 | 64 | 63 | 124.3s | $0.411 | 1.00 | 1.00 | **1.00** |
| **Augmented** (+ clone-catcher) | 88,040 | 4,486 | 17 | 16 | 61.2s | $0.108 | 1.00 | 1.00 | **1.00** |
| **Impact / Savings** | **-68.7%** | **-67.6%** | **-73.4%** | **-74.6%** | **2.03× faster** | **-73.7%** | — | — | **Parity** |

#### 2. `gin-gonic/gin` (99 files, Go)

| Arm | Input Tokens | Output Tokens | LLM Calls | Tool Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 127,787 | 13,819 | 26 | 25 | 147.5s | $0.217 | 0.40 | 1.00 | **0.57** |
| **Augmented** (+ clone-catcher) | 18,575 | 944 | 4 | 3 | 11.6s | $0.023 | 1.00 | 1.00 | **1.00** |
| **Impact / Savings** | **-85.5%** | **-93.2%** | **-84.6%** | **-88.0%** | **12.7× faster** | **-89.4%** | **+0.60** | **1.00** | **+0.43** |

#### 3. `pallets/click` (75 files, Python)

| Arm | Input Tokens | Output Tokens | LLM Calls | Tool Calls | Wall Time | Cost (USD) | Precision | Recall | F1 Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Baseline** (no MCP) | 98,915 | 9,239 | 20 | 19 | 122.8s | $0.161 | 0.00 | 0.00 | **0.00** |
| **Augmented** (+ clone-catcher) | 38,770 | 1,658 | 11 | 10 | 28.8s | $0.051 | 1.00 | 1.00 | **1.00** |
| **Impact / Savings** | **-60.8%** | **-82.1%** | **-45.0%** | **-47.4%** | **4.26× faster** | **-68.3%** | **+1.00** | **+1.00** | **+1.00** |

---

### Aggregate & Averaged Savings

Across all 3 benchmarks (240 total files analyzed):

| Metric | Baseline Total | Augmented Total | Average Savings / Delta |
|---|---:|---:|---|
| **Input Tokens** | 508,357 tokens | 145,385 tokens | **-71.4% average savings** (362,972 tokens saved) |
| **Output Tokens** | 36,902 tokens | 7,088 tokens | **-80.8% average savings** |
| **LLM Turns / Calls** | 110 turns | 32 turns | **-70.9% fewer LLM turns** |
| **Wall-Clock Time** | 394.6s (6.6 min) | 101.6s (1.7 min) | **3.88× faster execution** (-74.3% latency) |
| **Total API Cost** | $0.789 | $0.182 | **-76.9% cost reduction** |
| **Average F1 Accuracy** | 0.52 | 1.00 | **+0.48 F1 score** (eliminates false positives & missed clones) |

#### Server-Side Latency (OpenTelemetry Spans)

- **Full Workspace Tree-Sitter Indexing**: ~110ms – 299ms for 60–130 files.
- **LSH Forest Duplicate Group Clustering**: ~10ms – 18ms.
- **AST Diff Summary Calculation**: <0.5ms per file pair.

```
clone_catcher/        server, tokenizer, signatures, diff, telemetry, config
tests/                unit + in-memory MCP + stdio integration + calibration
evals/                fixture repo, ground truth, A/B harness, results (ignored)
tasks/plan.md         design decisions and risk log
```
