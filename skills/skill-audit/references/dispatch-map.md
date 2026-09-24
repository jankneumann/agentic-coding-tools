# Dispatch map: which phases and archetypes run each lifecycle skill

`scripts/dispatch_profile.py` reads this table at run time; it is the only
place the skill → phase mapping is written. Phases are keys of
`phase_mapping` in `agent-coordinator/archetypes.yaml`, which supplies the
archetype for each phase; `*` means every phase in that mapping. "Direct
archetypes" are archetypes a skill dispatches outside the phase machinery,
seeded from the `agent-archetypes` spec table "Skill Model Hint Integration".
Phases unknown to the roster are ignored, so this table can name phases a
roster has not adopted yet.

Skills absent from this table are not lifecycle skills: their archetypes are
read from `archetype=`/`archetype:` and `model=<archetype>_model` tokens in the
`Task(` / `Agent(` examples of their own `SKILL.md`. A skill with neither has an
empty dispatch profile and the report says so.

| Skill | Phases | Direct archetypes |
|---|---|---|
| autopilot | * | — |
| autopilot-roadmap | * | supervisor |
| supervise | — | supervisor |
| plan-feature | PLAN, PLAN_ITERATE | analyst |
| iterate-on-plan | PLAN_ITERATE, PLAN_FIX | analyst |
| parallel-review-plan | PLAN_REVIEW | — |
| implement-feature | IMPLEMENT, IMPL_ITERATE, IMPL_FIX | runner |
| iterate-on-implementation | IMPL_ITERATE, IMPL_FIX | runner |
| parallel-review-implementation | IMPL_REVIEW | — |
| validate-feature | VALIDATE, VAL_FIX | — |
| fix-scrub | — | implementer |
| prototype-feature | IMPLEMENT | — |
| cleanup-feature | SUBMIT_PR | — |
| session-bootstrap | INIT | — |

Tier resolution for every `(archetype, provider)` pair goes through
`skills/shared/archetype_roster.resolve_tier_for_provider`, so `{model,
thinking}` entries and the `frontier → premium` fallback behave exactly as
dispatch does. A provider that lacks the tier altogether (for example `local`
has no `premium`) gets no row for that archetype.
