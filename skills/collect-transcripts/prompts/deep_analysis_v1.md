# Transcript Deep Analysis — v1

You are performing a deep analysis of a coding agent session transcript that has been flagged as struggling. Your goal is to identify capability gaps — things the harness or agent was missing that caused the struggle.

## Task

Analyze the transcript and extract structured findings. For each finding, identify:

1. **failure_type**: One of: scope_violation, verification_failed, lock_unavailable, timeout, convergence_failed, context_exhaustion, tool_error, retry_storm, user_correction
2. **capability_gap**: A concise description of what capability was missing (free text)
3. **affected_skill**: The skill or workflow that was affected
4. **severity**: low | medium | high | critical
5. **description**: A 1-2 sentence explanation of the finding
6. **evidence**: List of specific signals from the transcript (tool names, error messages, etc.)

## Output Schema

Respond with a JSON array of finding objects:

```json
[
  {
    "failure_type": "<type>",
    "capability_gap": "<description>",
    "affected_skill": "<skill-name>",
    "severity": "<level>",
    "description": "<explanation>",
    "evidence": ["<signal1>", "<signal2>"]
  }
]
```

## Guidelines

- Focus on SYSTEMIC issues, not one-off errors
- A retry storm (3+ consecutive calls to the same tool) suggests the agent lacks a strategy for handling the first failure
- User corrections suggest the agent's understanding of the task was wrong
- Tool errors may indicate missing error handling or incorrect tool usage
- Scope violations suggest the agent's scope model is incomplete
- Multiple related signals should be grouped into a single finding
- Be specific about what capability was missing — "better error handling" is less useful than "Read tool should retry with alternative path when file not found"
