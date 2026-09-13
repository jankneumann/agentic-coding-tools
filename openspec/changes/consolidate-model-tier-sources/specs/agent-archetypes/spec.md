## MODIFIED Requirements

### Requirement: Sole Authored Provider Tier Map

The single authored tier→model source SHALL be
`agent-coordinator/archetypes.yaml` under `model_aliases` (bare model id or
`{model, thinking}` per tier). Task/phase → tier SHALL be authored only via
`archetypes` and `phase_mapping` in the same file.

`DEFAULT_PROVIDER_MODEL_MAP` in `agents_config.py` SHALL be an **emergency
fallback only**, used when `archetypes.yaml` cannot be loaded. It SHALL NOT be
a second authored roster operators keep in sync with YAML.

Consumers of the provider tier map (resolution, dispatch, contract tests)
MUST load YAML (directly or via `load_archetypes_config` /
`get_provider_model_map` after a successful load). Tests SHALL derive expected
models and thinking levels from the loaded YAML map, not from Python-map
literals as policy.

The normalized runtime/contract shape remains
`openspec/schemas/provider-model-map.schema.json`.

#### Scenario: YAML is the authored tier map

- **WHEN** an operator changes a provider's `premium` entry in
  `archetypes.yaml::model_aliases` and the coordinator reloads config
- **THEN** `get_provider_model_map()` / `resolve_provider_model_spec` SHALL
  reflect that entry
- **AND** no edit to `DEFAULT_PROVIDER_MODEL_MAP` SHALL be required for the
  change to take effect

#### Scenario: Emergency fallback when YAML unavailable

- **GIVEN** `archetypes.yaml` is missing or unreadable
- **WHEN** provider model resolution runs
- **THEN** the system SHALL use `DEFAULT_PROVIDER_MODEL_MAP` as fallback
- **AND** SHALL emit a structured warning that the emergency map is in use
- **AND** SHALL NOT treat the Python map as an alternate authored source under
  normal operation

#### Scenario: Consumers must load YAML

- **WHEN** a consumer needs tier→model or phase→tier policy
- **THEN** it SHALL obtain values from the loaded YAML-backed map / phase
  mapping (or the coordinator resolve-for-phase endpoint that loads them)
- **AND** it SHALL NOT hardcode a parallel phase→model or tier→model table as
  policy

#### Scenario: Tests do not pin Python-map literals as policy

- **WHEN** contract or resolution tests assert resolved models or thinking
- **THEN** expected values SHALL be derived from the loaded
  `model_aliases` fixture or live YAML
- **AND** tests SHALL NOT require `DEFAULT_PROVIDER_MODEL_MAP` to equal YAML
  as a correctness condition
