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

### Results

First live result (gemini-3.7-flash, 16-file fixture): both arms found all 7
truth pairs (P/R/F1 = 1.00), but the augmented arm cost **more** — 108k vs 61k
input tokens, 24 vs 11 LLM calls, $0.138 vs $0.083 — because the model issued
17 per-file `find_structural_clones` calls and still read every file.

Second live result (gemini-3.7-flash, 66-file "large" fixture): [Pending...]
come from omp's own per-call usage telemetry; tool calls from the event
stream; server latency from the OTel spans.

```bash
uv run python evals/omp_eval.py --model google-antigravity/gemini-3.7-flash:medium
```

First live result (gemini-3.7-flash, 16-file fixture, kept in
`evals/results/omp_report_*.md`): both arms found all 7 truth pairs (P/R/F1 =
1.00), but the augmented arm cost **more** — 108k vs 61k input tokens, 24 vs
11 LLM calls, $0.138 vs $0.083 — because the model issued 17 per-file
`find_structural_clones` calls and still read every file. Honest conclusion:
on a small fixture where reading everything is cheap, the tool adds context
rather than replacing reads. The mechanism it needs to prove itself is a
larger fixture with heavyweight files, and likely a one-shot
"all duplicate groups" tool instead of per-file queries.

## Repository layout

```
clone_catcher/        server, tokenizer, signatures, diff, telemetry, config
tests/                unit + in-memory MCP + stdio integration + calibration
evals/                fixture repo, ground truth, A/B harness, results (ignored)
tasks/plan.md         design decisions and risk log
```
