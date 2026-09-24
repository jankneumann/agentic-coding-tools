## ADDED Requirements

### Requirement: Judged Fix-Tier Classification for Markers and Deferred Findings

`classify_finding` SHALL replace the character-count heuristic on `markers`
findings and the substring heuristic on `deferred:*` findings with a
calibrated judgment: a `Noul("Could an agent act on this marker without
asking a human?")` question for `markers` findings, and a `Noul("Does this
finding include a concrete, applicable fix?")` question for `deferred:*`
findings. All judgeable findings from one `classify()` call SHALL be answered
in a single batched `decide()` call. `_is_ruff_fixable` and all other
source-based routing (`ruff`, `mypy`, `architecture`, `security`, unknown
sources) SHALL remain fully deterministic and SHALL NOT trigger a `decide()`
call. When the judgment is unavailable for the whole batch, or malformed or
missing for one finding within an otherwise-answered batch, that finding
SHALL fall back to the pre-existing heuristic (`_marker_has_sufficient_context`
or `_deferred_has_proposed_fix`), unchanged.

#### Scenario: A terse but actionable marker lands in the agent tier

- **GIVEN** a `markers` finding whose detail is short but names a concrete action
- **WHEN** the judgment confidently answers that an agent could act on it without asking a human
- **THEN** `classify_finding` SHALL return `tier="agent"`

#### Scenario: A verbose but unactionable marker lands in the manual tier

- **GIVEN** a `markers` finding with ten or more words of detail that names no concrete action
- **WHEN** the judgment confidently answers that an agent could not act on it without asking a human
- **THEN** `classify_finding` SHALL return `tier="manual"`

#### Scenario: All judgeable findings in one classify() call are answered by a single batched call

- **GIVEN** a findings list with two or more `markers` or `deferred:*` findings
- **WHEN** `classify` runs and the judgment is available
- **THEN** the calibrated-decision call SHALL be invoked exactly once for that `classify()` run

#### Scenario: Ruff, mypy, and architecture/security findings never trigger a decision call

- **GIVEN** a findings list containing only `ruff`, `mypy`, `architecture`, or `security` sourced findings
- **WHEN** `classify` runs
- **THEN** no calibrated-decision call SHALL be made

#### Scenario: Unavailable or partial judgment falls back to the existing heuristics unchanged

- **GIVEN** the judgment is unavailable for a whole `classify()` call, or malformed or missing for one finding within an otherwise-answered batch
- **WHEN** `classify_finding` runs for the affected finding(s)
- **THEN** the affected finding(s) SHALL be classified by the pre-existing character-count or substring heuristic, exactly as `classify_finding` behaved before the judgment existed
