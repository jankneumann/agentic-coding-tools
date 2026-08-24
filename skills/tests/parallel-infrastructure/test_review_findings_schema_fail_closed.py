"""ri-14 follow-up: the schema path must fail CLOSED, not open.

ri-14 shipped the canonical review-findings schema with the stated guarantee
that "a drifted finding fails loudly instead of manufacturing false consensus".
Three independent review vendors each found the same hole: every way the check
could fail to *run* was treated as the check *passing*.

* ``review_findings_schema._validate`` returned ``[]`` (i.e. "no errors") when
  ``jsonschema`` was not importable;
* ``review_dispatcher._validate_findings_or_error`` returned the unvalidated
  payload as a success when the schema module was missing or the validator
  raised;
* ``review_dispatcher.CliVendorAdapter._resolve_args`` dropped ``--json-schema``
  and dispatched anyway when the schema could not be derived;
* ``consensus_synthesizer._resolve_canonical_schema`` returned ``None`` for an
  unreadable ``--schema`` path, which made validation a no-op.

An empty error list from a validator that never ran is indistinguishable from a
clean bill of health. These tests pin the fail-closed behaviour; each fails on
the pre-fix tree.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

# conftest.py adds skills/parallel-infrastructure/scripts to sys.path.
import consensus_synthesizer  # type: ignore[import-untyped]
import review_dispatcher  # type: ignore[import-untyped]
import review_findings_schema as rfs  # type: ignore[import-untyped]
from consensus_synthesizer import ConsensusInputError  # type: ignore[import-untyped]
from review_dispatcher import (  # type: ignore[import-untyped]
    CliConfig,
    CliVendorAdapter,
    ModeConfig,
    SchemaInjectionError,
)

_CONFORMING = {
    "findings": [
        {
            "id": 1,
            "type": "correctness",
            "criticality": "high",
            "description": "d",
            "disposition": "fix",
            "axis": "correctness",
            "severity": "critical",
        }
    ]
}


@pytest.fixture
def no_jsonschema(monkeypatch: pytest.MonkeyPatch):
    """Make ``import jsonschema`` raise ImportError inside the modules."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError("simulated: jsonschema not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


# ---------------------------------------------------------------------------
# The validator itself
# ---------------------------------------------------------------------------
class TestValidatorUnavailable:
    def test_missing_jsonschema_raises_rather_than_reporting_clean(
        self, no_jsonschema
    ):
        """"Could not check" must not be reported as "checked and clean"."""
        with pytest.raises(rfs.ValidationUnavailableError):
            rfs.validate_findings_payload(_CONFORMING)

    def test_document_validation_also_raises(self, no_jsonschema):
        with pytest.raises(rfs.ValidationUnavailableError):
            rfs.validate_findings_document(
                {"review_type": "plan", "target": "t", **_CONFORMING}
            )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
class TestDispatcherFailsClosed:
    def test_missing_schema_module_rejects_findings(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """An unloadable schema module must not wave findings through.

        Scenario: the dispatcher runs from a vendored copy without
        review_findings_schema.py beside it. Pre-fix it returned
        ``(findings, None)`` — success — for findings nothing had inspected.
        """
        monkeypatch.setattr(review_dispatcher, "_schema_mod", lambda: None)
        findings, error = review_dispatcher._validate_findings_or_error(
            _CONFORMING
        )
        assert findings is None
        assert error is not None and "schema" in error.lower()

    def test_validator_exception_rejects_findings(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A raising validator is a failed check, not a passed one."""

        class _Boom:
            @staticmethod
            def validate_findings_payload(_payload):
                raise RuntimeError("canonical schema file is corrupt")

        monkeypatch.setattr(review_dispatcher, "_schema_mod", lambda: _Boom)
        findings, error = review_dispatcher._validate_findings_or_error(
            _CONFORMING
        )
        assert findings is None
        assert error is not None and "could not run" in error

    def test_conforming_findings_still_pass(self):
        """The fail-closed posture must not reject valid input."""
        findings, error = review_dispatcher._validate_findings_or_error(
            _CONFORMING
        )
        assert error is None
        assert findings == _CONFORMING


class TestSchemaInjectionFailsClosed:
    @staticmethod
    def _adapter() -> CliVendorAdapter:
        return CliVendorAdapter(
            agent_id="grok-local",
            vendor="grok",
            cli_config=CliConfig(
                command="grok",
                dispatch_modes={
                    "review": ModeConfig(
                        args=["--json-schema", rfs.GROK_SCHEMA_SENTINEL]
                    )
                },
                model_flag="-m",
            ),
        )

    def test_unresolvable_schema_raises_instead_of_dropping_the_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Dropping ``--json-schema`` used to look like graceful degradation.

        It is not: grok only populates ``structuredOutput`` when the flag is
        present, so the "degraded" dispatch reliably produced output the
        dispatcher then rejected as invalid JSON — with the real cause (an
        unresolvable canonical schema) visible only as a warning.
        """

        class _Boom:
            GROK_SCHEMA_SENTINEL = rfs.GROK_SCHEMA_SENTINEL

            @staticmethod
            def grok_schema_arg():
                raise FileNotFoundError("canonical schema missing")

        monkeypatch.setattr(review_dispatcher, "_schema_mod", lambda: _Boom)
        with pytest.raises(SchemaInjectionError):
            self._adapter()._resolve_args(
                ["--json-schema", rfs.GROK_SCHEMA_SENTINEL]
            )

    def test_resolvable_schema_substitutes_the_sentinel(self):
        resolved = self._adapter()._resolve_args(
            ["--json-schema", rfs.GROK_SCHEMA_SENTINEL]
        )
        assert resolved[0] == "--json-schema"
        assert rfs.GROK_SCHEMA_SENTINEL not in resolved
        # The substituted value is the canonical findings schema, not a stub.
        assert "findings" in json.loads(resolved[1])["properties"]


# ---------------------------------------------------------------------------
# Consensus synthesizer
# ---------------------------------------------------------------------------
class TestSynthesizerFailsClosed:
    def test_unreadable_explicit_schema_raises(self, tmp_path: Path):
        """``--schema /missing`` must abort, not silently skip validation."""
        with pytest.raises(ConsensusInputError):
            consensus_synthesizer._resolve_canonical_schema(
                str(tmp_path / "does-not-exist.json")
            )

    def test_unloadable_canonical_schema_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(consensus_synthesizer, "_schema_mod", lambda: None)
        with pytest.raises(ConsensusInputError):
            consensus_synthesizer._resolve_canonical_schema(None)

    def test_missing_jsonschema_raises_during_document_validation(
        self, no_jsonschema, tmp_path: Path
    ):
        with pytest.raises(ConsensusInputError):
            consensus_synthesizer._validate_vendor_document(
                {"review_type": "plan", "target": "t", **_CONFORMING},
                tmp_path / "findings-x.json",
                {"type": "object"},
            )

    def test_canonical_schema_still_resolves_normally(self):
        schema = consensus_synthesizer._resolve_canonical_schema(None)
        assert "findings" in schema["properties"]
