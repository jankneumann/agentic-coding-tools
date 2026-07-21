## MODIFIED Requirements

### Requirement: Cross-Repo Portability

Every skill selected by `skills/install.sh` SHALL function from the installed consumer layout without access to the `agentic-coding-tools` source checkout. The runtime dependency closure MAY include installed skill directories, installed `shared/`, installed `references/`, installed OpenSpec assets, declared third-party dependencies, and consumer-owned project files explicitly documented by the skill. It MUST NOT require a canonical repo-root `skills/` or `scripts/` tree, `agent-coordinator/`, or source-repository `docs/` files.

#### Scenario: Complete install runs without source checkout
- **WHEN** `skills/install.sh` rsyncs the complete payload into a fresh consumer repository
- **AND** the consumer has no canonical `skills/`, repo-root `scripts/`, `agent-coordinator/`, or source-repository `docs/`
- **THEN** every installed runtime entry point SHALL import or execute successfully through its documented smoke invocation
- **AND** optional external services SHALL fail or degrade through their documented public boundary rather than a missing source-tree import

#### Scenario: Missing runtime dependency blocks installation validation
- **WHEN** an installed entry point references a source-repository file that is absent from the declared payload
- **THEN** the portability gate SHALL fail
- **AND** identify both the referring source file and the missing installed target

### Requirement: Skill Script Path Resolution Convention

All runtime commands and cross-skill references SHALL resolve from the actual loaded skill directory. Sibling dependencies SHALL use `<skill-base-dir>/../<skill-name>/...` or an equivalent helper derived from `__file__`; canonical repo-root `skills/...` paths MUST NOT be used as runtime resolution. A bare `scripts/...` path MUST be explicitly documented as consumer-project-relative or rewritten as skill-relative.

#### Scenario: Claude and agents mirrors resolve the same sibling
- **WHEN** the same skill is installed under `.claude/skills/<name>` and `.agents/skills/<name>`
- **THEN** both copies SHALL resolve a sibling skill or shared library within their own installed skills directory
- **AND** neither copy SHALL traverse to `.claude/agent-coordinator`, `.agents/agent-coordinator`, or `<consumer>/skills`

#### Scenario: Runtime command uses a canonical source path
- **WHEN** a shipped `SKILL.md`, hook, or script constructs a runtime command beginning with repo-root `skills/`
- **THEN** static portability validation SHALL fail unless the reference is explicitly marked as source-contribution-only
- **AND** the diagnostic SHALL recommend the installed-skill-relative form

## ADDED Requirements

### Requirement: Install Payload Dependency Closure

The install payload SHALL be closed over runtime code and documentation references. Validation MUST inspect direct imports, computed `sys.path` additions, fixed `parents[N]` traversal, subprocess import strings, shell commands, hook commands, and local Markdown links.

#### Scenario: Coordinator internals are referenced directly
- **WHEN** a shipped Python file imports `src.*`, adds `agent-coordinator` to `sys.path`, or executes a subprocess importing coordinator internals
- **THEN** dependency-direction validation SHALL fail
- **AND** require use of an installed helper or the public HTTP/MCP coordination boundary

#### Scenario: Optional coordinator integration is unavailable
- **WHEN** a consumer runs a skill without a local coordinator source checkout
- **THEN** the skill SHALL use HTTP, MCP, or `coordination-bridge` when coordinator behavior is requested
- **AND** documented optional behavior SHALL degrade cleanly when those public interfaces are unavailable

### Requirement: Consumer-Layout Regression Gate

CI SHALL install the complete distribution into an isolated temporary consumer and run blocking portability probes over the installed output. The probes SHALL include `merge-pull-requests/scripts/discover_prs.py`, `parallel-infrastructure/scripts/result_validator.py`, and `autopilot/scripts/smoke_provider_dispatch.py`, and SHALL scan the complete payload rather than only changed files.

#### Scenario: Known regression entry points are portable
- **WHEN** the clean-consumer regression test runs after installation
- **THEN** the three known regression entry points SHALL import or return help successfully without `agent-coordinator/src`
- **AND** PR classification behavior SHALL remain consistent between skill and coordinator consumers

#### Scenario: A future unchanged-file violation exists
- **WHEN** a non-portable reference exists in a shipped file not touched by the current commit
- **THEN** the full-payload gate SHALL still detect and report it
- **AND** CI SHALL fail until the dependency is shipped, replaced, documented as consumer-owned, or excluded from distribution

### Requirement: Install Manifest Completeness

`install.sh` SHALL expose or derive a deterministic manifest containing selected skills, shared libraries, reference libraries, and installed OpenSpec assets. Every shipped runtime reference SHALL resolve within that manifest or to a declared external/consumer-owned prerequisite.

#### Scenario: Distributable skill has complete closure
- **WHEN** a skill is selected for consumer installation
- **THEN** its scripts, local references, cross-skill dependencies, and required shared helpers SHALL be present after sync
- **AND** manifest validation SHALL pass before installation is considered successful

#### Scenario: Skill is intentionally repository-scoped
- **WHEN** a skill cannot provide meaningful behavior outside the source repository
- **THEN** it SHALL be explicitly marked non-distributable with a tested rationale
- **AND** `install.sh` SHALL omit it rather than installing a broken runtime copy

### Requirement: Portable Configuration Discovery

Shipped skills SHALL prefer explicit paths, environment variables, and public HTTP/MCP configuration over source-repository defaults. Local `agent-coordinator/agents.yaml`, `.secrets.yaml`, `.venv`, compose files, and Makefile targets MAY be optional compatibility fallbacks but MUST NOT be required for import, help output, or documented baseline behavior.

#### Scenario: Explicit consumer configuration is provided
- **WHEN** a consumer provides `AGENTS_YAML`, an explicit compose file, secrets path, or public coordinator endpoint
- **THEN** the skill SHALL use that configuration without searching for a bundled coordinator source tree
- **AND** its entry point SHALL remain importable before the configured external resource is contacted

#### Scenario: Source-repository fallback is absent
- **WHEN** no explicit configuration and no source-repository fallback exists
- **THEN** the skill SHALL emit an actionable missing-configuration diagnostic or disable only the optional feature
- **AND** SHALL NOT fail with `ModuleNotFoundError` or a fabricated repository path
