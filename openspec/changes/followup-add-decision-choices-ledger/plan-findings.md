# Plan Findings: followup-add-decision-choices-ledger

Structured quality findings from `/iterate-on-plan` cycles. Each iteration
appends a dated section. Criticality: critical > high > medium > low.
Threshold for this run: medium.

## Iteration 1 — 2026-09-11T03:20:00Z

Baseline: `openspec validate followup-add-decision-choices-ledger --strict`
passed before this iteration. No critical findings.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | consistency | high | tasks.md cites `skill-workflow.7`, `.8` and "1 through 8". Those ordinals were positions in the parent delta (six scenarios) plus two; this delta holds only two scenarios, so the numbers resolve to nothing in this change and `.1–.6` now live in the canonical spec. | Added a scenario key table to tasks.md mapping every ordinal to its title and location (canonical spec vs this delta); ordinals retained so the parent's dependency graph stays reviewable. |
| 2 | completeness | high | The requirement says validation *and cleanup* gates surface `needs-user` entries and task 3.3 implements the cleanup half, but only the validation gate has a scenario. Orphan task. | Added `needs-user entries surface at the cleanup gate` scenario (skill-workflow.9); task 3.3 now cites it. |
| 3 | clarity | high | "at its human gate" (validate-feature) and "its own gate" (cleanup-feature) name no step. validate-feature has three plausible decision points (7.0 drift prompt, Step 11 report, After Validation); cleanup-feature has four (2, 2.5a, 5b, 6). | design.md F1 pins them: validate-feature Step 11 Phase Results row echoed in After Validation; cleanup-feature new Step 5.5 between open-task migration and archive. Tasks 3.2/3.3 name the steps. |
| 4 | feasibility | high | Task 3.6 "run an end-to-end audit against an archived-change fixture": `run_audit.py` writes the ledger to `openspec/changes/<change-id>/` unconditionally, so auditing an archived id creates a phantom active change directory (choices.json with no proposal.md), and archived changes have no live branch for base-sha resolution. | design.md F5: the fixture is a synthetic git repo (pattern of `test_readonly_posture.fixture_repo`) seeded with the archived parent's proposal/design/session-log as data, plus a canned candidate set. No driver change. |
| 5 | assumptions | high | Ledger commit policy is unstated. Step 11.5 runs after the loop's last commit (Step 10), so `choices.json`/`choices.md` would be left uncommitted; validate-feature and cleanup-feature read the ledger from the branch and archive moves the change dir, so an uncommitted ledger never reaches either gate. | design.md F2: Step 11.5 commits the ledger pair in its own `chore(choices):` commit when the pair changed; idempotent re-audit with no diff commits nothing. Alternatives recorded. |
| 6 | assumptions | high | Step 11.5 mechanics unstated: which base sha, which `run_id`, how the independent auditor sub-agent is dispatched from inside iterate-on-implementation, and what "unavailable" means. | design.md F3/F6: Step 11.5 delegates to `/audit-choices <change-id>` Steps 1–5 (which own range resolution and dispatch); `run_id=iterate-on-implementation-<UTC ISO timestamp>`; "fails" and "unavailable" enumerated; every branch is one WARN line then continue. |
| 7 | assumptions | medium | Presenting choices inside `validation-report.md` risks being parsed by `gate_logic.py`, which reads `## <heading>` sections with a `**Status**` line and would treat a `## Choices` section as a phase. | design.md F4: choices appear only as a `Choices:` row inside the existing Phase Results block, never as a `## Choices` section; the gate parser is untouched, so approve/reject semantics are unchanged by construction. Scenario 8 now asserts the PASS/FAIL result is unaffected. |
| 8 | completeness | medium | No design.md; tasks cite parent decisions D5/D6 that do not resolve inside this change; a change wiring three skills with five open decisions warrants one. | Created design.md: links D5/D6 by reference to the archived parent, records follow-up decisions F1–F7 with alternatives and risks. |
| 9 | completeness | medium | No scenario for a change with no ledger (or a ledger with zero `needs-user` entries) reaching either gate — the common case. | Added `Absent or empty ledger is silent at the gates` scenario (skill-workflow.10). |
| 10 | completeness | medium | Requirement clause "the audit SHALL also be invocable standalone against any change id or commit range" has no scenario (behaviour shipped in Phase 2, but the carried requirement is what becomes canonical). | Added `Standalone invocation against a commit range` scenario (skill-workflow.11), exercised by task 3.6 in the fixture repo. Known quirk (range form writes under `openspec/changes/range:<base>..<head>/`) recorded as out of scope in design.md. |
| 11 | parallelizability | medium | Tasks 3.2 and 3.3 would each inline a "read choices.json, filter `needs-user`, rank, print" snippet in two SKILL.md files — duplicated logic that drifts. No `**Files**` scope lines on any task. | Added task 3.0: read-only `needs_user.py` reader CLI in `skills/audit-choices/scripts/` (exit 0 always, silent when no ledger); 3.2 and 3.3 depend on it. Added `**Files**` to every task. |
| 12 | testability | medium | 3.6 has no pass criterion and a successful audit run cannot exercise scenario 7 (failure path) or scenarios 8–10 (gate presentation). | Split: 3.6 is a pytest end-to-end (fixture repo, canned candidates, forced-failure branch, reader output for 8–11); new 3.7 pins the three SKILL.md hooks with content tests in the style of `skills/tests/cleanup-feature/test_skill_md.py`. |
| 13 | feasibility | medium | Editing canonical skills trips gates beyond pytest: `install.sh --check` (new `<skill-base-dir>` path in SKILL.md), runtime-copy resync, and the `make decisions` freshness gate for 3.5 (README producer change must land with the regenerated `docs/decisions/README.md` in the same commit). | Checkpoints now list the gate set; 3.5 explicitly includes `make decisions` and staging `docs/decisions/`. |
| 14 | scope | low | Whether cleanup-feature should *migrate* open `needs-user` entries into the follow-up proposal (as it does open tasks) is unstated; parent D6/non-goals say no lifecycle machinery. | design.md Non-Goals: surface only, never migrate or block. |
| 15 | security | low | Ledger entry text is auditor output rendered into gate presentations; a gate hook that shell-interpolates it would be an injection surface. | design.md Risks: the reader prints plain text; hooks never `eval` or template entry text into commands. |
| 16 | clarity | low | Scenario 7 "fails or is unavailable" undefined. | Defined in design.md F6 and tightened in the scenario. |

### Parallelizability assessment (after fixes)

- Independent tasks (no shared files, no upstream): 3.0, 3.1, 3.4, 3.5 — 4
- Sequential chains: 3.0 → {3.2, 3.3} → 3.6; {3.1, 3.2, 3.3} → 3.7
- Max parallel width: 4
- File overlap: none. 3.1/3.2/3.3 each edit one distinct SKILL.md; 3.0 and 3.6/3.7 touch `skills/audit-choices/scripts/` and `skills/tests/audit-choices/` respectively; 3.4 and 3.5 are docs/producer only.

### Deferred / out of scope

- `run_audit.py` resolves `change_dir` from the raw id, so the `range:<base>..<head>` standalone form writes under `openspec/changes/range:...`. Latent Phase 2 quirk; not touched here (proposal: no driver change). Recommend a follow-up proposal `fix-audit-choices-range-ledger-path`.
