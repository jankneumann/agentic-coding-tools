"""The verdict that completes a work package.

``PackageAcceptance`` is the only value ``DAGScheduler.mark_completed`` and the
integration gate accept as proof that a package passed. It is produced by
``result_validator.accept_package_result`` from a validated result, or by
``PackageAcceptance.override_for`` when a named approver records a reason.

This module imports only the standard library so that the scheduler can check
the type without pulling in the validator and its schema dependencies.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class PackageAcceptance:
    """Whether a package's result was accepted, and why or why not.

    Attributes:
        package_id: The package the verdict is about.
        accepted: True only for a validated PASS or a recorded override.
        outcome: The result's effective outcome, or None when it could not be
            read (and for an override, which is not derived from a result).
        reasons: One entry per failed condition; empty for a clean acceptance.
        override: Read-only ``{"reason", "approver"}`` when the verdict is an
            override.
        result_digest: ``digest_result`` of the result the verdict was made
            from, so a decision point can tell that a recorded result is the
            one that was accepted; None for an override.

    Raises:
        ValueError: if the verdict is accepted without either an outcome of
            PASS or a recorded override, or if an override has a blank reason
            or approver. There is no way to accept a package silently.
    """

    package_id: str
    accepted: bool
    outcome: str | None
    reasons: tuple[str, ...] = ()
    override: Mapping[str, str] | None = None
    result_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.override is not None:
            override = dict(self.override)
            for key in ("reason", "approver"):
                override[key] = _require_text(key, override.get(key))
            # A read-only copy: the recorded reason and approver must not
            # change after the verdict is made.
            object.__setattr__(self, "override", MappingProxyType(override))
        elif self.accepted and self.outcome != "PASS":
            raise ValueError(
                "an accepted verdict needs outcome PASS or a recorded override "
                f"(use PackageAcceptance.override_for); got outcome={self.outcome!r}"
            )

    @classmethod
    def override_for(
        cls, package_id: str, reason: str, approver: str,
    ) -> PackageAcceptance:
        """Accept a package on a recorded human decision.

        Raises:
            ValueError: if the package id, reason or approver is blank.
        """
        clean_package = _require_text("package_id", package_id)
        clean_reason = _require_text("reason", reason)
        clean_approver = _require_text("approver", approver)
        return cls(
            package_id=clean_package,
            accepted=True,
            outcome=None,
            reasons=(f"override: {clean_reason}",),
            override={"reason": clean_reason, "approver": clean_approver},
        )


def digest_result(result: Any) -> str:
    """A stable SHA-256 of a result payload, independent of key order."""
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"override requires a non-blank {name}")
    return value.strip()
