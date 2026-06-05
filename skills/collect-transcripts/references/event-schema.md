# Normalized Event Schema

All vendor-specific adapters normalize their raw events into this common schema. Downstream consumers (sanitizer, triage, deep-analysis) operate on sequences of `NormalizedEvent` instances.

## NormalizedEvent

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string | Unique event identifier |
| `session_id` | string | Session this event belongs to |
| `timestamp` | string | ISO 8601 timestamp |
| `sequence_number` | int | Monotonically increasing within a session |
| `role` | EventRole | Who produced this event (user, assistant, tool, system) |
| `content` | list[ContentBlock] | Content blocks (text, thinking, tool_use, tool_result) |
| `usage` | TokenUsage? | Token usage (assistant events only) |
| `harness` | string | Source adapter identifier (e.g. "claude_code_cli") |
| `model` | string | Model identifier if available |
| `version` | string | Harness/CLI version if available |
| `metadata` | dict | Additional vendor-specific metadata |

## EventRole

| Value | Description |
|-------|-------------|
| `user` | Human user input |
| `assistant` | Agent/model response |
| `tool` | Tool execution result |
| `system` | System/metadata event |

## ContentBlock

| Field | Type | Description |
|-------|------|-------------|
| `type` | ContentType | Block type |
| `text` | string | Text content |
| `tool_name` | string | Tool name (tool_use blocks only) |
| `tool_input` | dict | Tool arguments (tool_use blocks only) |
| `tool_use_id` | string | Links tool_use to tool_result |
| `is_error` | bool | Whether the tool result is an error (tool_result only) |

## ContentType

| Value | Description |
|-------|-------------|
| `text` | Plain text |
| `thinking` | Agent thinking/reasoning |
| `tool_use` | Tool invocation with name and arguments |
| `tool_result` | Tool execution output |
| `image` | Image content (base64 or URL) |
| `unknown` | Unrecognized content type |

## TokenUsage

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | int | Input token count |
| `output_tokens` | int | Output token count |
| `cache_creation_input_tokens` | int | Cache creation tokens |
| `cache_read_input_tokens` | int | Cache read tokens |

## SessionSummary

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier |
| `harness` | string | Source adapter identifier |
| `source_path` | string | Filesystem path to the raw session file |
| `start_time` | string | ISO 8601 session start time |
| `event_count` | int | Number of events in the session |
| `metadata` | dict | Additional metadata |

## JSONL Format

Normalized events are serialized as JSONL (one JSON object per line) under `docs/transcripts/<date>/<session-id>.jsonl`.

Example line:
```json
{"event_id":"evt-001","session_id":"abc123","timestamp":"2026-05-01T10:00:00Z","sequence_number":0,"role":"user","content":[{"type":"text","text":"Fix the test"}],"harness":"claude_code_cli","model":"","version":"","metadata":{}}
```
