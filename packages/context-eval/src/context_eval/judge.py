"""An advisory qualitative review that cannot reach any verdict.

The judge is admissible and structurally powerless. ``agent-scenarios`` states
the rule as "the judge never overrides the deterministic verdict"; design D15
makes it a property instead of a promise, and this module is the half of that
property that lives here:

- Nothing in this module imports :mod:`context_eval.verdict`, and nothing in
  :mod:`context_eval.verdict` imports this one. ``test_judge_isolation.py``
  asserts both directions.
- The only thing produced here is a document. It is attached to a report by
  :func:`context_eval.report.attach_judge` *after* ``compose_verdict()`` has
  returned, and the report emitter takes it as an opaque mapping rather than as
  a type it can branch on.
- The notes are free prose, deliberately. Anything a machine could branch on
  would be a channel from the judge to the verdict, and there is no such channel.

An absent judge is a completely normal run. :data:`UNAVAILABLE` is what a run
with no configured backend records — ``{"available": false}`` — and no failure
reason exists for it, in this module or in the report contract's closed
vocabulary.

The backend shape follows ``agent-scenarios``' injectable judge:
``is_available()`` and ``complete(prompt, system)``. No model identifier appears
here as a literal; the backend names itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: The system prompt. It asks for prose about a rendered section and offers no
#: verdict, score, rating, or pass/fail vocabulary to fill in — there is nothing
#: for a caller to parse into an outcome even if one tried.
SYSTEM_PROMPT = (
    "You are reviewing a block of code context that was assembled for a "
    "software engineer working on a task. Describe, in prose, what is useful "
    "about it and what is missing or distracting. Do not score it, rate it, or "
    "give a verdict: this review is advisory and is recorded alongside a "
    "measurement it does not affect."
)

#: Longest note the report contract accepts, so an over-long completion is
#: truncated here rather than rejected by schema validation at write time.
MAX_NOTE_CHARACTERS = 4000


@runtime_checkable
class JudgeBackend(Protocol):
    """A qualitative review backend, injected or absent."""

    def is_available(self) -> bool:
        """Whether this backend can be called at all."""

    def complete(self, prompt: str, system: str) -> str:
        """Return prose for *prompt*."""


@dataclass(frozen=True)
class ReviewNote:
    """One case's prose review."""

    case_id: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "note": self.note[:MAX_NOTE_CHARACTERS]}


@dataclass(frozen=True)
class AdvisoryReview:
    """The report's optional ``judge`` block, as a value."""

    available: bool
    backend: str | None = None
    notes: tuple[ReviewNote, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {"available": self.available}
        if self.backend:
            document["backend"] = self.backend
        if self.notes:
            document["notes"] = [note.to_dict() for note in self.notes]
        return document


#: What a run with no configured backend records. Not an error, not a gate.
UNAVAILABLE = AdvisoryReview(available=False)


def backend_name(backend: object) -> str:
    """How a backend names itself, read from it rather than written here."""
    named = getattr(backend, "name", None)
    if isinstance(named, str) and named:
        return named
    return type(backend).__name__


def review_sections(
    backend: JudgeBackend | None,
    sections: Sequence[tuple[str, str]],
) -> AdvisoryReview:
    """Review each ``(case_id, rendered section)`` pair, or record that none ran.

    Every failure mode collapses to the same fact — no review is available —
    because a judge that could fail a run would be a gate, and it is not one. A
    backend that raises produces :data:`UNAVAILABLE` exactly like a backend that
    was never configured.
    """
    if backend is None or not backend.is_available():
        return UNAVAILABLE

    notes: list[ReviewNote] = []
    for case_id, rendered in sections:
        try:
            prose = backend.complete(rendered, SYSTEM_PROMPT)
        except Exception:  # noqa: BLE001 - an advisory input may never fail a run
            return UNAVAILABLE
        if isinstance(prose, str) and prose.strip():
            notes.append(ReviewNote(case_id=case_id, note=prose.strip()))
    return AdvisoryReview(available=True, backend=backend_name(backend), notes=tuple(notes))
