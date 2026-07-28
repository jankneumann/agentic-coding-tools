"""Scope compliance: four measures, zero tolerance, and one apparatus guard.

Measured on both ends of the exchange, because they can disagree and the
disagreement is the interesting case (design D8):

``outbound_scope_fidelity``
    The request body ri-12 builds carries *exactly* the case's declared
    ``read_allow``/``deny``. A client that quietly widened a scope before asking
    would produce a perfectly clean rendered section and would still have leaked
    the agent's boundary to the service.

``rendered_scope_violations``
    Rendered results falling outside the declared scope under deny-precedence
    semantics. **There is no tolerance.** One violation fails the gate and the
    path is named.

``deny_precedence``
    A path matching both an allow glob and a deny glob is absent from ``hits``
    *and* present in ``omissions`` with ``reason: "scope_filtered"``. Both halves
    are asserted: a section that silently drops material claims a completeness it
    does not have.

``expectation_honored``
    A case declaring a specific outcome — an empty scope, a rejected scope, an
    unrecognized service state — gets that exact ``(status, trigger, reason)``
    triple and zero rendered hits. The pair, never just the trigger: ri-12's
    state mapping is total by design, so a check on the trigger alone passes on
    the wrong cause.

Two implementation notes that are decisions rather than details.

**Zero tolerance is structural, not a threshold.** The manifest declares
``max_rendered_scope_violations: 0`` so a report is self-describing, and this
module records it — but the failure test is ``any violation at all``, independent
of that value. Reading the tolerance from data would make "allow three leaks" a
reviewable one-line diff, and design D8 says there is no tolerance to configure.
This is the one place the harness deliberately does not defer to the manifest,
and it defers in the safe direction: editing the manifest can never loosen it.

**The glob semantics are mirrored, not invented.** ``matches`` reproduces
``skills/validate-packages/scripts/context_impact.py:144`` exactly, including the
``**/`` prefix rule, and ``test_scope_scorer.py`` cross-checks the two
implementations over a table of paths. ``packages/`` may not import ``skills/``,
so the choice is between mirroring with a proof of agreement and depending on a
sibling skill; a silent divergence in glob matching is precisely the failure this
gate exists to detect.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from ..models import Case, Scope
from .arms import Arm

PASS = "pass"
FAIL = "fail"

SCOPE_FILTERED = "scope_filtered"

#: Threshold keys the manifest declares for this gate.
MAX_RENDERED_VIOLATIONS = "max_rendered_scope_violations"
MIN_OUTBOUND_FIDELITY = "min_outbound_scope_fidelity"
REQUIRED_THRESHOLDS: tuple[str, ...] = (MAX_RENDERED_VIOLATIONS, MIN_OUTBOUND_FIDELITY)

#: From the report contract's closed ``FailReason`` vocabulary.
SCOPE_VIOLATION = "scope_violation"
APPARATUS_FAILURE = "apparatus_failure"

RESOLVED = "resolved"
DEGRADED = "degraded"


class ScopeScoringError(ValueError):
    """The scope measurement is not well defined for the inputs it was given."""


def matches(path: str, pattern: str) -> bool:
    """Match a repository-relative path against a glob.

    ``fnmatchcase`` rather than ``fnmatch`` so the answer does not vary with the
    host filesystem's case sensitivity — a scope decision that differs between
    macOS and Linux is not a scope decision. A ``**/`` prefix additionally
    matches at the repository root, so ``**/*.py`` covers ``setup.py`` as well as
    ``pkg/mod.py``.
    """
    if fnmatchcase(path, pattern):
        return True
    return pattern.startswith("**/") and fnmatchcase(path, pattern[len("**/") :])


def allows(path: str, read_allow: Sequence[str], deny: Sequence[str]) -> bool:
    """Whether *path* is readable. Deny is evaluated first and wins outright."""
    if any(matches(path, pattern) for pattern in deny):
        return False
    return any(matches(path, pattern) for pattern in read_allow)


def scope_violations(arm: Arm, scope: Scope) -> tuple[str, ...]:
    """Rendered paths the declared scope rejects, in render order, deduplicated.

    Order preserved rather than sorted: the report names violating paths so a
    reader can find them, and "the third thing in the section" is more useful
    than an alphabetical list.
    """
    seen: dict[str, None] = {}
    for hit in arm.hits:
        if not allows(hit.file_path, scope.read_allow, scope.deny):
            seen.setdefault(hit.file_path, None)
    return tuple(seen)


def outbound_scope_fidelity(request_body: Mapping[str, object], scope: Scope) -> bool:
    """Does the outbound request carry exactly the declared scope, as an explicit one?"""
    payload = request_body.get("scope")
    if not isinstance(payload, Mapping):
        return False
    if payload.get("kind") != "explicit":
        return False
    read_allow = payload.get("read_allow")
    deny = payload.get("deny")
    if not isinstance(read_allow, Sequence) or isinstance(read_allow, (str, bytes)):
        return False
    if not isinstance(deny, Sequence) or isinstance(deny, (str, bytes)):
        return False
    return tuple(read_allow) == scope.read_allow and tuple(deny) == scope.deny


def deny_precedence_honored(arm: Arm, scope: Scope) -> bool:
    """Every denied path is absent from ``hits`` AND recorded as ``scope_filtered``.

    Vacuously true when the response offered nothing denied — which is why the
    corpus carries ``ADV-DENY-PRECEDENCE``, whose recorded body puts a denied
    path at the highest similarity in the response. Without an adversarial body
    this measure proves that the server behaved, not that the client re-checked.
    """
    denied_rendered = [
        hit.file_path
        for hit in arm.hits
        if any(matches(hit.file_path, pattern) for pattern in scope.deny)
    ]
    if denied_rendered:
        return False
    recorded = set(arm.scope_filtered_paths())
    for omission in arm.omissions:
        denied = any(matches(omission.file_path, pattern) for pattern in scope.deny)
        if denied and omission.file_path not in recorded:
            return False
    return True


def expectation_honored(case: Case, arm: Arm) -> bool | None:
    """Does *arm* match the exact outcome *case* declares? ``None`` if none is.

    ``None`` rather than ``True`` for a case with no expectation: "this case made
    no claim" and "this case's claim held" are different facts, and folding the
    first into the second inflates the match rate a fail-closed gate is judged on.
    """
    expectation = case.expectation
    if expectation is None:
        return None
    if arm.status != expectation.status:
        return False
    if expectation.trigger is not None and arm.fallback_trigger != expectation.trigger:
        return False
    if expectation.reason is not None and arm.fallback_reason != expectation.reason:
        return False
    if expectation.rendered_hits is not None and len(arm.hits) != expectation.rendered_hits:
        return False
    return True


@dataclass(frozen=True)
class ScopeCaseResult:
    """One case's scope measurements."""

    case_id: str
    consumer: str
    violations: tuple[str, ...]
    deny_precedence: bool
    #: ``None`` when the case never issued a request (an empty scope short-circuits
    #: before the wire), which is a fact about the case, not a missing measurement.
    outbound_fidelity: bool | None
    expectation_honored: bool | None

    @property
    def compliant(self) -> bool:
        return not self.violations and self.deny_precedence


@dataclass(frozen=True)
class ScopeGateResult:
    """The scope-compliance gate's outcome."""

    verdict: str
    measured: Mapping[str, float]
    thresholds: Mapping[str, float]
    fail_reasons: tuple[str, ...]
    violating_paths: tuple[str, ...]
    scope_adapter: str
    per_case: tuple[ScopeCaseResult, ...]


def score_case(
    case: Case, arm: Arm, *, request_body: Mapping[str, object] | None = None
) -> ScopeCaseResult:
    """Measure one case's scope compliance against its own declared scope."""
    return ScopeCaseResult(
        case_id=case.case_id,
        consumer=case.consumer,
        violations=scope_violations(arm, case.scope),
        deny_precedence=deny_precedence_honored(arm, case.scope),
        outbound_fidelity=(
            None if request_body is None else outbound_scope_fidelity(request_body, case.scope)
        ),
        expectation_honored=expectation_honored(case, arm),
    )


def score_scope(
    per_case: Sequence[ScopeCaseResult],
    thresholds: Mapping[str, float],
    *,
    scope_adapter: str,
) -> ScopeGateResult:
    """Compose the scope-compliance gate.

    A degraded adapter fails the gate before any number is considered. The
    measurements may look perfect and still be meaningless: they were computed
    under different glob semantics than the report claims, and reporting them
    would be worse than reporting nothing (design D8).
    """
    missing = [key for key in REQUIRED_THRESHOLDS if key not in thresholds]
    if missing:
        raise ScopeScoringError(f"the scope gate was given no {missing!r} threshold")
    if scope_adapter not in (RESOLVED, DEGRADED):
        raise ScopeScoringError(f"scope_adapter must be resolved or degraded: {scope_adapter!r}")
    if not per_case:
        raise ScopeScoringError("the scope gate scored no cases; a vacuous pass is unwritable")

    violating_paths = tuple(path for entry in per_case for path in entry.violations)
    deny_failures = [entry.case_id for entry in per_case if not entry.deny_precedence]

    checked = [entry for entry in per_case if entry.outbound_fidelity is not None]
    faithful = sum(1 for entry in checked if entry.outbound_fidelity)
    fidelity = (faithful / len(checked)) if checked else 1.0

    measured: dict[str, float] = {
        "rendered_scope_violations": len(violating_paths),
        "outbound_scope_fidelity": fidelity,
        "deny_precedence_failures": len(deny_failures),
        "cases_scored": len(per_case),
        "outbound_requests_checked": len(checked),
    }

    reasons: list[str] = []
    # Structural, not read from `thresholds`: see this module's docstring.
    if violating_paths or deny_failures:
        reasons.append(SCOPE_VIOLATION)
    if fidelity < thresholds[MIN_OUTBOUND_FIDELITY]:
        reasons.append(SCOPE_VIOLATION)
    if scope_adapter == DEGRADED:
        reasons.append(APPARATUS_FAILURE)

    ordered = tuple(dict.fromkeys(reasons))
    return ScopeGateResult(
        verdict=FAIL if ordered else PASS,
        measured=measured,
        thresholds=dict(thresholds),
        fail_reasons=ordered,
        violating_paths=violating_paths,
        scope_adapter=scope_adapter,
        per_case=tuple(per_case),
    )
