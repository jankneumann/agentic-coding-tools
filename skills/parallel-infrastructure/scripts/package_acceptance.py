"""The verdict that completes a work package.

``PackageAcceptance`` is the only value ``DAGScheduler.mark_completed`` and the
integration gate accept as proof that a package passed. It is produced by
``result_validator.accept_package_result`` from a validated result, or by
``PackageAcceptance.override_for`` when a named approver records a reason.

This module imports only the standard library so that the scheduler can check
the type without pulling in the validator and its schema dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
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
        override: ``{"reason", "approver"}`` when the verdict is an override.
    """

    package_id: str
    accepted: bool
    outcome: str | None
    reasons: tuple[str, ...] = ()
    override: dict[str, str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))

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


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"override requires a non-blank {name}")
    return value.strip()
