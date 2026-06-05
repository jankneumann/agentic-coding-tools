# Plan Findings: harness-engineering-features

## Iteration 1 (2026-06-05)

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 1 | consistency | critical | Contracts reference migration `017` but latest is `025`; next should be `026` | **Fixed** — updated to 026 |
| 2 | consistency | high | Tasks reference wrong convergence_loop.py path (`auto-dev-loop` vs actual `autopilot`) | **Fixed** — path was already correct in tasks.md; confirmed at `skills/autopilot/scripts/` |
| 3 | consistency | high | convergence_loop.py already has checkpoints, max_rounds, stall detection; tasks 3.1-3.4 described building what partially exists | **Fixed** — rewrote WP3 tasks to extend existing infrastructure |
| 4 | feasibility | high | CLAUDE.md grew to 188 lines (plan assumed ~130); 120-line spec max requires extracting ~90 lines | **Fixed** — updated proposal Feature 2 description |
| 5 | consistency | medium | Task 4.3 says "wire into --phase=architecture" but phase already exists with validate_flows | **Fixed** — reworded to "extend existing architecture phase" |
| 6 | consistency | medium | Contracts tag convention table missing `source:` and `prompt_version:` tags from D4/D9 | **Fixed** — added both rows |
| 7 | completeness | medium | PR #195 coordination risk with convergence_loop.py not documented | **Fixed** — added to design.md D1 |
| 8 | consistency | low | work-packages.yaml title doesn't reflect full 9-feature scope | **Fixed** — updated title |
