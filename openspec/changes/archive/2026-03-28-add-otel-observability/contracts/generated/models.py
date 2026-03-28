"""Generated type stubs for OTel metric labels.

These Literal types define the canonical label values for each metric family.
Import them in instrumentation code to ensure label consistency.
"""

from typing import Literal

LockOutcome = Literal["acquired", "refreshed", "denied", "error"]
QueueClaimOutcome = Literal["claimed", "empty", "error"]
QueueTaskOutcome = Literal["completed", "failed"]
PolicyDecision = Literal["allow", "deny"]
CacheResult = Literal["hit", "miss"]
GuardrailSeverity = Literal["block", "warn", "log"]
