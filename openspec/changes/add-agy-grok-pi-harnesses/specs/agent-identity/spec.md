# agent-identity — delta for add-agy-grok-pi-harnesses

Reworks profile-seeding scenarios that referenced the removed `gemini-cloud` agents.yaml entry.

## MODIFIED Requirements

### Requirement: Profile Seeding from Config

The agents config SHALL optionally seed the `agent_profiles` database table from YAML definitions.

- `seed_profiles_from_config()` SHALL insert or update profiles matching `agents.yaml` entries
- Existing profiles not in `agents.yaml` SHALL NOT be deleted (additive only)
- Seeding SHALL be an explicit action invoked by the setup-coordinator skill, NOT automatic on startup

Because seeding is additive, retiring a harness from `agents.yaml` SHALL NOT delete its previously seeded profile rows. Removal of orphaned profiles SHALL be an explicit operator action.

#### Scenario: Seed creates new profile
- **WHEN** `agents.yaml` defines `grok-local` with `profile: grok_local` and `trust_level: 3`
- **AND** no `grok_local` profile exists in the DB
- **THEN** a new `agent_profiles` row SHALL be inserted with the declared trust level and capabilities

#### Scenario: Seed updates existing profile
- **WHEN** `agents.yaml` declares `trust_level: 3` for a profile that exists with `trust_level: 2`
- **THEN** the DB row SHALL be updated to `trust_level: 3`

#### Scenario: Retired harness profile survives seeding
- **GIVEN** a `gemini_local` profile row exists from a prior seed
- **WHEN** `seed_profiles_from_config()` runs against an `agents.yaml` with no gemini entry
- **THEN** the `gemini_local` row SHALL remain in the table untouched
- **AND** no error SHALL be raised
