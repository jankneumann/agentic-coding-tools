# Skill Flow

How the skills in this repo fit together, including the artifacts each one consumes
and produces. This is the visual companion to the prose in
[`skills-workflow.md`](../skills-workflow.md) and the index in
[`skills-catalogue.md`](../skills-catalogue.md).

The diagrams below are [Mermaid](https://mermaid.js.org/) — they render inline on
GitHub and stay diff-able as the workflow evolves. Three coordinated views:

1. [Single-feature lifecycle](#1-single-feature-lifecycle) — the canonical
   `explore → plan → implement → validate → cleanup` flow, with human gates,
   refinement loops, and artifacts.
2. [Roadmap orchestration](#2-roadmap-orchestration) — how `plan-roadmap` /
   `autopilot` wrap the lifecycle for multi-change initiatives.
3. [Supporting-skill map](#3-supporting-skill-map) — quality, methodology,
   vendor, and infrastructure skills that hang off the lifecycle.

## Legend

| Shape / colour | Meaning |
|---|---|
| 🟧 Orange box | A **skill** (slash command an operator or orchestrator invokes) |
| 🟥 Pink box | A **human approval gate** — work stops here until a person approves |
| ⬜ Dashed box | An **artifact** produced or consumed (file on disk, branch, PR) |
| 🔶 Red diamond | A **decision / retry loop** (mirrors the "Max N times" loops in the setup) |
| 🟦 Grey box | A **git/process state** (new branch, PR, merge) |

---

## 1. Single-feature lifecycle

The core flow. Every skill ends at a natural handoff point where a human reviews
and approves before the next stage begins. Optional refinement and review skills
loop back into their stage before the gate.

```mermaid
flowchart TD
    classDef human fill:#ffd5d5,stroke:#c0392b,stroke-width:2px,color:#000
    classDef skill fill:#ffd9a8,stroke:#e67e22,stroke-width:2px,color:#000
    classDef artifact fill:#ffffff,stroke:#c0392b,stroke-width:1.3px,stroke-dasharray:4 3,color:#000
    classDef process fill:#c7c9d9,stroke:#5d6d7e,stroke-width:2px,color:#000
    classDef decision fill:#e74c3c,stroke:#922b21,color:#fff

    %% ---------- Discovery ----------
    explore["/explore-feature<br/>(optional)"]:::skill
    refresh["/refresh-architecture<br/>(optional)"]:::skill
    a_disc["opportunities.json<br/>history.json<br/>architecture-analysis/*"]:::artifact
    explore --> a_disc
    refresh --> a_disc

    %% ---------- Plan ----------
    plan["/plan-feature"]:::skill
    a_disc --> plan
    a_plan["openspec/changes/&lt;id&gt;/<br/>proposal.md · design.md<br/>specs/ · tasks.md<br/>contracts · work-packages"]:::artifact
    plan --> a_plan

    refinePlan["/iterate-on-plan<br/>/parallel-review-plan<br/>/prototype-feature<br/>(optional)"]:::skill
    a_plan --> refinePlan
    refinePlan -->|plan-findings.md<br/>prototype-findings.md| a_plan

    gatePlan["HUMAN: approve proposal"]:::human
    a_plan --> gatePlan

    %% ---------- Implement ----------
    branch["new branch openspec/&lt;id&gt;<br/>+ worktree"]:::process
    gatePlan --> branch
    implement["/implement-feature"]:::skill
    branch --> implement
    a_impl["change-context.md (RTM)<br/>code + passing tests<br/>updated tasks.md"]:::artifact
    implement --> a_impl

    refineImpl["/iterate-on-implementation<br/>/parallel-review-implementation<br/>(optional)"]:::skill
    a_impl --> refineImpl
    refineImpl -->|impl-findings.md| a_impl

    pr["open PR"]:::process
    a_impl --> pr
    gateImpl["HUMAN: review PR"]:::human
    pr --> gateImpl

    %% ---------- Validate ----------
    validate["/validate-feature<br/>(deploy · smoke · security<br/>· e2e · spec · logs)"]:::skill
    gateImpl --> validate
    security["/security-review<br/>(standalone, optional)"]:::skill
    a_val["validation-report.md<br/>architecture-impact.md<br/>docs/security-review/*"]:::artifact
    validate --> a_val
    security --> a_val

    decVal{"Findings to<br/>address?"}:::decision
    a_val --> decVal
    decVal -->|Yes| refineImpl
    gateVal["HUMAN: accept results"]:::human
    decVal -->|No| gateVal

    %% ---------- Cleanup ----------
    cleanup["/cleanup-feature"]:::skill
    gateVal --> cleanup
    updateSpecs["/update-specs<br/>(if drift found)"]:::skill
    cleanup --> updateSpecs
    merge["merge PR<br/>(rebase: agent PRs ·<br/>squash: deps/automation)"]:::process
    cleanup --> merge
    a_done["openspec/changes/archive/&lt;id&gt;/<br/>updated openspec/specs/<br/>deferred-tasks.md"]:::artifact
    merge --> a_done
    updateSpecs --> a_done
```

### What flows where

| Stage | Skill(s) | Consumes | Produces | Gate |
|---|---|---|---|---|
| Discovery | `explore-feature`, `refresh-architecture` | specs, active changes, code signals | `opportunities.json`, `history.json`, `architecture-analysis/*` | none |
| Plan | `plan-feature` (+ `iterate-on-plan`, `parallel-review-plan`, `prototype-feature`) | discovery context, existing specs | `proposal.md`, `design.md`, `specs/`, `tasks.md`, contracts, work-packages, `plan-findings.md` | **approve proposal** |
| Implement | `implement-feature` (+ `iterate-on-implementation`, `parallel-review-implementation`) | approved proposal/spec/tasks | branch `openspec/<id>`, `change-context.md`, tests, PR, `impl-findings.md` | **review PR** |
| Validate | `validate-feature`, `security-review` | running system, spec scenarios, changed files | `validation-report.md`, `architecture-impact.md`, `docs/security-review/*` | **accept results** |
| Cleanup | `cleanup-feature`, `update-specs` | approved PR, `tasks.md` completion | archived change, updated `openspec/specs/`, merged PR | none (mechanical) |

---

## 2. Roadmap orchestration

For long-form proposals describing 3+ capabilities, the roadmap layer **wraps**
the single-feature lifecycle: it decomposes the proposal into a dependency DAG of
OpenSpec changes, then drives each one through the lifecycle above with learning
feedback between items. `autopilot` does the same for a single change end-to-end.

```mermaid
flowchart TD
    classDef human fill:#ffd5d5,stroke:#c0392b,stroke-width:2px,color:#000
    classDef skill fill:#ffd9a8,stroke:#e67e22,stroke-width:2px,color:#000
    classDef artifact fill:#ffffff,stroke:#c0392b,stroke-width:1.3px,stroke-dasharray:4 3,color:#000
    classDef decision fill:#e74c3c,stroke:#922b21,color:#fff

    proposal["long-form proposal<br/>(Claude/ChatGPT/Perplexity)"]:::artifact
    planRoadmap["/plan-roadmap"]:::skill
    proposal --> planRoadmap
    prioritize["/prioritize-proposals<br/>(optional)"]:::skill
    prioritize --> planRoadmap

    roadmapYaml["roadmap.yaml + child<br/>OpenSpec changes (DAG)"]:::artifact
    planRoadmap --> roadmapYaml
    gateRoadmap["HUMAN: approve candidates"]:::human
    roadmapYaml --> gateRoadmap

    autopilotR["/autopilot-roadmap"]:::skill
    gateRoadmap --> autopilotR

    subgraph LC["per ready item — single-feature lifecycle (view 1)"]
        lifecycle["/plan-feature → /implement-feature<br/>→ /iterate-on-implementation<br/>→ /validate-feature → /cleanup-feature"]:::skill
    end
    autopilotR --> LC

    learning["learnings/&lt;item-id&gt;.md<br/>checkpoint.json"]:::artifact
    LC --> learning
    decMore{"More items?<br/>(deps-aware,<br/>priority order)"}:::decision
    learning --> decMore
    decMore -->|Yes, replan + ingest learnings| autopilotR
    decMore -->|No| doneRoadmap["roadmap complete"]:::artifact

    autopilot["/autopilot<br/>(single change, full lifecycle<br/>with multi-vendor review)"]:::skill
    autopilot -.same lifecycle, one item.-> LC
```

---

## 3. Supporting-skill map

Skills that aren't stages of the lifecycle but plug into it — grouped by purpose
(matching [`skills-catalogue.md`](../skills-catalogue.md)). Quality skills keep the
codebase healthy, methodology skills encode disciplines that orchestrators auto-load,
vendor skills are authority docs for external services, and infrastructure skills are
the machinery the workflow skills call.

```mermaid
flowchart LR
    classDef skill fill:#ffd9a8,stroke:#e67e22,stroke-width:2px,color:#000
    classDef infra fill:#d5e8f0,stroke:#2980b9,stroke-width:1.5px,color:#000

    subgraph QM["Quality & maintenance"]
        bug["/bug-scrub"]:::skill --> fix["/fix-scrub"]:::skill
        simplify["/simplify"]:::skill
        techdebt["/tech-debt-analysis"]:::skill
        changelog["/changelog-version"]:::skill
    end

    subgraph METH["Engineering methodology (orchestrators auto-load)"]
        tdd["/test-driven-development"]:::skill
        dbg["/debugging-and-error-recovery"]:::skill
        perf["/performance-optimization"]:::skill
        feui["/frontend-ui-engineering"]:::skill
        api["/api-and-interface-design"]:::skill
        deprec["/deprecation-and-migration"]:::skill
        adr["/documentation-and-adrs"]:::skill
    end

    subgraph PR["PR triage & ad-hoc"]
        mergeprs["/merge-pull-requests"]:::skill
        quick["/quick-task"]:::skill
        gen["/gen-eval"]:::skill
        genSc["/gen-eval-scenario"]:::skill
    end

    subgraph VEND["Vendor & service authority docs"]
        neon["/neon-postgres"]:::skill
        claim["/claimable-postgres"]:::skill
        supa["/supabase-postgres-best-practices"]:::skill
        lang["/langfuse"]:::skill
        rail["/use-railway"]:::skill
    end

    subgraph INFRA["Infrastructure (orchestrator-loaded)"]
        worktree["worktree"]:::infra
        bridge["coordination-bridge"]:::infra
        parinf["parallel-infrastructure"]:::infra
        rdrun["roadmap-runtime"]:::infra
        valpkg["validate-packages"]:::infra
        valflows["validate-flows"]:::infra
        ctxeng["context-engineering"]:::infra
        srcdd["source-driven-development"]:::infra
        browser["browser-testing-with-devtools"]:::infra
        setupc["/setup-coordinator"]:::skill
        vstatus["/vendor-status"]:::skill
    end
```

**How these connect to the lifecycle:**

- `bug-scrub` → `fix-scrub` is a diagnose/remediate pair you run any time, independent of a change.
- Methodology skills are loaded *by* `implement-feature` / `iterate-on-implementation` when the work touches their domain (e.g. `test-driven-development` shapes the RED→GREEN task ordering; `source-driven-development` and `context-engineering` are loaded automatically by the orchestrator skills).
- `merge-pull-requests` is the multi-source merge gate (it, `update-specs`, and `cleanup-feature` are the **sync-point skills** that touch `main` directly).
- Vendor skills are referenced by `source-driven-development` as primary sources when implementation code touches those services.
- Infrastructure skills (`worktree`, `parallel-infrastructure`, `coordination-bridge`, `roadmap-runtime`) provide isolation, DAG scheduling, coordinator transport, and roadmap state to the workflow skills above.

---

## Editing these diagrams

Edit the Mermaid code blocks in this file directly — GitHub re-renders on push. To
preview locally, paste a block into the [Mermaid Live Editor](https://mermaid.live)
or use any Markdown previewer with Mermaid support. Keep the four `classDef` styles
consistent across views so the colour grammar in the legend holds.
