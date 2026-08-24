"""Unified agent trust scale — the single programmatic definition.

The scale itself is not new: ``openspec/specs/agent-coordinator/spec.md``
(Requirement "Agent Profiles", table "Profile Trust Levels") documents it as

    | Level | Name      | Typical Capabilities                                    |
    |-------|-----------|---------------------------------------------------------|
    | 0     | Untrusted | Read-only, no network, all changes require manual review |
    | 1     | Limited   | Read-write with locks, documentation domains only        |
    | 2     | Standard  | Full file access, approved domains, automated verification|
    | 3     | Elevated  | Skip Tier 0-1 verification, extended resource limits     |
    | 4     | Admin     | Full access, can modify policies and profiles            |

This module is that table's programmatic rendering (design D4 of
``derive-agent-identity-from-registry``). Every validator and enforcement point —
the ``agents.yaml`` JSON schema bounds, the policy engine's action-tier
thresholds, and the ``agent_profiles`` CHECK constraint — derives from here
rather than repeating integer literals.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Final


class TrustLevel(IntEnum):
    """Agent trust levels, ordered least to most privileged.

    ``IntEnum`` so members compare and serialize as the plain integers already
    stored in ``agent_profiles.trust_level`` and carried in policy contexts.
    """

    UNTRUSTED = 0
    LIMITED = 1
    STANDARD = 2
    ELEVATED = 3
    ADMIN = 4


#: Inclusive bounds of the scale — the authoritative source for the YAML schema
#: bounds and the ``agent_profiles`` CHECK constraint.
MIN_TRUST: Final[int] = int(min(TrustLevel))
MAX_TRUST: Final[int] = int(max(TrustLevel))

#: Action-tier thresholds consumed by the policy engine. An agent at
#: ``UNTRUSTED`` is suspended and denied every operation, so read access begins
#: at ``LIMITED``.
MIN_READ_TRUST: Final[TrustLevel] = TrustLevel.LIMITED
MIN_WRITE_TRUST: Final[TrustLevel] = TrustLevel.STANDARD
MIN_ADMIN_TRUST: Final[TrustLevel] = TrustLevel.ELEVATED

__all__ = [
    "MAX_TRUST",
    "MIN_ADMIN_TRUST",
    "MIN_READ_TRUST",
    "MIN_TRUST",
    "MIN_WRITE_TRUST",
    "TrustLevel",
]
