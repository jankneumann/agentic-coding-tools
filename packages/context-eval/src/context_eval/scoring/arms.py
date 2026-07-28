"""What one arm actually put in front of a coding job.

This is the harness's input contract (design D4). Every scorer consumes an
:class:`Arm` and nothing else — not a service response, not a database, not a
runtime. That single choice buys three properties at once: the exact-search
producer and the live semantic producer become interchangeable inputs, a
recorded run and a hand-written fixture score identically, and ``packages/``
never imports ``skills/``.

The invariants below mirror ri-12's ``SemanticContextResult.__post_init__``
deliberately. An injected section with no hits, or a fallback carrying hits, is
unconstructable there and is unconstructable here, so a producer cannot hand a
scorer a document the runtime could never have produced. Reimplemented rather
than imported for the dependency-direction reason above; ``arm_from_section``
is the seam where the two shapes meet, and it is one function.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: The three columns a case can be measured in. ``naive_phrase`` is the literal
#: ``rg -il '<query>'`` floor — recorded, never gated on (design D5).
ARM_NAMES: tuple[str, ...] = ("semantic", "baseline", "naive_phrase")

INJECTED = "injected"
FALLBACK = "fallback"


class ArmError(ValueError):
    """A rendered section that no runtime could have produced."""


@dataclass(frozen=True)
class RenderedHit:
    """One rendered excerpt: a file and an inclusive, 1-based line span."""

    file_path: str
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if not self.file_path:
            raise ArmError("a rendered hit must name a file")
        if self.start_line < 1:
            raise ArmError(f"start_line must be 1-based: {self.start_line}")
        if self.end_line < self.start_line:
            raise ArmError(f"end_line {self.end_line} precedes start_line {self.start_line}")

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def covers(self, line: int) -> bool:
        return self.start_line <= line <= self.end_line

    def intersects(self, start_line: int, end_line: int) -> bool:
        return self.start_line <= end_line and start_line <= self.end_line


@dataclass(frozen=True)
class RenderedOmission:
    """Something the arm decided not to render, and why.

    Kept because a section that silently drops material claims a completeness it
    does not have — which is precisely what ``ADV-DENY-PRECEDENCE`` asserts
    against. The scope scorer reads ``reason == "scope_filtered"`` from here.
    """

    file_path: str
    start_line: int
    end_line: int
    reason: str


@dataclass(frozen=True)
class Arm:
    """One arm's rendered section, under the single declared budget (D5)."""

    arm: str
    status: str
    hits: tuple[RenderedHit, ...] = ()
    omissions: tuple[RenderedOmission, ...] = ()
    fallback_trigger: str | None = None
    fallback_reason: str | None = None
    #: The outbound request body, when this arm issued one. Recorded so scope
    #: fidelity is measurable on the request as well as on the result (D8).
    request_body: Mapping[str, Any] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.arm not in ARM_NAMES:
            raise ArmError(f"unknown arm {self.arm!r}; expected one of {ARM_NAMES!r}")
        if self.status == INJECTED:
            if not self.hits:
                raise ArmError("an injected section must carry at least one hit")
            if self.fallback_trigger is not None or self.fallback_reason is not None:
                raise ArmError("an injected section cannot carry a fallback")
        elif self.status == FALLBACK:
            if self.hits:
                raise ArmError("a fallback section must carry no hits")
            if not self.fallback_trigger or not self.fallback_reason:
                raise ArmError("a fallback section must say why")
        else:
            raise ArmError(f"status must be {INJECTED!r} or {FALLBACK!r}, got {self.status!r}")

    @property
    def rendered_files(self) -> tuple[str, ...]:
        """Distinct files, first appearance first, in the arm's own rank order.

        A dict rather than a set: the order a reader meets these files in is the
        order ``steps_to_evidence`` counts, so it has to be the arm's order and
        not an arbitrary one (design D16).
        """
        seen: dict[str, None] = {}
        for hit in self.hits:
            seen.setdefault(hit.file_path, None)
        return tuple(seen)

    @property
    def rendered_lines(self) -> int:
        """Total lines rendered — the denominator of ``evidence_density``.

        Summed per hit rather than over distinct ``(file, line)`` pairs. ri-12's
        deduplication keeps partially overlapping spans on purpose, and the lines
        in the overlap really are printed twice into the section, so the reader
        really does pay for them twice.
        """
        return sum(hit.line_count for hit in self.hits)

    @property
    def injected(self) -> bool:
        return self.status == INJECTED

    def top_k_files(self, k: int) -> tuple[str, ...]:
        if k < 1:
            raise ArmError(f"k must be positive, got {k}")
        return self.rendered_files[:k]

    def scope_filtered_paths(self) -> tuple[str, ...]:
        return tuple(
            omission.file_path
            for omission in self.omissions
            if omission.reason == "scope_filtered"
        )


def fallback_arm(arm: str, trigger: str, reason: str) -> Arm:
    """The rendering of "nothing was injected" — a scored outcome, not a gap."""
    return Arm(arm=arm, status=FALLBACK, fallback_trigger=trigger, fallback_reason=reason)


def arm_from_section(document: Mapping[str, Any], *, arm: str = "semantic") -> Arm:
    """Adapt ri-12's published section document into an :class:`Arm`.

    The document is ``SemanticContextResult.to_dict()``, i.e. exactly what
    ``semantic-context-section.schema.json`` describes. This function is the only
    place in the harness that knows that shape, so a change to the section
    contract has one place to land.
    """
    status = str(document.get("status", ""))
    fallback = document.get("fallback") or {}
    if not isinstance(fallback, Mapping):
        raise ArmError("fallback must be an object when present")

    return Arm(
        arm=arm,
        status=status,
        hits=_hits(document.get("hits") or ()),
        omissions=_omissions(document.get("omissions") or ()),
        fallback_trigger=_optional_str(fallback.get("trigger")),
        fallback_reason=_optional_str(fallback.get("reason")),
    )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _hits(payloads: Iterable[Mapping[str, Any]] | Sequence[Any]) -> tuple[RenderedHit, ...]:
    return tuple(
        RenderedHit(
            file_path=str(payload["file_path"]),
            start_line=int(payload["start_line"]),
            end_line=int(payload["end_line"]),
        )
        for payload in payloads
    )


def _omissions(
    payloads: Iterable[Mapping[str, Any]] | Sequence[Any],
) -> tuple[RenderedOmission, ...]:
    return tuple(
        RenderedOmission(
            file_path=str(payload["file_path"]),
            start_line=int(payload["start_line"]),
            end_line=int(payload["end_line"]),
            reason=str(payload["reason"]),
        )
        for payload in payloads
    )
