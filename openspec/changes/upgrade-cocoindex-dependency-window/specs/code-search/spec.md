## ADDED Requirements

### Requirement: Coupled Upstream Dependency Window

The code-search package SHALL hard-pin its upstream indexing dependencies: `cocoindex-code` to an
exact version and `cocoindex` to a bounded window. The `cocoindex` window MUST be no wider than the
`cocoindex` requirement declared by the pinned `cocoindex-code` release, and the locked versions in
`packages/code-search/uv.lock` MUST satisfy the declared pins. The window recorded in the pipeline
fingerprint payload MUST equal the window declared in `pyproject.toml`. A change to any of these
SHALL be detected by an automated test that runs without the optional `index` extra installed.

#### Scenario: Range widening beyond the upstream cap is rejected

- **WHEN** the `cocoindex` upper bound in `pyproject.toml` is raised above the upper bound that the
  pinned `cocoindex-code` release declares (for example `<1.2.0` while `cocoindex-code==0.2.42`
  declares `<1.1.0`)
- **THEN** the dependency-window test SHALL fail with a message naming the coupling rule and both
  bounds

#### Scenario: Lockfile matches the declared pins

- **WHEN** the dependency-window test reads `packages/code-search/uv.lock`
- **THEN** the locked `cocoindex-code` version SHALL equal the exact pin
- **AND** the locked `cocoindex` version SHALL satisfy the declared window

#### Scenario: Fingerprint payload follows the pin

- **WHEN** the pinned `cocoindex` window or `cocoindex-code` version changes
- **THEN** the pipeline fingerprint payload SHALL record the same values as `pyproject.toml`
- **AND** the resulting pipeline fingerprint SHALL differ from the previous one, so no previously
  ready semantic index is reused

#### Scenario: Live install exposes the frozen surface

- **WHEN** the resource-gated compatibility test runs with the `index` extra installed
- **THEN** the installed `cocoindex` and `cocoindex-code` versions SHALL match the lock
- **AND** every upstream symbol imported by the indexer SHALL resolve with a compatible call
  signature

### Requirement: Matcher-Independent Path Policy Evaluation

Indexing-policy include, read, and deny decisions SHALL be identical for every repository path
regardless of which supported major version of the path-matching library is installed. Paths
containing control characters such as newline or tab MUST be evaluated by the same rules as other
paths, and a deny rule that covers a path's directory MUST deny that path.

#### Scenario: Deny rule covers a newline-named file

- **WHEN** the policy includes `**/*.py` and denies `src/private/**`
- **AND** the repository tracks `src/private/x\ny.py`
- **THEN** the path SHALL be rejected as denied
- **AND** its content SHALL NOT be read or embedded

#### Scenario: Include rule covers tab- and newline-named files

- **WHEN** the policy includes `src/**`
- **AND** the repository tracks `src/odd\tname.py` and `src/odd\nname.py`
- **THEN** both paths SHALL be eligible

#### Scenario: Decisions agree across matcher library versions

- **WHEN** the same policy and path set are evaluated with the locked path-matching library and
  with its other supported major version
- **THEN** every include, read, and deny decision SHALL be identical
