"""Stable producer registry and fail-closed invocation (ri-05 D1/D2/D3).

The shared layer owns registration, invocation, input/result validation, and
deterministic ordering. Domain owners retain parsing and rendering. This module
never defines a result model — every adapter returns the ri-06
:class:`ProducerResult`, which :func:`run_producer` validates against the
installed schema before returning.

Public surface:

* :data:`Mode` — the two producer modes, ``generate`` and ``check``.
* :class:`ProducerSpec` — registration metadata (owner, version, inputs, outputs).
* :class:`Producer` — adapter base class; subclasses implement ``run``.
* :func:`list_producers` — specs ordered by stable producer id.
* :func:`run_producer` — validate inputs, dispatch, enforce policy, validate result.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from _runtime import (
    ProducerResult,
    ProducerStatus,
    Remediation,
    SafeError,
    ensure_git_revision,
)
from contract import validate_producer_result
from results import failed

Mode = Literal["generate", "check"]
_VALID_MODES: frozenset[str] = frozenset({"generate", "check"})

# Stable v1 producer ids (design D1). Ordering is by this id.
DOCUMENTATION_INVENTORY = "documentation.inventory"
API_CONTRACTS = "api.contracts"
DECISIONS_TIMELINE = "decisions.timeline"
OPENSPEC_PROJECTION = "openspec.projection"


class ProducerError(Exception):
    """A fail-closed registry error raised before any adapter runs.

    Distinct from a producer *result* of ``failed``: these are caller mistakes
    (unknown id, invalid mode, invalid revision, missing repository) surfaced
    before publication rather than swallowed into a result object.
    """


@dataclass(frozen=True, slots=True)
class ProducerSpec:
    """Immutable registration metadata for one deterministic producer.

    It deliberately does not duplicate any ri-06 result class; it only describes
    identity, canonical ownership, declared inputs, and declared managed outputs.
    """

    producer_id: str
    producer_version: str
    owner: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    optional: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "producer_id": self.producer_id,
            "producer_version": self.producer_version,
            "owner": self.owner,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "optional": self.optional,
        }


class Producer(abc.ABC):
    """Base class for a deterministic context producer adapter.

    Subclasses declare a :attr:`spec` and implement :meth:`run`. They call their
    canonical domain owner (a Python entry point or a stable command boundary)
    and return an ri-06 :class:`ProducerResult`. They MUST NOT persist durable
    operations, mutate main outside their declared managed outputs, or use file
    modification times to decide freshness.
    """

    spec: ProducerSpec

    @abc.abstractmethod
    def run(self, mode: Mode, repository: Path, source_revision: str) -> ProducerResult:
        """Generate or check for *repository* at the exact *source_revision*."""
        raise NotImplementedError


# Populated at import time by ``register`` calls in ``_default_registry``.
_REGISTRY: dict[str, Producer] = {}


def register(producer: Producer) -> None:
    """Register *producer*, rejecting a duplicate or mismatched producer id."""
    producer_id = producer.spec.producer_id
    if producer_id in _REGISTRY:
        raise ProducerError(f"duplicate producer id registered: {producer_id!r}")
    _REGISTRY[producer_id] = producer


def _ensure_default_registry() -> None:
    """Lazily register the four canonical producers on first use.

    Import is deferred so a syntax/​import error in one adapter surfaces on use
    with a clear traceback rather than at module import of the whole package.
    """
    if _REGISTRY:
        return
    # Imported lazily to avoid a circular import (adapters import this module).
    from producer_documentation import DocumentationInventoryProducer
    from producer_api_contracts import ApiContractsProducer
    from producer_decisions import DecisionsTimelineProducer
    from producer_openspec import OpenSpecProjectionProducer

    for producer in (
        DocumentationInventoryProducer(),
        ApiContractsProducer(),
        DecisionsTimelineProducer(),
        OpenSpecProjectionProducer(),
    ):
        register(producer)


def registry() -> Mapping[str, Producer]:
    """Return the live producer registry (read-only view), registering defaults."""
    _ensure_default_registry()
    return dict(_REGISTRY)


def list_producers() -> tuple[ProducerSpec, ...]:
    """Return all producer specs ordered by stable producer id (D1)."""
    _ensure_default_registry()
    return tuple(sorted((p.spec for p in _REGISTRY.values()), key=lambda s: s.producer_id))


def _bounded_safe_error(exc: BaseException) -> SafeError:
    """Reduce an adapter exception to a bounded, machine-safe error.

    Only the exception class name and its ``str`` are kept, and the summary is
    length-bounded. Tracebacks, environment values, subprocess output, and
    absolute machine paths are never persisted (design "Failure Behavior").
    """
    summary = str(exc).strip() or exc.__class__.__name__
    if len(summary) > 300:
        summary = summary[:297] + "..."
    return SafeError(error_class=exc.__class__.__name__, summary=summary)


def run_producer(
    producer_id: str,
    mode: Mode,
    repository: Path,
    source_revision: str,
) -> ProducerResult:
    """Validate inputs, dispatch to the owner, enforce policy, validate result.

    Fail-closed before dispatch on: unknown ``producer_id``, an invalid ``mode``,
    a non-full-SHA ``source_revision``, or a missing repository. After dispatch,
    a required producer that returns ``not-configured`` becomes ``failed`` (policy
    violation), and every result is validated against the ri-06 schema and its
    declared identity before it is returned.
    """
    _ensure_default_registry()
    producer = _REGISTRY.get(producer_id)
    if producer is None:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise ProducerError(f"unknown producer id {producer_id!r}; known: {known}")
    if mode not in _VALID_MODES:
        raise ProducerError(
            f"invalid mode {mode!r}; expected one of {sorted(_VALID_MODES)}"
        )
    ensure_git_revision(source_revision)
    repository = Path(repository)
    if not repository.is_dir():
        raise ProducerError(f"repository is not a directory: {repository}")

    spec = producer.spec
    try:
        result = producer.run(mode, repository, source_revision)
    except ProducerError:
        # A fail-closed input error inside the adapter propagates as-is.
        raise
    except BaseException as exc:  # noqa: BLE001 - adapters must never crash the caller
        result = failed(
            spec.producer_id,
            spec.producer_version,
            error=_bounded_safe_error(exc),
            remediation=[
                Remediation(
                    summary=(
                        f"Investigate the {spec.producer_id} producer against its "
                        "canonical owner and re-run in check mode."
                    ),
                )
            ],
        )

    result = _enforce_policy(spec, result)
    _verify_identity(spec, result)
    validate_producer_result(result)
    return result


def _enforce_policy(spec: ProducerSpec, result: ProducerResult) -> ProducerResult:
    """A required producer cannot legitimately be ``not-configured`` (design)."""
    if (
        result.status is ProducerStatus.NOT_CONFIGURED
        and not spec.optional
    ):
        return failed(
            spec.producer_id,
            spec.producer_version,
            error=SafeError(
                error_class="RegistryPolicyError",
                summary=(
                    f"required producer {spec.producer_id!r} returned not-configured"
                ),
            ),
            remediation=list(result.remediation)
            or [
                Remediation(
                    summary=(
                        f"Configure the canonical owner for {spec.producer_id!r} or "
                        "mark the producer optional in the registry."
                    )
                )
            ],
        )
    return result


def _verify_identity(spec: ProducerSpec, result: ProducerResult) -> None:
    """Reject a result whose identity does not match its registration."""
    if result.producer_id != spec.producer_id:
        raise ProducerError(
            f"producer {spec.producer_id!r} returned mismatched id "
            f"{result.producer_id!r}"
        )
    if result.producer_version != spec.producer_version:
        raise ProducerError(
            f"producer {spec.producer_id!r} returned version "
            f"{result.producer_version!r}, expected {spec.producer_version!r}"
        )


# Field re-exported so ri-07 can enumerate declared managed outputs without
# importing individual adapters.
__all__ = [
    "Mode",
    "Producer",
    "ProducerSpec",
    "ProducerError",
    "DOCUMENTATION_INVENTORY",
    "API_CONTRACTS",
    "DECISIONS_TIMELINE",
    "OPENSPEC_PROJECTION",
    "register",
    "registry",
    "list_producers",
    "run_producer",
]
