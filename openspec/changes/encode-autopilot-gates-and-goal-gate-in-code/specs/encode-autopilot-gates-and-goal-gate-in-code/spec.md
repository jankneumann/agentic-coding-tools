## ADDED Requirements

### Requirement: Encode autopilot gates and goal gate in code

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-06` and is refined by
`/plan-feature` before implementation.

#### Scenario: Grep of skills/autopilot/SKILL.md finds no gate whose only…

- **WHEN** the roadmap item is implemented
- **THEN** Grep of skills/autopilot/SKILL.md finds no gate whose only enforcement is prose

#### Scenario: An unattended run with an auto-everything posture reaches SUBMIT_PR…

- **WHEN** the roadmap item is implemented
- **THEN** An unattended run with an auto-everything posture reaches SUBMIT_PR without interaction; with the default posture it parks exactly where it does today

#### Scenario: A run whose VALIDATE record is missing or failed cannot reach DONE

- **WHEN** the roadmap item is implemented
- **THEN** A run whose VALIDATE record is missing or failed cannot reach DONE

#### Scenario: replan_required re-invokes /plan-roadmap in replan mode when the…

- **WHEN** the roadmap item is implemented
- **THEN** replan_required re-invokes /plan-roadmap in replan mode when the posture allows
