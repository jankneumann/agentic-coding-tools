# Evaluation: Magnitude as a Local-Model Agent Harness for the GX10

**Status**: Draft evaluation
**Created**: 2026-08-08
**Subject**: [magnitudedev/magnitude](https://github.com/magnitudedev/magnitude) (Apache-2.0)
**Target context**: local-model execution tiers on the ASUS Ascent GX10 always-on host
(see `docs/proposals/always-on-agent-automation.md`)

## Verdict (TL;DR)

Magnitude is worth tracking but is **not yet integrable as a dispatch provider**, and its
inference engine is **unproven on the GX10's hardware**. Two findings drive this:

1. **No documented headless mode.** The CLI is an interactive OpenTUI terminal client;
   nothing equivalent to `claude -p` / `codex exec` is documented. Our per-phase dispatch
   (`skills/autopilot/scripts/provider_dispatch.py`) requires non-interactive invocation.
   A programmatic path exists in principle — the CLI talks to an `acn` daemon over typed
   RPC via `@magnitudedev/sdk` — but using it means writing and maintaining a TypeScript
   adapter against an SDK with no published API docs and 161 stars' worth of stability.
2. **CUDA support is undocumented.** The inference engine ("ICN", Rust on a pinned
   llama.cpp bindings fork) documents only the macOS **Metal** backend, with
   `--gpu-layers 0` CPU fallback. The GX10 is an ARM64 NVIDIA GB10 (Grace Blackwell)
   box whose entire value is its CUDA GPU and 128 GB unified memory. Until magnitude's
   bindings enable CUDA on Linux/aarch64, its differentiators (hardware auto-profiling,
   memory-aware model loading/switching) don't reach our target machine's GPU.

The immediately useful takeaway is architectural, not product: magnitude validates the
pattern of a **local OpenAI-compatible inference server + tiered model presets**, which
this repo can adopt today with mature servers (llama.cpp `llama-server`, vLLM, or Ollama
— all CUDA-proven on GB10-class hardware) behind the existing `pi`-style
OpenAI-compatible provider path. Magnitude then becomes a candidate *replacement* for
that serving layer once CUDA lands, and a candidate *provider* once headless invocation
exists.

## What Magnitude Is

An open-source local-first agent ("100% private and offline") with its own inference
stack. Monorepo (TypeScript/Bun/Turbo + Rust), ~293 commits, active development.

Components, per the repo's `AGENTS.md` and `inference/README.md`:

- **ACN daemon** — hosts the agent runtime (event-sourced sessions, tools, file ops,
  command execution). Clients (CLI, web, desktop) connect over typed RPC
  (`clients → client-common → sdk → acn`).
- **CLI** — `npm install -g @magnitudedev/cli; magnitude`. React/OpenTUI interactive
  client. macOS and Linux; Windows via WSL.
- **ICN inference engine** — Rust workspace on a pinned llama.cpp bindings fork. Loads
  GGUF models, exposes an **OpenAI-compatible HTTP server** (default `:8080`) with
  streaming and per-token timings. Metal on Apple Silicon; CPU otherwise (documented).
- **Model management** — profiles the host and offers preset tiers (Balanced,
  Best Quality, Fastest, Lightweight); "calculates memory requirements before loading";
  manages download, load, and model switching.
- **Skills** — installable via `npx skills add`, sourced from the skills.sh directory
  (same Claude-style agent-skills convention this repo already uses).
- **Provider abstraction** — `Provider` / `ModelCatalog` / `BoundModel` registry in
  `packages/ai` + `packages/providers`, so the agent is not hard-wired to ICN.

## Fit Against This Repo's Dispatch Stack

Two distinct integration surfaces exist here, and magnitude maps to them differently.

### Path A — magnitude as a dispatch provider (not viable yet)

Providers are enumerated in `provider_dispatch.py` (`_SUPPORTED_PROVIDERS`) and given
tier rosters in `agent-coordinator/archetypes.yaml` (`model_aliases`), with per-phase
archetype resolution served by `POST /archetypes/resolve_for_phase`. Every existing
provider (claude_code, codex, antigravity, grok, pi) is dispatched through a
**non-interactive CLI surface**. Magnitude has no documented equivalent; adding it means
either (a) waiting for a headless CLI mode, or (b) building a Node adapter against
`@magnitudedev/sdk` RPC — feasible but an ongoing maintenance liability against an
undocumented, fast-moving API. Recommendation: wait for (a).

### Path B — local models behind an OpenAI-compatible endpoint (viable now, without magnitude)

The `pi` provider already demonstrates the shape: OpenAI-compatible `publisher/model`
slugs resolved per tier. A `local` provider entry pointing at a GX10-hosted
OpenAI-compatible server is the same pattern with a different base URL. Magnitude's ICN
*could* be that server — but today llama.cpp's own `llama-server`, vLLM, or Ollama do
the same job with documented CUDA on Linux/aarch64. Magnitude's value-add over these
(auto-profiling, preset tiers, memory-aware switching) is exactly the part that is
Metal-only today.

### Which operations suit local models

The archetype system already encodes the answer to "select operations well suited to
local models": tiers are tuned for cost per successful task, and the low tiers carry
work where frontier capability is wasted. Candidate archetypes for a local tier on the
GX10, in order of increasing risk:

| Archetype | Phase(s) | Why local fits |
|---|---|---|
| `runner` (economy) | INIT, SUBMIT_PR | Execute-and-report; near-zero reasoning demand. |
| `analyst` (standard, read-only) | discovery/analysis fan-outs | Read-heavy synthesis; wrong answers are cheap because output is advisory. |
| `documenter` (standard) | doc-sync phases | Templated writing against existing conventions; reviewed downstream. |
| `validator` (standard) | VALIDATE | Structured evidence collection; the pipeline itself does the judging. |

`architect`, `reviewer`, and `gatekeeper` phases should stay on frontier/premium cloud
models — that division is the same one the always-on proposal draws for unattended
operation, and it is also where local-model failure would be silent rather than caught
by a downstream gate. A useful additional property of local tiers for the always-on
host: they are immune to the usage-limit wait/switch policy engine's main failure mode
(provider rate limits), making them natural fallback targets for the `runner`-class
phases when cloud vendors throttle.

## GX10 Hardware Fit

The GX10 (NVIDIA GB10 Grace Blackwell, 20-core ARM64, 128 GB unified LPDDR5x, ~1 PFLOP
FP4, DGX OS Linux) comfortably serves 30–70B-class GGUF/AWQ models — the
qwen3-coder / GLM / gpt-oss class that the low archetype tiers need. The constraint on
this machine is *serving-stack maturity on Linux/aarch64 + CUDA*, which is precisely
magnitude's documentation gap and precisely where llama.cpp/vLLM/Ollama are proven.
Magnitude's Node/Bun CLI layer runs fine on DGX OS; that was never the risk.

## Recommendation

1. **Do not integrate magnitude now.** Neither dispatch path is ready: no headless CLI,
   no documented CUDA.
2. **If/when a local tier is wanted on the GX10** (a natural Phase-2+ companion to the
   always-on proposal), implement Path B with a mature server: add a `local` provider to
   `_SUPPORTED_PROVIDERS` and an `archetypes.yaml` roster mapping economy/standard tiers
   to GX10-hosted models, routed to `runner`/`analyst`/`documenter`/`validator`
   archetypes first. This is a small, magnitude-independent change that captures the
   entire near-term value the user identified.
3. **Re-evaluate magnitude on two triggers**, either of which changes the verdict:
   - a documented non-interactive/headless CLI mode (enables Path A: magnitude as a
     sixth provider with its own tier roster);
   - documented CUDA/Linux GPU support in the ICN bindings (makes its auto-profiling and
     model-switching engine a candidate serving layer for Path B, replacing hand-tuned
     llama.cpp flags).
4. **Track its skills-directory compatibility.** Magnitude consumes skills.sh-style
   skills — the same convention as `skills/` here — so if Path A ever opens, this repo's
   skill corpus is plausibly reusable inside magnitude sessions with little translation.

## Open Questions

- Does the ACN daemon accept connections from non-magnitude RPC clients stably enough to
  script (undocumented today)?
- What is ICN's real throughput/quality on CPU-only Linux? (Irrelevant for GX10 GPU use,
  but would bound a stopgap deployment.)
- Does magnitude's agent runtime expose tool-permission controls comparable to what the
  coordinator's guardrails/trust-posture work assumes? Unattended dispatch to any new
  provider needs an answer before it joins the always-on loop.

## Sources

- https://github.com/magnitudedev/magnitude (README, repo structure)
- `AGENTS.md` (repo root and `cli/`) — architecture: clients → client-common → sdk → acn
- `inference/README.md` — ICN workspace layout, OpenAI-compatible server on `:8080`,
  GGUF loading, Metal-only acceleration note, `bun icn:serve` usage
- Fetched 2026-08-08; docs.magnitude.dev unreachable from this environment (egress
  policy), so claims rest on the repository itself.
