"""Approval gate service — the interviewer abstraction for human gates.

This is the ri-05 *approval gate service*: a small, host-assisted library that turns
the machine-readable trust posture (ri-04, :mod:`shared.trust_posture`) into an
executed decision at a workflow gate. It is modeled on attractor's *Interviewer*
interface — auto-approve / queue / callback / console with a timeout and a default
choice — collapsed onto this repo's existing coordinator surface (approval queue,
reply-to-approve notifications, audit log).

Given a gate name and a context dict, :meth:`ApprovalGate.evaluate` returns an
:class:`ApprovalDecision`:

- ``auto``                — log to audit and proceed immediately.
- ``notify_with_timeout`` — file a coordinator approval (``request_approval``), push a
                            reply-to-approve notification, poll ``check_approval`` until
                            the human resolves it *or* ``timeout_seconds`` elapses; on
                            timeout apply the gate's ``default_action`` (proceed | block).
- ``block``               — return a BLOCKED decision that *parks* the caller. The
                            library never hangs; the orchestrator persists loop state
                            and stops for later resume.

Two invariants dominate the design:

1. **Fail closed.** If the coordinator transport is unreachable at *any* point of a
   ``notify_with_timeout`` flow (filing the approval, notifying, or polling), the gate
   degrades to ``block`` rather than guessing. Ambiguity parks work.
2. **Audit always.** *Every* decision — auto, human-resolved, defaulted, blocked, or
   degraded — is recorded through the injected :class:`AuditSink` with the posture
   disposition that authorized it. Audit is attempted on every path; an audit-sink
   failure is swallowed (best-effort) so it can never itself crash a gate, but with a
   working sink the record is guaranteed.

Determinism / testability: the polling clock, the sleep function, the coordinator
client, and the audit sink are all injectable (mirroring ri-01's injectable runners).
Tests drive the whole state machine with a fake clock and a fake client — no real
sleeping, no real network.

Host-assisted invariant: this library makes **no direct LLM API calls**. It only
consults the posture, talks to the coordinator over the injected client, and records
audit. Any model-in-the-loop behavior belongs to the coordinator/host, not here.

Typical use::

    from shared.approval_gate import build_default_gate
    from shared.trust_posture import Gate

    gate = build_default_gate(agent_id="autopilot-1")
    decision = gate.evaluate(Gate.PROPOSAL_APPROVAL, {"change_id": "add-foo"})
    if decision.proceed:
        continue_workflow()
    else:
        park_loop_state(decision)      # persist + stop; resume later
"""
from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Union

from shared.trust_posture import (
    DefaultAction,
    Disposition,
    Gate,
    GateDisposition,
    TrustPosture,
    load_posture,
)

logger = logging.getLogger(__name__)

# Default cadence for polling ``check_approval`` inside a notify_with_timeout window.
DEFAULT_POLL_INTERVAL_SECONDS = 5.0

# The audit operation name every gate decision is logged under, so the whole gate
# history is queryable with a single ``operation`` filter.
AUDIT_OPERATION = "approval_gate_decision"


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #

class Outcome(str, enum.Enum):
    """The caller-facing verdict: may the workflow proceed, or is it parked?"""

    PROCEED = "proceed"
    BLOCKED = "blocked"


class Resolution(str, enum.Enum):
    """*How* the outcome was reached — the audit-grade detail behind :class:`Outcome`.

    ``PROCEED`` outcomes: ``AUTO``, ``APPROVED``, ``TIMEOUT_PROCEED``.
    ``BLOCKED`` outcomes: ``REJECTED``, ``TIMEOUT_BLOCK``, ``POSTURE_BLOCK``,
    ``COORDINATOR_UNREACHABLE``.
    """

    AUTO = "auto"                                    # posture said auto
    APPROVED = "approved"                            # human approved in the window
    REJECTED = "rejected"                            # human denied in the window
    TIMEOUT_PROCEED = "timeout_default_proceed"      # timer expired, default_action=proceed
    TIMEOUT_BLOCK = "timeout_default_block"          # timer expired, default_action=block
    POSTURE_BLOCK = "posture_block"                  # posture said block
    COORDINATOR_UNREACHABLE = "coordinator_unreachable"  # fail-closed degradation


_PROCEED_RESOLUTIONS = frozenset(
    {Resolution.AUTO, Resolution.APPROVED, Resolution.TIMEOUT_PROCEED}
)


@dataclass(frozen=True)
class ApprovalDecision:
    """The result of evaluating one gate.

    ``outcome``      — PROCEED or BLOCKED (what the caller acts on).
    ``resolution``   — the specific path taken (audit-grade).
    ``disposition``  — the trust-posture disposition that authorized this decision.
    ``gate``         — the gate that was evaluated.
    ``reason``       — human-readable one-liner for logs/notifications.
    ``approval_id``  — the coordinator approval request id, when one was filed.
    ``default_action`` — the applied default, when the timer expired.
    ``posture_present`` — whether a TRUST_POSTURE.md was loaded (vs. the absent-file
                          all-block default), so audit can distinguish them.
    """

    gate: Gate
    outcome: Outcome
    resolution: Resolution
    disposition: Disposition
    reason: str
    approval_id: Optional[str] = None
    default_action: Optional[DefaultAction] = None
    posture_present: bool = False

    @property
    def proceed(self) -> bool:
        return self.outcome is Outcome.PROCEED

    @property
    def blocked(self) -> bool:
        return self.outcome is Outcome.BLOCKED

    def to_audit_record(self) -> dict[str, Any]:
        """Flatten to the dict handed to the :class:`AuditSink`."""
        return {
            "gate": self.gate.value,
            "outcome": self.outcome.value,
            "resolution": self.resolution.value,
            "authorizing_disposition": self.disposition.value,
            "reason": self.reason,
            "approval_id": self.approval_id,
            "default_action": (
                self.default_action.value if self.default_action is not None else None
            ),
            "posture_present": self.posture_present,
        }


# --------------------------------------------------------------------------- #
# Injection seams
# --------------------------------------------------------------------------- #

class CoordinatorUnavailable(Exception):
    """Raised by a :class:`CoordinatorClient` when the coordinator transport fails.

    Raising this from ``request_approval``, ``push_notification``, or
    ``check_approval`` triggers the gate's fail-closed degradation to ``block``.
    A client MUST raise this (rather than return a sentinel) for *transport* errors
    so the gate can distinguish "coordinator is down" from "the human said no".
    """


class CoordinatorClient(Protocol):
    """The coordinator approval surface the gate depends on.

    All three methods raise :class:`CoordinatorUnavailable` on transport failure.
    ``check_approval`` returns one of ``pending`` | ``approved`` | ``denied`` |
    ``expired`` (the coordinator's ``approval_queue.status`` vocabulary).
    """

    def request_approval(
        self,
        *,
        operation: str,
        resource: Optional[str],
        context: dict[str, Any],
        timeout_seconds: int,
    ) -> str:
        """File an approval request; return its ``request_id``."""
        ...

    def push_notification(
        self, *, subject: str, body: str, approval_id: str
    ) -> bool:
        """Push a reply-to-approve notification. Returns whether a channel accepted it.

        A ``False`` return (no channel configured / soft no-op) is non-fatal — the
        approval is still filed and pollable. Only a raised
        :class:`CoordinatorUnavailable` (transport down) fails the gate closed.
        """
        ...

    def check_approval(self, approval_id: str) -> str:
        """Return the current status of an approval request."""
        ...


class AuditSink(Protocol):
    """The durable record surface for gate decisions."""

    def record(self, record: dict[str, Any]) -> bool:
        """Persist one gate-decision record. Returns success (best-effort)."""
        ...


Clock = Callable[[], float]
Sleep = Callable[[float], None]
PostureLoader = Callable[..., TrustPosture]


# --------------------------------------------------------------------------- #
# The gate service
# --------------------------------------------------------------------------- #

@dataclass
class ApprovalGate:
    """Evaluate workflow gates against the trust posture — the interviewer.

    Construct with an injected :class:`CoordinatorClient` and :class:`AuditSink`; the
    clock, sleep, poll interval, and posture loader are injectable for deterministic
    tests. :func:`build_default_gate` wires the production (bridge-backed) defaults.
    """

    coordinator: CoordinatorClient
    audit: AuditSink
    agent_id: str = "approval-gate"
    repo_root: Optional[str] = None
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    clock: Clock = time.monotonic
    sleep: Sleep = time.sleep
    posture_loader: PostureLoader = load_posture
    # Overrides the (repo_root) argument passed to the loader when set; lets tests and
    # callers point at an explicit contract path.
    posture_path: Optional[str] = None
    _logger: logging.Logger = field(default=logger, repr=False)

    def evaluate(
        self, gate: Union[Gate, str], context: Optional[dict[str, Any]] = None
    ) -> ApprovalDecision:
        """Resolve ``gate`` against the current posture and return a decision.

        Reads the posture fresh on every call (ri-04's hot-reload property). Unknown
        gate names raise ``ValueError`` from the loader — a programming error, not a
        posture decision, so it is intentionally not swallowed.
        """
        ctx = dict(context or {})
        posture = self.posture_loader(self.repo_root, path=self.posture_path)
        gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
        gd = posture.disposition_for(gate_enum)

        if gd.disposition is Disposition.AUTO:
            return self._finalize(self._auto(gate_enum, gd), posture)
        if gd.disposition is Disposition.BLOCK:
            return self._finalize(self._posture_block(gate_enum, gd), posture)
        # NOTIFY_WITH_TIMEOUT
        return self._finalize(self._notify(gate_enum, gd, ctx), posture)

    # -- disposition handlers ------------------------------------------------ #

    def _auto(self, gate: Gate, gd: GateDisposition) -> _Draft:
        return _Draft(
            gate=gate,
            outcome=Outcome.PROCEED,
            resolution=Resolution.AUTO,
            disposition=gd.disposition,
            reason=f"gate {gate.value!r} auto-approved by trust posture",
        )

    def _posture_block(self, gate: Gate, gd: GateDisposition) -> _Draft:
        return _Draft(
            gate=gate,
            outcome=Outcome.BLOCKED,
            resolution=Resolution.POSTURE_BLOCK,
            disposition=gd.disposition,
            reason=f"gate {gate.value!r} parked: trust posture disposition is block",
        )

    def _notify(self, gate: Gate, gd: GateDisposition, ctx: dict[str, Any]) -> _Draft:
        # gd.timeout_seconds / gd.default_action are guaranteed non-None for
        # notify_with_timeout by the ri-04 loader/validator.
        timeout = int(gd.timeout_seconds or 0)
        default_action = gd.default_action or DefaultAction.BLOCK

        # (1) File the approval. Transport failure here → fail closed.
        try:
            approval_id = self.coordinator.request_approval(
                operation=self._operation_name(gate),
                resource=ctx.get("resource"),
                context=ctx,
                timeout_seconds=timeout,
            )
        except CoordinatorUnavailable as exc:
            return self._unreachable(gate, gd, f"request_approval failed: {exc}")

        # (2) Notify. A raised CoordinatorUnavailable (transport down) fails closed;
        # an undelivered notification (returns False: no channel/auth/rate-limit) is
        # non-fatal here — the approval is still filed and pollable — but its delivery
        # status gates whether a default_action=proceed may auto-proceed on timeout.
        try:
            notified = self.coordinator.push_notification(
                subject=f"Approval needed: {gate.value}",
                body=self._notification_body(gate, ctx, approval_id, timeout),
                approval_id=approval_id,
            )
        except CoordinatorUnavailable as exc:
            return self._unreachable(
                gate, gd, f"push_notification failed: {exc}", approval_id=approval_id
            )

        # (3) Poll until resolved or the timer expires.
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            try:
                status = self.coordinator.check_approval(approval_id)
            except CoordinatorUnavailable as exc:
                return self._unreachable(
                    gate, gd, f"check_approval failed: {exc}", approval_id=approval_id
                )

            resolved = self._interpret_status(
                gate, gd, status, approval_id, notified=notified
            )
            if resolved is not None:
                return resolved

            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            self.sleep(min(self.poll_interval_seconds, remaining))

        # (4) Timer expired unresolved → apply the default action (a proceed default
        # fails closed to block when the notification was never delivered).
        return self._apply_default(
            gate, gd, default_action, approval_id, notified=notified
        )

    # -- notify helpers ------------------------------------------------------ #

    def _interpret_status(
        self,
        gate: Gate,
        gd: GateDisposition,
        status: str,
        approval_id: str,
        *,
        notified: bool = True,
    ) -> Optional[_Draft]:
        """Map a coordinator status to a terminal draft, or ``None`` to keep polling."""
        normalized = (status or "").strip().lower()
        if normalized == "approved":
            return _Draft(
                gate=gate,
                outcome=Outcome.PROCEED,
                resolution=Resolution.APPROVED,
                disposition=gd.disposition,
                reason=f"gate {gate.value!r} approved by human",
                approval_id=approval_id,
            )
        if normalized in ("denied", "rejected"):
            return _Draft(
                gate=gate,
                outcome=Outcome.BLOCKED,
                resolution=Resolution.REJECTED,
                disposition=gd.disposition,
                reason=f"gate {gate.value!r} denied by human",
                approval_id=approval_id,
            )
        if normalized == "expired":
            # Server-side expiry is the same terminal condition as our local timeout.
            default_action = gd.default_action or DefaultAction.BLOCK
            return self._apply_default(
                gate, gd, default_action, approval_id, notified=notified
            )
        # pending / unknown → keep polling
        return None

    def _apply_default(
        self,
        gate: Gate,
        gd: GateDisposition,
        default_action: DefaultAction,
        approval_id: str,
        *,
        notified: bool = True,
    ) -> _Draft:
        if default_action is DefaultAction.PROCEED and not notified:
            # The gate would auto-proceed on timeout, but no human was ever
            # notified (notification undelivered). Proceeding would be an
            # unattended action nobody could have vetoed, so fail closed to block.
            self._logger.warning(
                "approval gate %s timed out with default_action=proceed but the "
                "notification was undelivered; failing closed to block",
                gate.value,
            )
            return _Draft(
                gate=gate,
                outcome=Outcome.BLOCKED,
                resolution=Resolution.TIMEOUT_BLOCK,
                disposition=gd.disposition,
                reason=(
                    f"gate {gate.value!r} timed out; default_action=proceed NOT applied "
                    "because the approval notification was undelivered — failing closed"
                ),
                approval_id=approval_id,
                default_action=DefaultAction.BLOCK,
            )
        if default_action is DefaultAction.PROCEED:
            return _Draft(
                gate=gate,
                outcome=Outcome.PROCEED,
                resolution=Resolution.TIMEOUT_PROCEED,
                disposition=gd.disposition,
                reason=(
                    f"gate {gate.value!r} timed out; default_action=proceed applied"
                ),
                approval_id=approval_id,
                default_action=DefaultAction.PROCEED,
            )
        return _Draft(
            gate=gate,
            outcome=Outcome.BLOCKED,
            resolution=Resolution.TIMEOUT_BLOCK,
            disposition=gd.disposition,
            reason=f"gate {gate.value!r} timed out; default_action=block applied",
            approval_id=approval_id,
            default_action=DefaultAction.BLOCK,
        )

    def _unreachable(
        self,
        gate: Gate,
        gd: GateDisposition,
        detail: str,
        approval_id: Optional[str] = None,
    ) -> _Draft:
        self._logger.warning(
            "approval gate %s degrading to block: coordinator unreachable (%s)",
            gate.value,
            detail,
        )
        return _Draft(
            gate=gate,
            outcome=Outcome.BLOCKED,
            resolution=Resolution.COORDINATOR_UNREACHABLE,
            disposition=gd.disposition,
            reason=f"gate {gate.value!r} parked: coordinator unreachable ({detail})",
            approval_id=approval_id,
        )

    # -- finalize + audit ---------------------------------------------------- #

    def _finalize(self, draft: _Draft, posture: TrustPosture) -> ApprovalDecision:
        decision = ApprovalDecision(
            gate=draft.gate,
            outcome=draft.outcome,
            resolution=draft.resolution,
            disposition=draft.disposition,
            reason=draft.reason,
            approval_id=draft.approval_id,
            default_action=draft.default_action,
            posture_present=posture.present,
        )
        self._record_audit(decision)
        return decision

    def _record_audit(self, decision: ApprovalDecision) -> None:
        """Best-effort audit. A sink failure is logged but never crashes the gate.

        The decision is still returned to the caller either way; with a healthy sink
        (the tested path) the record is guaranteed.
        """
        record = decision.to_audit_record()
        record["agent_id"] = self.agent_id
        record["operation"] = AUDIT_OPERATION
        try:
            ok = self.audit.record(record)
            if not ok:
                self._logger.warning(
                    "audit sink reported failure for gate %s decision %s",
                    decision.gate.value,
                    decision.resolution.value,
                )
        except Exception:  # noqa: BLE001 - audit must never break the gate
            self._logger.exception(
                "audit sink raised for gate %s decision %s",
                decision.gate.value,
                decision.resolution.value,
            )

    # -- context formatting -------------------------------------------------- #

    def _operation_name(self, gate: Gate) -> str:
        return f"gate:{gate.value}"

    def _notification_body(
        self, gate: Gate, ctx: dict[str, Any], approval_id: str, timeout: int
    ) -> str:
        parts = [
            f"Approval required for gate '{gate.value}'.",
            f"Request id: {approval_id}",
            f"Timeout: {timeout}s (reply to approve/deny before it expires).",
        ]
        if ctx:
            parts.append(f"Context: {ctx}")
        return "\n".join(parts)


@dataclass
class _Draft:
    """Internal pre-finalize decision (before the posture-present flag + audit)."""

    gate: Gate
    outcome: Outcome
    resolution: Resolution
    disposition: Disposition
    reason: str
    approval_id: Optional[str] = None
    default_action: Optional[DefaultAction] = None


# --------------------------------------------------------------------------- #
# Production (bridge-backed) default clients
# --------------------------------------------------------------------------- #

def _import_bridge() -> Any:
    """Import the coordination bridge from its sibling skill dir, lazily.

    Returns the module, or raises ``ImportError``. Kept lazy so the library imports
    (and unit tests inject fakes) without the bridge on ``sys.path``.
    """
    import sys
    from pathlib import Path

    bridge_scripts = (
        Path(__file__).resolve().parent.parent / "coordination-bridge" / "scripts"
    )
    if str(bridge_scripts) not in sys.path:
        sys.path.insert(0, str(bridge_scripts))
    import coordination_bridge  # type: ignore[import-not-found]

    return coordination_bridge


class BridgeCoordinatorClient:
    """Default :class:`CoordinatorClient` over the coordinator HTTP bridge.

    Uses the bridge's transport primitives to hit ``/approvals/request``,
    ``/approvals/{id}``, and ``/notifications/test``. Any transport failure (missing
    URL, unreachable coordinator, 5xx, 404 capability-absent) raises
    :class:`CoordinatorUnavailable`, so the gate fails closed. Never makes LLM calls.
    """

    def __init__(
        self,
        *,
        agent_id: str = "approval-gate",
        http_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id
        self._http_url = http_url
        self._api_key = api_key

    def _bridge(self) -> Any:
        try:
            return _import_bridge()
        except ImportError as exc:  # bridge not deployed alongside → fail closed
            raise CoordinatorUnavailable(f"coordination bridge unavailable: {exc}")

    def _resolved(self, bridge: Any) -> tuple[str, Optional[str]]:
        url = bridge._resolve_http_url(self._http_url)
        if not url:
            raise CoordinatorUnavailable("no coordinator HTTP URL configured")
        return url, bridge._resolve_api_key(self._api_key)

    @staticmethod
    def _require_ok(response: dict[str, Any]) -> dict[str, Any]:
        status = response.get("status_code")
        if status is None or status >= 500 or status == 404:
            raise CoordinatorUnavailable(
                f"coordinator transport error (status={status}, "
                f"error={response.get('error')})"
            )
        if status in (401, 403):
            # Auth failure is not the human's decision → fail closed.
            raise CoordinatorUnavailable(f"coordinator unauthorized (status={status})")
        return response

    def request_approval(
        self,
        *,
        operation: str,
        resource: Optional[str],
        context: dict[str, Any],
        timeout_seconds: int,
    ) -> str:
        bridge = self._bridge()
        url, api_key = self._resolved(bridge)
        response = self._require_ok(
            bridge._http_request(
                method="POST",
                path="/approvals/request",
                payload={
                    "agent_id": self.agent_id,
                    "operation": operation,
                    "resource": resource,
                    "context": context,
                    "timeout_seconds": timeout_seconds,
                },
                http_url=url,
                api_key=api_key,
            )
        )
        data = response.get("data") or {}
        request_id = data.get("request_id")
        if not request_id:
            raise CoordinatorUnavailable(
                "approval request returned no request_id (approvals disabled?)"
            )
        return str(request_id)

    def push_notification(
        self, *, subject: str, body: str, approval_id: str
    ) -> bool:
        bridge = self._bridge()
        url, api_key = self._resolved(bridge)
        response = bridge._http_request(
            method="POST",
            path="/notifications/test",
            payload={"subject": subject, "body": body, "approval_id": approval_id},
            http_url=url,
            api_key=api_key,
        )
        status = response.get("status_code")
        if status is None or status >= 500:
            # Transport genuinely down → fail closed (raised, caller degrades to block).
            raise CoordinatorUnavailable(
                f"notification transport error (status={status})"
            )
        # We deliberately do NOT report delivery from this path. `/notifications/test`
        # is a *diagnostic* endpoint: it emits a generic test notification and ignores
        # the approval subject/body/approval_id, so even a `sent: true` does not mean a
        # human received the actual approval (with its id and approve/deny actions).
        # Reporting delivery here would let a default_action=proceed gate auto-proceed
        # on timeout believing a human was asked when they were not. Until a real
        # approval-notification channel exists (one that carries the approval id and
        # actionable instructions), return False so `proceed` gates fail closed on
        # timeout. The approval is still filed and pollable, so a human can resolve it
        # from the queue; and the 5xx check above still fails closed when the
        # coordinator is unreachable.
        # TODO: return True only once a dedicated approval-notification endpoint
        # confirms the *approval* (not a test ping) was delivered.
        return False

    def check_approval(self, approval_id: str) -> str:
        bridge = self._bridge()
        url, api_key = self._resolved(bridge)
        response = self._require_ok(
            bridge._http_request(
                method="GET",
                path=f"/approvals/{approval_id}",
                http_url=url,
                api_key=api_key,
            )
        )
        data = response.get("data") or {}
        return str(data.get("status", "pending"))


class BridgeAuditSink:
    """Default :class:`AuditSink` that records gate decisions on the coordinator.

    Host-side skill code has no direct DB handle, and the coordinator exposes no
    external audit-*write* route, so this sink persists the decision through the
    coordinator's durable memory surface (``/memory/store`` via the bridge's
    ``try_remember``) tagged ``approval_gate`` — a queryable, immutable-by-convention
    record. When the gate runs *inside* the coordinator process, swap in a sink that
    calls ``audit.log_operation`` directly; the injectable seam makes that a one-liner.
    Best-effort: returns ``False`` rather than raising when the coordinator is down,
    because a park/proceed decision must still be returned to the caller.
    """

    def __init__(
        self,
        *,
        agent_id: str = "approval-gate",
        http_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id
        self._http_url = http_url
        self._api_key = api_key

    def record(self, record: dict[str, Any]) -> bool:
        try:
            bridge = _import_bridge()
        except ImportError:
            return False
        result = bridge.try_remember(
            agent_id=self.agent_id,
            event_type="approval_gate_decision",
            summary=record.get("reason", "approval gate decision"),
            details=record,
            outcome=record.get("outcome"),
            tags=[
                "approval_gate",
                f"gate:{record.get('gate')}",
                f"disposition:{record.get('authorizing_disposition')}",
                f"resolution:{record.get('resolution')}",
            ],
            http_url=self._http_url,
            api_key=self._api_key,
        )
        return bool(result.get("status") == "ok")


def build_default_gate(
    *,
    agent_id: str = "approval-gate",
    repo_root: Optional[str] = None,
    http_url: Optional[str] = None,
    api_key: Optional[str] = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> ApprovalGate:
    """Wire an :class:`ApprovalGate` with the production bridge-backed defaults."""
    return ApprovalGate(
        coordinator=BridgeCoordinatorClient(
            agent_id=agent_id, http_url=http_url, api_key=api_key
        ),
        audit=BridgeAuditSink(agent_id=agent_id, http_url=http_url, api_key=api_key),
        agent_id=agent_id,
        repo_root=repo_root,
        poll_interval_seconds=poll_interval_seconds,
    )
