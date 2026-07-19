# Spike Report — Retrieval Quality Gate (task 0.2, design D9)

**Change**: `add-semantic-code-search`
**Date**: 2026-07-19
**Environment**: Claude Code cloud harness (ephemeral container, PyPI-only network allowlist)

## Verdict

**BLOCKED (environment)** — the semantic half of the spike cannot execute in this sandbox
because every embedding backend is unreachable. The deterministic ripgrep baseline was measured
(hit@5 = 3/10); the semantic hit@5 could not be measured here. Per design D9 the gate requires an
explicit PASS/FAIL on semantic retrieval quality before any backend work proceeds, so this is a
**non-PASS** and the feature MUST NOT proceed past the gate on this run. Task 0.2 must be re-run in
an environment with a reachable embedder (see "How to complete" below).

This is not a failure of the approach — it is a measurement that could not be taken. It also
directly corroborates the decision memo's core thesis (see "What this tells us" below).

## What ran

| Artifact | Status |
|---|---|
| `eval-set.yaml` — 10 hand-labeled retrieval tasks + ripgrep baselines (task 0.1) | ✅ complete |
| `run_eval.py` — deterministic ripgrep-phrase + fair ripgrep-keyword hit@5 | ✅ complete |
| `baseline-results.json` — machine-readable baseline evidence | ✅ complete |
| `index_and_query.py` — semantic query driver over stock `ccc` | ✅ written, ⛔ not runnable here |
| cocoindex-code semantic hit@5 (task 0.2) | ⛔ **blocked** |

## Baseline result (measured, deterministic)

Over 10 tasks at k=5:

| Strategy | hit@5 | Notes |
|---|---|---|
| ripgrep-phrase (naive literal grep) | **0/10** | Full-query-as-pattern; the first thing an agent tries |
| ripgrep-keyword (fair lexical baseline) | **3/10** | Query tokenized, files ranked by distinct-term coverage then match frequency, top-5 |

Per-task: T2, T8, T9 hit under the keyword baseline; T1, T3, T4, T5, T6, T7, T10 miss. Notably the
two literal-token "control" tasks — T5 (`cross-session` in a docstring) and T7 (`exponential
backoff`) — still miss at k=5, because those terms are diluted across 24–40 files in a ~1000-file
repo. This is the lexical ceiling semantic search must beat.

The gate's PASS bar (design D9 / spec `code-search` "Retrieval Quality Gate"): semantic hit@5 ≥
7/10 **and** ≥ 2 of the passing tasks are ones this keyword baseline misses (the seven
`semantic-win` tasks are the candidates).

## Why the semantic half is blocked

`cocoindex-code`'s embedder is either a local SentenceTransformers model (needs a HuggingFace
download) or a LiteLLM cloud provider (needs an endpoint + API key). Reachability probe (Python
`urllib` through the session proxy):

| Endpoint | Result | Needed for |
|---|---|---|
| `pypi.org` | **HTTP 200** | package install (works) |
| `huggingface.co` | **403 Forbidden (tunnel)** | local model weights |
| `download.pytorch.org` | **403 Forbidden (tunnel)** | CPU-only torch wheels |
| `api.openai.com` | **403 Forbidden (tunnel)** | LiteLLM cloud embeddings |

Embedding API keys present in env (`OPENAI_API_KEY`, `COHERE_API_KEY`, `VOYAGE_API_KEY`,
`HF_TOKEN`): **none**.

Install attempts: `cocoindex-code` and its wheels install fine from PyPI. `pip install
"cocoindex-code[embeddings-local]"` pulls torch; the default PyPI torch drags the full ~6GB CUDA
stack (CPU box), and the CPU-only index (`download.pytorch.org`) is 403-blocked. Even with torch
installed, `SentenceTransformer(model)` would fail at the HuggingFace download step. The LiteLLM
path fails at the provider endpoint. So both embedder options are dead-ends in this specific
environment.

## What this tells us (feeds the design)

The block is evidence *for* the plan, not against it:

- It concretely demonstrates the constraint behind **design D4** (coordinator-side embedding
  against a provisioned backend) and the decision memo's ephemeral-cloud argument: a per-session
  process in a cloud container cannot reach model hosts. The stock cocoindex-code
  per-project-daemon topology would be non-functional in exactly this environment.
- **Infrastructure requirement surfaced**: the fleet needs a *reachable* embedding endpoint. Three
  options for the implementation phase to decide (a follow-up for `wp-coordinator-service` /
  `wp-indexing-infra`):
  1. Network policy allowlists a HuggingFace (or mirror) host so local models download once.
  2. A provisioned cloud embedding key (OpenAI/Voyage/Cohere) + allowlisted provider host.
  3. The embedding model pre-baked into the container image (no runtime download).
- The ripgrep baseline (3/10, with literal-token controls missing) already shows the lexical
  ceiling is low on conceptual queries — the retrieval gap the feature targets is real.

## How to complete the gate (task 0.2, elsewhere)

Run in an environment where one embedder is reachable (local dev machine, or a cloud session whose
network policy allows HuggingFace / an embedding provider):

```bash
# 1. Install (local model, no API key):
uv pip install "cocoindex-code[embeddings-local]"      # CPU box: also allow download.pytorch.org
# 2. Index this repo once:
cd <repo-root> && ccc init --litellm-model <model-or-skip-for-local> && ccc index
# 3. Produce the semantic column and score the gate:
python3 openspec/changes/add-semantic-code-search/eval/index_and_query.py --ccc $(which ccc) \
    --out openspec/changes/add-semantic-code-search/eval/semantic-results.json
python3 openspec/changes/add-semantic-code-search/eval/run_eval.py \
    --semantic openspec/changes/add-semantic-code-search/eval/semantic-results.json
```

The final command prints `GATE (>=7/10 semantic AND >=2 wins): PASS|FAIL`. Replace this Verdict
section with that result and the per-task table, then proceed to `wp-contracts` on PASS or stop
with a written finding on FAIL.

## Recommendation

Hold the gate open. Do not fan out `wp-contracts` and the implementation packages from this
session — the go/no-go signal (semantic hit@5) is unmeasured. Re-run task 0.2 where an embedder is
reachable, or provision one of the three embedding-endpoint options above for the cloud harness so
the gate (and later the indexer job) can run.
