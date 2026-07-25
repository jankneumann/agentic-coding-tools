"""Core registry + invocation contract tests (tasks 1.1-1.3).

These exercise the shared layer with a fake producer so the four canonical
adapters are not a dependency of the core: input fail-closed rules, the four
result outcomes validating against the ri-06 schema, required-vs-optional policy,
and identity verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import registry as reg
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    RepositoryArtifact,
    SafeError,
    ChangeKind,
)
from contract import ContractValidationError, validate_producer_result
import results as R

FULL_SHA = "0" * 40


class _FakeProducer(reg.Producer):
    def __init__(self, spec: reg.ProducerSpec, outcome):
        self.spec = spec
        self._outcome = outcome
        self.calls: list[tuple[str, str]] = []

    def run(self, mode, repository, source_revision):
        self.calls.append((mode, source_revision))
        if callable(self._outcome):
            return self._outcome(mode, repository, source_revision)
        return self._outcome


def _spec(producer_id="test.producer", version="1", optional=False):
    return reg.ProducerSpec(
        producer_id=producer_id,
        producer_version=version,
        owner="test-owner",
        inputs=("**",),
        outputs=(),
        optional=optional,
    )


def _fresh(spec):
    return R.fresh(spec.producer_id, spec.producer_version, validations=[R.passed("v", "ok")])


# --------------------------------------------------------------------------- #
# 1.3 fail-closed input validation
# --------------------------------------------------------------------------- #
def test_unknown_producer_id_fails_closed(tmp_path):
    with pytest.raises(reg.ProducerError, match="unknown producer id"):
        reg.run_producer("nope", "check", tmp_path, FULL_SHA)


def test_invalid_mode_fails_closed(tmp_path):
    spec = _spec()
    reg.register(_FakeProducer(spec, _fresh(spec)))
    with pytest.raises(reg.ProducerError, match="invalid mode"):
        reg.run_producer(spec.producer_id, "rebuild", tmp_path, FULL_SHA)  # type: ignore[arg-type]


def test_invalid_revision_fails_closed(tmp_path):
    spec = _spec()
    reg.register(_FakeProducer(spec, _fresh(spec)))
    with pytest.raises(Exception):
        reg.run_producer(spec.producer_id, "check", tmp_path, "not-a-sha")


def test_missing_repository_fails_closed():
    spec = _spec()
    reg.register(_FakeProducer(spec, _fresh(spec)))
    with pytest.raises(reg.ProducerError, match="not a directory"):
        reg.run_producer(spec.producer_id, "check", Path("/no/such/repo/xyz"), FULL_SHA)


def test_duplicate_registration_fails_closed():
    spec = _spec()
    reg.register(_FakeProducer(spec, _fresh(spec)))
    with pytest.raises(reg.ProducerError, match="duplicate producer id"):
        reg.register(_FakeProducer(spec, _fresh(spec)))


# --------------------------------------------------------------------------- #
# 1.1 four outcomes validate against the installed ri-06 ProducerResult schema
# --------------------------------------------------------------------------- #
def test_clean_result_validates(tmp_path):
    spec = _spec()
    reg.register(_FakeProducer(spec, _fresh(spec)))
    result = reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.FRESH
    validate_producer_result(result)  # no raise


def test_drift_result_validates(tmp_path):
    spec = _spec()
    artifact = RepositoryArtifact("docs/x.md", ChangeKind.MODIFIED, "a" * 64)
    outcome = R.drift(
        spec.producer_id,
        spec.producer_version,
        artifacts=[artifact],
        validations=[R.failed_validation("v", "drift")],
        remediation=[Remediation(summary="regenerate")],
    )
    reg.register(_FakeProducer(spec, outcome))
    result = reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.DEGRADED
    assert result.fallback is not None and result.fallback.kind is FallbackKind.CUSTOM
    assert result.artifacts[0].path == "docs/x.md"


def test_failed_result_validates(tmp_path):
    spec = _spec()
    outcome = R.failed(
        spec.producer_id,
        spec.producer_version,
        error=SafeError("ValueError", "boom"),
        remediation=[Remediation(summary="fix it")],
    )
    reg.register(_FakeProducer(spec, outcome))
    result = reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.FAILED
    assert result.error is not None


def test_optional_not_configured_validates(tmp_path):
    spec = _spec(optional=True)
    outcome = R.not_configured(
        spec.producer_id,
        spec.producer_version,
        fallback=Fallback(FallbackKind.SKIP, "owner absent"),
        remediation=[Remediation(summary="install owner")],
    )
    reg.register(_FakeProducer(spec, outcome))
    result = reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.NOT_CONFIGURED


# --------------------------------------------------------------------------- #
# 1.3 policy + identity + exception guard
# --------------------------------------------------------------------------- #
def test_required_producer_cannot_be_not_configured(tmp_path):
    spec = _spec(optional=False)
    outcome = R.not_configured(
        spec.producer_id,
        spec.producer_version,
        fallback=Fallback(FallbackKind.SKIP, "owner absent"),
        remediation=[Remediation(summary="install owner")],
    )
    reg.register(_FakeProducer(spec, outcome))
    result = reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.FAILED
    assert result.error is not None
    assert "not-configured" in result.error.summary


def test_adapter_exception_becomes_failed_result(tmp_path):
    spec = _spec()

    def boom(mode, repository, source_revision):
        raise RuntimeError("kaboom /Users/secret/abs/path")

    reg.register(_FakeProducer(spec, boom))
    result = reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.FAILED
    assert result.error is not None
    assert result.error.error_class == "RuntimeError"


def test_mismatched_identity_fails_closed(tmp_path):
    spec = _spec()
    wrong = ProducerResult("other.id", "1", ProducerStatus.FRESH)
    reg.register(_FakeProducer(spec, wrong))
    with pytest.raises(reg.ProducerError, match="mismatched id"):
        reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)


def test_mismatched_version_fails_closed(tmp_path):
    spec = _spec(version="2")
    wrong = ProducerResult(spec.producer_id, "1", ProducerStatus.FRESH)
    reg.register(_FakeProducer(spec, wrong))
    with pytest.raises(reg.ProducerError, match="version"):
        reg.run_producer(spec.producer_id, "check", tmp_path, FULL_SHA)


def test_schema_invalid_dict_rejected():
    # A bare dict missing required keys must not validate.
    with pytest.raises(ContractValidationError):
        from contract import validate_producer_result_dict

        validate_producer_result_dict({"producer_id": "x"})
