"""Degradation classification tests (ri-10 wp-lifecycle task 2.1, design D2/D3).

``decide_outcome`` collapses deterministic drift, an absent optional owner, and a
non-succeeded semantic index onto one ``OperationState.DEGRADED`` with no
discriminator. ``classify_degradation`` is the *additive* fix: a pure function
returning four disjoint groups, leaving ``decide_outcome``, ``OperationState``,
and the durable schemas untouched.

The tests are organised by the requirement they pin:

* ``TestDisjointGroups`` — "Groups are disjoint" and totality.
* ``TestProjectionIsInformational`` — "Pending merges do not fail the gate" and
  "Projection drift does not mask blocking drift".
* ``TestAdditive`` — "Existing outcome decision is unaffected", plus the enum and
  schema pins that make the word "additive" checkable rather than aspirational.
* ``TestPurity`` — the classification performs no input or output, and the
  inherited/introduced attribution axis stays outside it (D3).
"""

from __future__ import annotations

import builtins
import itertools
import json
import subprocess
from pathlib import Path

import pytest

import orchestrator
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    SafeError,
    ValidationResult,
    ValidationStatus,
)
from models import OperationState, SemanticIndexReference, SemanticIndexStatus
from registry import (
    API_CONTRACTS,
    DECISIONS_TIMELINE,
    DOCUMENTATION_INVENTORY,
    OPENSPEC_PROJECTION,
)

FULL_SHA = "b" * 40

#: Installed (and promoted) schema copies that pin the durable vocabulary. The
#: additive guarantee is only meaningful if these are the files under test, not a
#: literal list retyped inside the test.
_RUNTIME_SCHEMAS = (
    Path(__file__).resolve().parents[2]
    / "project-context-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
)


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #
def _result(pid: str, status: ProducerStatus, version: str = "1") -> ProducerResult:
    """A ProducerResult satisfying the ri-06 per-status invariants."""
    is_fresh = status is ProducerStatus.FRESH
    return ProducerResult(
        producer_id=pid,
        producer_version=version,
        status=status,
        validations=(
            ValidationResult(
                validation_id=f"{pid}-check",
                status=ValidationStatus.PASSED if is_fresh else ValidationStatus.FAILED,
                summary="fixture",
            ),
        ),
        remediation=() if is_fresh else (Remediation(summary=f"re-run {pid}"),),
        fallback=(
            Fallback(kind=FallbackKind.CUSTOM, reason="fixture drift")
            if status is ProducerStatus.DEGRADED
            else Fallback(kind=FallbackKind.SKIP, reason="fixture absent")
            if status is ProducerStatus.NOT_CONFIGURED
            else None
        ),
        error=(
            SafeError(error_class="FixtureError", summary="fixture failure")
            if status is ProducerStatus.FAILED
            else None
        ),
    )


def _semantic(status: SemanticIndexStatus) -> SemanticIndexReference:
    if status is SemanticIndexStatus.SUCCEEDED:
        return SemanticIndexReference(
            status=status,
            requested_revision=FULL_SHA,
            operation_id="op",
            registry_record_id="rec",
            indexed_revision=FULL_SHA,
        )
    return SemanticIndexReference(
        status=status,
        requested_revision=FULL_SHA,
        fallback=Fallback(kind=FallbackKind.EXACT_SEARCH, reason="unavailable"),
    )


def _ids(results: tuple[ProducerResult, ...]) -> list[str]:
    return [r.producer_id for r in results]


def _groups(breakdown: orchestrator.DegradationBreakdown) -> dict[str, list[str]]:
    return {
        "blocking_drift": _ids(breakdown.blocking_drift),
        "informational_drift": _ids(breakdown.informational_drift),
        "not_configured": _ids(breakdown.not_configured),
        "failed": _ids(breakdown.failed),
    }


# --------------------------------------------------------------------------- #
# Disjointness and totality
# --------------------------------------------------------------------------- #
class TestDisjointGroups:
    def test_one_of_each_lands_in_exactly_one_group(self) -> None:
        results = (
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),
            _result(orchestrator.ARCHITECTURE_PRODUCER_ID, ProducerStatus.NOT_CONFIGURED),
            _result(API_CONTRACTS, ProducerStatus.FAILED),
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
        )
        breakdown = orchestrator.classify_degradation(results, None)

        assert _groups(breakdown) == {
            "blocking_drift": [DOCUMENTATION_INVENTORY],
            "informational_drift": [OPENSPEC_PROJECTION],
            "not_configured": [orchestrator.ARCHITECTURE_PRODUCER_ID],
            "failed": [API_CONTRACTS],
        }
        # Disjointness stated as a set property, not inferred from the table above.
        placements = [
            pid for group in _groups(breakdown).values() for pid in group
        ]
        assert len(placements) == len(set(placements))

    def test_fresh_results_appear_in_no_group(self) -> None:
        results = (
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.FRESH),
            _result(API_CONTRACTS, ProducerStatus.FRESH),
        )
        breakdown = orchestrator.classify_degradation(results, None)
        assert _groups(breakdown) == {
            "blocking_drift": [],
            "informational_drift": [],
            "not_configured": [],
            "failed": [],
        }

    def test_every_non_fresh_result_is_placed_and_no_result_is_duplicated(self) -> None:
        """Totality: over every status combination the groups partition the input."""
        statuses = list(ProducerStatus)
        pids = (DOCUMENTATION_INVENTORY, API_CONTRACTS, OPENSPEC_PROJECTION)
        for combo in itertools.product(statuses, repeat=len(pids)):
            results = tuple(
                _result(pid, status) for pid, status in zip(pids, combo, strict=True)
            )
            breakdown = orchestrator.classify_degradation(results, None)
            placed = [
                r
                for group in (
                    breakdown.blocking_drift,
                    breakdown.informational_drift,
                    breakdown.not_configured,
                    breakdown.failed,
                )
                for r in group
            ]
            expected = [r for r in results if r.status is not ProducerStatus.FRESH]
            assert sorted(_ids(tuple(placed))) == sorted(_ids(tuple(expected))), combo
            assert len(placed) == len(set(id(r) for r in placed)), combo

    def test_empty_input_yields_empty_groups(self) -> None:
        breakdown = orchestrator.classify_degradation((), None)
        assert _groups(breakdown) == {
            "blocking_drift": [],
            "informational_drift": [],
            "not_configured": [],
            "failed": [],
        }

    def test_input_order_is_preserved_within_each_group(self) -> None:
        results = (
            _result("z.later", ProducerStatus.DEGRADED),
            _result("a.earlier", ProducerStatus.DEGRADED),
        )
        breakdown = orchestrator.classify_degradation(results, None)
        assert _ids(breakdown.blocking_drift) == ["z.later", "a.earlier"]

    def test_breakdown_is_a_frozen_slots_dataclass_of_tuples(self) -> None:
        breakdown = orchestrator.classify_degradation(
            (_result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),), None
        )
        assert isinstance(breakdown.blocking_drift, tuple)
        assert isinstance(breakdown.informational_drift, tuple)
        assert isinstance(breakdown.not_configured, tuple)
        assert isinstance(breakdown.failed, tuple)
        assert not hasattr(breakdown, "__dict__")  # slots=True
        with pytest.raises(Exception):
            breakdown.blocking_drift = ()  # type: ignore[misc]

    def test_semantic_reference_is_carried_through_unchanged(self) -> None:
        ref = _semantic(SemanticIndexStatus.FAILED)
        breakdown = orchestrator.classify_degradation((), ref)
        assert breakdown.semantic_index is ref
        assert orchestrator.classify_degradation((), None).semantic_index is None

    def test_semantic_status_never_moves_a_producer_between_groups(self) -> None:
        """The index is external state, not a producer result (D6)."""
        results = (_result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),)
        baseline = _groups(orchestrator.classify_degradation(results, None))
        for status in SemanticIndexStatus:
            breakdown = orchestrator.classify_degradation(results, _semantic(status))
            assert _groups(breakdown) == baseline, status


# --------------------------------------------------------------------------- #
# Projection is informational (D3)
# --------------------------------------------------------------------------- #
class TestProjectionIsInformational:
    def test_default_informational_set_is_derived_from_the_registry_id(self) -> None:
        # Derived from the registry constant, never a retyped string literal.
        assert orchestrator.INFORMATIONAL_PRODUCERS == frozenset({OPENSPEC_PROJECTION})
        assert isinstance(orchestrator.INFORMATIONAL_PRODUCERS, frozenset)

    def test_projection_drift_alone_leaves_blocking_drift_empty(self) -> None:
        results = (
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.FRESH),
            _result(API_CONTRACTS, ProducerStatus.FRESH),
        )
        breakdown = orchestrator.classify_degradation(results, None)
        assert breakdown.blocking_drift == ()
        assert breakdown.failed == ()
        # The findings stay visible so the pending-merge surface is reported.
        assert _ids(breakdown.informational_drift) == [OPENSPEC_PROJECTION]

    def test_projection_drift_does_not_mask_blocking_drift(self) -> None:
        results = (
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),
        )
        breakdown = orchestrator.classify_degradation(results, None)
        assert _ids(breakdown.blocking_drift) == [DOCUMENTATION_INVENTORY]
        assert _ids(breakdown.informational_drift) == [OPENSPEC_PROJECTION]

    def test_a_projection_failure_is_a_failure_not_informational(self) -> None:
        """Informational applies to the producer's *drift*, not to its apparatus."""
        results = (_result(OPENSPEC_PROJECTION, ProducerStatus.FAILED),)
        breakdown = orchestrator.classify_degradation(results, None)
        assert _ids(breakdown.failed) == [OPENSPEC_PROJECTION]
        assert breakdown.informational_drift == ()

    def test_a_projection_not_configured_is_an_absent_owner(self) -> None:
        results = (_result(OPENSPEC_PROJECTION, ProducerStatus.NOT_CONFIGURED),)
        breakdown = orchestrator.classify_degradation(results, None)
        assert _ids(breakdown.not_configured) == [OPENSPEC_PROJECTION]
        assert breakdown.informational_drift == ()

    def test_the_informational_set_is_injectable(self) -> None:
        results = (
            _result(DECISIONS_TIMELINE, ProducerStatus.DEGRADED),
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
        )
        breakdown = orchestrator.classify_degradation(
            results, None, informational_producer_ids=frozenset({DECISIONS_TIMELINE})
        )
        assert _ids(breakdown.informational_drift) == [DECISIONS_TIMELINE]
        assert _ids(breakdown.blocking_drift) == [OPENSPEC_PROJECTION]

    def test_an_empty_informational_set_makes_all_drift_blocking(self) -> None:
        results = (_result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),)
        breakdown = orchestrator.classify_degradation(
            results, None, informational_producer_ids=frozenset()
        )
        assert _ids(breakdown.blocking_drift) == [OPENSPEC_PROJECTION]
        assert breakdown.informational_drift == ()


# --------------------------------------------------------------------------- #
# The classification is additive (D2)
# --------------------------------------------------------------------------- #
def _outcome_oracle(
    statuses: tuple[ProducerStatus, ...], semantic: SemanticIndexStatus | None
) -> OperationState:
    """The documented ``decide_outcome`` rules, restated from its docstring.

    Written from the specification rather than copied from the implementation, so
    a behaviour change in ``decide_outcome`` shows up as a disagreement here.
    """
    if any(s is ProducerStatus.FAILED for s in statuses):
        return OperationState.FAILED
    degraded = any(
        s in (ProducerStatus.DEGRADED, ProducerStatus.NOT_CONFIGURED) for s in statuses
    )
    semantic_ok = semantic is None or semantic is SemanticIndexStatus.SUCCEEDED
    if degraded or not semantic_ok:
        return OperationState.DEGRADED
    return OperationState.SUCCEEDED


class TestAdditive:
    def test_decide_outcome_matches_its_documented_rules_for_every_input(self) -> None:
        pids = ("a", "b", OPENSPEC_PROJECTION)
        semantic_options: list[SemanticIndexStatus | None] = [None, *SemanticIndexStatus]
        for combo in itertools.product(ProducerStatus, repeat=len(pids)):
            results = [
                _result(pid, status) for pid, status in zip(pids, combo, strict=True)
            ]
            for semantic in semantic_options:
                ref = None if semantic is None else _semantic(semantic)
                outcome, error = orchestrator.decide_outcome(results, ref)
                assert outcome is _outcome_oracle(combo, semantic), (combo, semantic)
                assert (error is not None) is (outcome is OperationState.FAILED)

    def test_projection_drift_still_degrades_the_terminal_outcome(self) -> None:
        """The classifier reclassifies for the *gate*; it must not soften ri-06."""
        results = [_result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED)]
        outcome, _error = orchestrator.decide_outcome(results, None)
        assert outcome is OperationState.DEGRADED

    def test_decide_outcome_signature_is_unchanged(self) -> None:
        import inspect

        params = list(inspect.signature(orchestrator.decide_outcome).parameters)
        assert params == ["producer_results", "semantic_index"]

    def test_operation_state_members_match_the_pinned_operation_schema(self) -> None:
        schema = json.loads(
            (_RUNTIME_SCHEMAS / "context-refresh-operation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        assert [s.value for s in OperationState] == schema["properties"]["state"]["enum"]

    def test_operation_state_covers_the_pinned_manifest_refresh_status(self) -> None:
        schema = json.loads(
            (_RUNTIME_SCHEMAS / "context-refresh-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        enum = schema["properties"]["refresh_status"]["enum"]
        assert enum == ["succeeded", "degraded", "failed"]
        assert set(enum) <= {s.value for s in OperationState}

    def test_the_breakdown_introduces_no_new_operation_state(self) -> None:
        results = (
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
        )
        # Both classify differently, yet the terminal state stays the one value
        # the durable schemas allow.
        breakdown = orchestrator.classify_degradation(results, None)
        assert breakdown.blocking_drift and breakdown.informational_drift
        outcome, _ = orchestrator.decide_outcome(results, None)
        assert outcome is OperationState.DEGRADED


# --------------------------------------------------------------------------- #
# Purity
# --------------------------------------------------------------------------- #
class TestPurity:
    def test_classification_performs_no_input_or_output(self) -> None:
        """Every IO primitive is disarmed for the duration of the call.

        Patched and restored by hand rather than with ``monkeypatch``: pytest's own
        failure reporting opens and reads files, so the doors have to be back on
        their hinges before any assertion is allowed to fail.
        """

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("classify_degradation must be IO-free")

        results = (
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
            _result(API_CONTRACTS, ProducerStatus.FAILED),
        )
        semantic = _semantic(SemanticIndexStatus.NOT_CONFIGURED)
        patched = (
            (builtins, "open", builtins.open),
            (subprocess, "run", subprocess.run),
            (Path, "read_text", Path.read_text),
            (Path, "read_bytes", Path.read_bytes),
            (Path, "write_text", Path.write_text),
            (Path, "write_bytes", Path.write_bytes),
            (Path, "open", Path.open),
        )
        for target, name, _original in patched:
            setattr(target, name, _boom)
        try:
            breakdown = orchestrator.classify_degradation(results, semantic)
            error: BaseException | None = None
        except BaseException as exc:  # noqa: BLE001 - re-raised after restoration
            breakdown, error = None, exc
        finally:
            for target, name, original in patched:
                setattr(target, name, original)

        if error is not None:
            raise error
        assert breakdown is not None
        assert _ids(breakdown.blocking_drift) == [DOCUMENTATION_INVENTORY]

    def test_attribution_is_not_folded_into_the_classification(self) -> None:
        """D3: attribution is a separate axis, not a fifth group.

        Inherited-versus-introduced attribution answers *whose fault* a finding
        is; these four groups answer *how severe* it is, and the two are
        independent. It also shells out to git, which the purity pin above
        forbids outright. So it lives in the gate's composition layer: the
        breakdown carries no attribution field, this module exposes no
        attribution vocabulary, and the gate is where both live.
        """
        assert set(orchestrator.DegradationBreakdown.__dataclass_fields__) == {
            "blocking_drift",
            "informational_drift",
            "not_configured",
            "failed",
            "semantic_index",
        }
        assert not [
            name for name in dir(orchestrator) if "attribut" in name.lower()
        ]

        import gate

        assert gate.attribute_producer is not None
        assert {
            gate.ATTRIBUTION_INHERITED,
            gate.ATTRIBUTION_INTRODUCED,
            gate.ATTRIBUTION_INDETERMINATE,
        } == {"inherited", "introduced", "indeterminate"}

    def test_classification_does_not_mutate_its_input(self) -> None:
        results = (
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),
            _result(API_CONTRACTS, ProducerStatus.FRESH),
        )
        before = [r.to_dict() for r in results]
        orchestrator.classify_degradation(results, None)
        assert [r.to_dict() for r in results] == before

    def test_repeated_classification_is_identical(self) -> None:
        results = (
            _result(DOCUMENTATION_INVENTORY, ProducerStatus.DEGRADED),
            _result(OPENSPEC_PROJECTION, ProducerStatus.DEGRADED),
        )
        first = orchestrator.classify_degradation(results, None)
        second = orchestrator.classify_degradation(results, None)
        assert first == second
