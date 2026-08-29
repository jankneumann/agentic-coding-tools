## ADDED Requirements

### Requirement: One fact schema feeds every capture path

Hook-based Langfuse logging and transcript capture SHALL both derive from
the `collect-transcripts` adapter output (`NormalizedEvent`), extended
with subagent linkage (`parent_session_id`, `spawned_by_tool_use_id`,
`agent_label`). No capture path SHALL maintain a private transcript
parser for a harness that has an adapter.

#### Scenario: Hook processes a session turn

- **WHEN** the Stop hook runs for a harness with a registered adapter
- **THEN** it SHALL obtain events via that adapter's
  `normalize_session()`
- **AND** the observations it emits SHALL carry `session_id`, the
  harness identifier tag, `as_type="agent"` per turn and
  `as_type="tool"` per tool invocation

#### Scenario: Adapter lacks linkage fields

- **WHEN** a normalized session contains no subagent linkage fields
- **THEN** the flow display SHALL render it as a single-agent session
- **AND** SHALL NOT fail

### Requirement: Flow state is a pure fold over facts

The flow display SHALL compute session state as an idempotent,
commutative fold over the ordered fact stream, so replaying any prefix
reproduces exactly the state live playback would have reached, and fact
arrival order never changes terminal state.

#### Scenario: User seeks backward in a replay

- **WHEN** the playhead moves to an earlier content-time position
- **THEN** the rendered state SHALL equal a fresh fold of
  `facts[0..playhead]`

#### Scenario: Facts arrive out of order

- **WHEN** the same fact set is folded in two different orders
- **THEN** the resulting states SHALL be equal

#### Scenario: Spawn acknowledgment arrives

- **WHEN** a fact acknowledges an asynchronous agent launch
- **THEN** the subagent SHALL be marked launched, not completed
- **AND** terminal status SHALL be set only by explicit completion facts

### Requirement: Both sources serve the same wire shape

The flow API SHALL serve session summaries and ordered fact streams from
captured transcript JSONL and from the Langfuse API in one contract
shape, SHALL prefer the transcript source when both exist, and SHALL
keep Langfuse credentials server-side.

#### Scenario: A source is unavailable

- **WHEN** Langfuse is unreachable or the transcripts directory is empty
- **THEN** the API SHALL return the remaining source's results with a
  `source_warnings` entry
- **AND** SHALL NOT return an error status for the missing source alone

#### Scenario: Session exists in both sources

- **WHEN** a session id resolves in transcripts and in Langfuse
- **THEN** the event stream SHALL come from the transcript source

### Requirement: Capture sanitizes before egress

Every capture path SHALL apply the shared sanitizer chain to prompts,
tool arguments, and tool results before writing transcript JSONL or
emitting to Langfuse, and SHALL respect the existing prompt-logging
truncation posture.

#### Scenario: A secret appears in a tool result

- **WHEN** a normalized event contains a recognizable credential pattern
- **THEN** the persisted and emitted forms SHALL contain the redacted
  form only

### Requirement: Capture never degrades a session

Hooks and batch uploaders SHALL be gated on explicit enablement, SHALL
exit successfully when credentials or configuration are absent, and
SHALL fail soft on adapter or network errors without interrupting the
harness session.

#### Scenario: Hook runs without Langfuse credentials

- **WHEN** the Stop hook executes with `LANGFUSE_ENABLED` unset
- **THEN** it SHALL exit 0 without side effects
