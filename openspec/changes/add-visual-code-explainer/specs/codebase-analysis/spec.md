## ADDED Requirements

### Requirement: Atlas Symbol Tree Export

`skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional `--hops N` (default `2`, maximum `4`, larger values clamped with a stderr note) and `--direction out|in|both` (default `out`), and SHALL print an indented text tree to stdout instead of rendering the page. The traversal SHALL walk the symbol-level adjacency produced by `build_view_model()` (`symbolEdges`) restricted to edges whose `ty` is `call` — `import` and every other edge type are dependencies, not calls, and SHALL NOT appear as callers or callees — using only the Python standard library and making no network requests. Each line SHALL show `<name>  (<file>:<line>)  [<kind>]`, children SHALL be sorted by name then id, a node already on the current path SHALL be printed once with the suffix `(cycle)` and not expanded, and a parent with further neighbours beyond the hop depth SHALL carry the suffix `(+<n> more)` where `<n>` is the count of those omitted further neighbours. The output SHALL end with a single footer line `graph @ <sha7> · <language> <percent>% / <language> <percent>% covered`, one `<language> <percent>%` entry per language present, sorted by language name and joined with ` / `, with `<percent>` printed to exactly one decimal place as `Coverage.percent` returns it (for example `14.4%`, `37.0%`), unless `--no-coverage` is given. `<target>` SHALL resolve as exact node id, then unique symbol name, then module file path or basename (rooting the tree at the module with its own symbols as hop 1). Exit codes SHALL be `0` success, `1` input or IO error, `2` target not found, `3` target ambiguous (candidate ids listed on stderr, one per line, sorted). Output SHALL be byte-identical across runs for a fixed graph and arguments.

#### Scenario: Callees tree for a symbol

- **WHEN** `build_atlas.py --tree <symbol-id>` runs against a graph containing that symbol
- **THEN** stdout SHALL start with a root line matching `<name>  (<file>:<line>)  [<kind>]` and list its callees indented two spaces per hop, sorted by name then id
- **AND** the exit code SHALL be `0`

#### Scenario: Callers tree with hop cap

- **WHEN** `--direction in --hops 1` is given for a symbol with callers two hops away
- **THEN** only direct callers SHALL be printed
- **AND** each printed caller that has further callers SHALL carry a `(+<n> more)` suffix

#### Scenario: Non-call edges are excluded

- **WHEN** the graph contains `A calls B` and `A imports C`, and `--tree A --direction both` runs
- **THEN** `B` SHALL be listed under `callees:`
- **AND** `C` SHALL NOT appear anywhere in the output

#### Scenario: Cycle is printed once

- **WHEN** the graph contains `A calls B` and `B calls A` and `--tree A --hops 4` runs
- **THEN** `A` SHALL appear under `B` exactly once with the suffix `(cycle)`
- **AND** it SHALL NOT be expanded further

#### Scenario: File target gives the aggregated module view

- **WHEN** `--tree <file-basename>` names a module in the graph
- **THEN** the root line SHALL be the module and hop 1 SHALL be the module's own symbols
- **AND** subsequent hops SHALL follow those symbols' `call` edges

#### Scenario: Unknown target exits 2

- **WHEN** `--tree` names a symbol that is not in the graph
- **THEN** the exit code SHALL be `2`
- **AND** stderr SHALL contain `not found`

#### Scenario: Ambiguous target exits 3

- **WHEN** `--tree` names a bare symbol name matching several node ids
- **THEN** the exit code SHALL be `3`, distinct from not-found
- **AND** stderr SHALL list the candidate ids, one per line, sorted

#### Scenario: Deterministic output

- **WHEN** the same `--tree` invocation runs twice against the same graph file
- **THEN** the two stdout outputs SHALL be byte-identical

#### Scenario: Coverage footer matches the page banner

- **WHEN** `--tree` runs without `--no-coverage`
- **THEN** the footer percentages SHALL equal the `Coverage.percent` values `build_view_model()` computes for the same repository root

#### Scenario: Default hops and direction

- **WHEN** `--tree <target>` is invoked with neither `--hops` nor `--direction`
- **THEN** the traversal SHALL use `--hops 2` and `--direction out`
- **AND** the exit code SHALL be `0` for a resolvable target

#### Scenario: Hops above four are clamped

- **WHEN** `--tree <target> --hops 9` is given
- **THEN** the effective hop cap SHALL be `4`
- **AND** stderr SHALL contain a note that the value was clamped

#### Scenario: No-coverage suppresses the footer

- **WHEN** `--tree <target> --no-coverage` runs
- **THEN** stdout SHALL omit the `graph @` coverage footer line

#### Scenario: Input or IO error exits 1

- **WHEN** `--tree` cannot read the graph file (missing path via `--graph`, or unreadable IO)
- **THEN** the exit code SHALL be `1`

#### Scenario: Coverage footer shape

- **WHEN** `--tree` runs without `--no-coverage` on a graph with multiple languages
- **THEN** stdout SHALL end with one line matching `graph @ <sha7> · <language> <percent>% / <language> <percent>% covered`
- **AND** language entries SHALL be sorted by language name and joined with ` / `
- **AND** each `<percent>` SHALL use exactly one decimal place as returned by `Coverage.percent`

#### Scenario: Target resolution precedence

- **WHEN** the same string could match an exact node id and also appear as a symbol name
- **THEN** `--tree` SHALL resolve the exact node id and SHALL NOT treat the name match as ambiguous

#### Scenario: Unique name resolves

- **WHEN** `--tree` is given a bare symbol name that matches exactly one node
- **THEN** that node SHALL be the root and the exit code SHALL be `0`

#### Scenario: Direction both labels sections

- **WHEN** `--tree <target> --direction both` runs
- **THEN** stdout SHALL include labelled `callees:` and `callers:` sections
