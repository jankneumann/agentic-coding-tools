"""Scope compliance, measured on responses that are allowed to misbehave.

A scope gate run against a well-behaved server proves that the server behaved.
The layer that actually protects the agent is ri-12's own client-side deny
re-check, and no amount of server-side correctness exercises it. So the corpus
carries three adversarial recorded bodies and this file drives ri-12's real
``collect_semantic_context`` over them — the module is loaded here in the *test*,
through the ``search`` seam its own tests use, so ``packages/`` still never
imports ``skills/`` at runtime.

That gives two independent things, and both are needed:

* **The scorer can fail.** Hand-built arms carrying a leak, a denied path, and a
  mismatched expectation each fail, with the offending path named. A gate nobody
  has seen fail is not evidence that it works.
* **The runtime passes.** The same scorer, fed what ri-12 actually renders from
  the adversarial bodies, finds zero violations and finds the leaked hits
  recorded as ``scope_filtered`` omissions. That is a measurement of ri-12's
  defense in depth rather than a restatement of it.

The apparatus guard is asserted the same way. ``_normalize_read_scope``
(``semantic_context.py:919``) is not injectable and falls back to unnormalized
globs at ``:934-938`` when its sibling skill is missing. A run in that state must
be an ``apparatus_failure``, never a clean-looking compliance number computed
under semantics the report does not claim.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"

RI12_SCRIPTS = REPO_ROOT / "skills" / "context-engineering" / "scripts"
IMPACT_SCRIPTS = REPO_ROOT / "skills" / "validate-packages" / "scripts"

for _path in (SRC, RI12_SCRIPTS, IMPACT_SCRIPTS):
    if str(_path) not in sys.path:  # pragma: no cover - import plumbing
        sys.path.insert(0, str(_path))

import semantic_context as ri12  # noqa: E402
from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, CaseLabels, Scope  # noqa: E402
from context_eval.producers import scope_adapter as adapter_module  # noqa: E402
from context_eval.scoring import scope as scoring  # noqa: E402
from context_eval.scoring.arms import (  # noqa: E402
    Arm,
    RenderedHit,
    RenderedOmission,
    arm_from_section,
)


@dataclass(frozen=True)
class _Scopes:
    """ri-08's ``IndexScopes``, duck-typed the way ri-12 consumes it.

    ``allows`` delegates to the scorer's own matcher so the runtime under
    measurement and the measurement itself agree on glob semantics — which is
    the property ``test_the_glob_matcher_agrees_with_the_repositorys_own`` proves
    against ri-08's implementation rather than assuming.
    """

    read_allow: tuple[str, ...]
    deny: tuple[str, ...]

    def allows(self, file_path: str) -> bool:
        return scoring.allows(file_path, self.read_allow, self.deny)


def _corpus():
    return load_corpus(CORPUS_ROOT)


def _scope_thresholds():
    gate = next(g for g in _corpus().gates if g.kind == "scope_compliance")
    return gate.thresholds


def _recorded_body(case) -> dict:
    return json.loads((CORPUS_ROOT / case.recorded_response.path).read_text(encoding="utf-8"))


def _drive_ri12(case) -> tuple[Arm, dict]:
    """Render *case*'s recorded response through ri-12, exactly as a job would.

    Returns the rendered arm and the outbound request body ri-12 built, so
    inbound and outbound compliance are measured from one run rather than from
    two that might have diverged.
    """
    body = _recorded_body(case)
    revision = body["request"]["source_revision"]
    captured: dict = {}

    def search(request_body):
        captured.update(request_body)
        return {"status": "ok", "response": body}

    def git(_repository, argv):
        """``--show-toplevel`` -> the root, ``HEAD`` -> the recorded revision.

        A clean ``status --porcelain`` is returned as ``""``: the recorded
        responses describe an index built at exactly this revision, so a dirty
        tree would short-circuit into ``stale`` before the response was ever
        consulted and the case would measure the fixture's own worktree instead.
        """
        if "--show-toplevel" in argv:
            return str(REPO_ROOT)
        if "HEAD" in argv:
            return revision
        return ""

    runtime = ri12.SemanticContextRuntime(
        search=search,
        detect=lambda: {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "http"},
        git=git,
        load_package=lambda *_a: {"scope": {"read_allow": list(case.scope.read_allow)}},
        index_scopes=lambda _package: _Scopes(case.scope.read_allow, case.scope.deny),
        load_checkpoint=lambda *_a, **_k: None,
        env={"SEMANTIC_CONTEXT_INJECTION": "1"},
    )
    request = ri12.SemanticContextRequest(
        repository=REPO_ROOT,
        query=case.query,
        consumer=case.consumer,
        change_id="gate-semantic-context-default-enablement",
        package_id="wp-scoring",
    )
    result = ri12.collect_semantic_context(request, runtime)
    assert result.requested_revision in (revision, ri12.UNRESOLVED_REVISION)
    return arm_from_section(result.to_dict()), captured


def _case(
    *,
    case_id: str = "S1",
    read_allow: tuple[str, ...] = ("agent-coordinator/src/**",),
    deny: tuple[str, ...] = ("**/.venv/**",),
) -> Case:
    return Case(
        case_id=case_id,
        consumer="implement-feature",
        query="anything",
        category="control",
        scope=Scope(read_allow=read_allow, deny=deny),
        labels=CaseLabels(expected_files=(), must_touch=(), evidence_spans=()),
        rationale="fixture",
        source_path=f"cases/{case_id}.yaml",
    )


def _arm(*paths: str, omissions: tuple[RenderedOmission, ...] = ()) -> Arm:
    return Arm(
        arm="semantic",
        status="injected",
        hits=tuple(RenderedHit(path, 1, 2) for path in paths),
        omissions=omissions,
    )


# --------------------------------------------------------------------------
# the glob semantics are the repository's, not this module's invention
# --------------------------------------------------------------------------


def test_the_glob_matcher_agrees_with_the_repositorys_own() -> None:
    """``packages/`` may not import ``skills/``, so agreement is proved, not assumed.

    A silent divergence in glob matching would make every number this gate
    produces describe a different scope from the one ri-12 enforced.
    """
    from context_impact import matches as ri08_matches

    table = (
        ("agent-coordinator/src/locks.py", "agent-coordinator/src/**"),
        ("agent-coordinator/src/a/b/c.py", "agent-coordinator/src/**"),
        ("skills/autopilot/SKILL.md", "agent-coordinator/src/**"),
        ("setup.py", "**/*.py"),
        ("pkg/mod.py", "**/*.py"),
        ("pkg/.venv/lib/x.py", "**/.venv/**"),
        ("pkg/mod.py", "**/.venv/**"),
        ("Skills/Autopilot/SKILL.md", "skills/**"),
        (
            "skills/parallel-infrastructure/scripts/tests/t.py",
            "skills/parallel-infrastructure/scripts/tests/**",
        ),
    )
    for path, pattern in table:
        assert scoring.matches(path, pattern) == ri08_matches(path, pattern), (path, pattern)


def test_deny_beats_allow_even_when_both_match() -> None:
    assert scoring.allows("a/b.py", ("a/**",), ()) is True
    assert scoring.allows("a/b.py", ("a/**",), ("a/**",)) is False
    assert scoring.allows("a/b.py", (), ()) is False


# --------------------------------------------------------------------------
# the scorer can fail, and names what failed
# --------------------------------------------------------------------------


def test_exactly_one_out_of_scope_result_fails_the_gate_and_names_the_path() -> None:
    """The spec scenario, literally. Two clean hits do not dilute one leak."""
    case = _case()
    arm = _arm(
        "agent-coordinator/src/locks.py",
        "skills/autopilot/SKILL.md",
        "agent-coordinator/src/work_queue.py",
    )
    result = scoring.score_case(case, arm)
    assert result.violations == ("skills/autopilot/SKILL.md",)

    gate = scoring.score_scope([result], _scope_thresholds(), scope_adapter="resolved")
    assert gate.verdict == "fail"
    assert scoring.SCOPE_VIOLATION in gate.fail_reasons
    assert gate.violating_paths == ("skills/autopilot/SKILL.md",)


def test_a_positive_declared_tolerance_still_cannot_admit_a_violation() -> None:
    """Zero tolerance is structural: editing the manifest cannot loosen it.

    Deliberately the one place the harness does not defer to corpus data. If the
    tolerance were read from the manifest, "allow three leaks" would be a
    reviewable one-line diff, and design D8 says there is no tolerance to
    configure.
    """
    thresholds = dict(_scope_thresholds())
    thresholds[scoring.MAX_RENDERED_VIOLATIONS] = 3
    result = scoring.score_case(_case(), _arm("skills/autopilot/SKILL.md"))
    gate = scoring.score_scope([result], thresholds, scope_adapter="resolved")
    assert gate.verdict == "fail"


def test_a_denied_path_rendered_at_all_fails_deny_precedence() -> None:
    case = _case(
        read_allow=("skills/parallel-infrastructure/**",),
        deny=("skills/parallel-infrastructure/scripts/tests/**",),
    )
    arm = _arm("skills/parallel-infrastructure/scripts/tests/test_dag_scheduler.py")
    result = scoring.score_case(case, arm)
    assert result.deny_precedence is False
    gate = scoring.score_scope([result], _scope_thresholds(), scope_adapter="resolved")
    assert gate.verdict == "fail"


def test_a_denied_path_dropped_without_an_omission_record_fails() -> None:
    """Absence from ``hits`` is half the requirement; the record is the other half."""
    case = _case(
        read_allow=("skills/parallel-infrastructure/**",),
        deny=("skills/parallel-infrastructure/scripts/tests/**",),
    )
    denied = "skills/parallel-infrastructure/scripts/tests/test_dag_scheduler.py"
    silent = _arm(
        "skills/parallel-infrastructure/scripts/scope_checker.py",
        omissions=(RenderedOmission(denied, 12, 13, "duplicate_exact"),),
    )
    assert scoring.deny_precedence_honored(silent, case.scope) is False

    recorded = _arm(
        "skills/parallel-infrastructure/scripts/scope_checker.py",
        omissions=(RenderedOmission(denied, 12, 13, scoring.SCOPE_FILTERED),),
    )
    assert scoring.deny_precedence_honored(recorded, case.scope) is True


def test_a_widened_outbound_scope_fails_fidelity() -> None:
    """A clean section can still have leaked the job's boundary to the service."""
    case = _case()
    honest = {"scope": {"kind": "explicit", "read_allow": ["agent-coordinator/src/**"],
                        "deny": ["**/.venv/**"]}}
    widened = {"scope": {"kind": "explicit", "read_allow": ["**"], "deny": []}}
    assert scoring.outbound_scope_fidelity(honest, case.scope) is True
    assert scoring.outbound_scope_fidelity(widened, case.scope) is False

    result = scoring.score_case(case, _arm("agent-coordinator/src/locks.py"),
                                request_body=widened)
    gate = scoring.score_scope([result], _scope_thresholds(), scope_adapter="resolved")
    assert gate.verdict == "fail"
    assert gate.measured["outbound_scope_fidelity"] == 0.0


def test_an_implicit_scope_kind_is_not_fidelity() -> None:
    case = _case()
    implicit = {"scope": {"kind": "work_package", "read_allow": list(case.scope.read_allow),
                          "deny": list(case.scope.deny)}}
    assert scoring.outbound_scope_fidelity(implicit, case.scope) is False


# --------------------------------------------------------------------------
# a degraded adapter is an apparatus failure, never a silent pass
# --------------------------------------------------------------------------


def test_a_degraded_adapter_fails_even_with_perfect_compliance() -> None:
    result = scoring.score_case(_case(), _arm("agent-coordinator/src/locks.py"))
    assert result.compliant is True

    clean = scoring.score_scope([result], _scope_thresholds(), scope_adapter="resolved")
    assert clean.verdict == "pass"

    degraded = scoring.score_scope([result], _scope_thresholds(), scope_adapter="degraded")
    assert degraded.verdict == "fail"
    assert scoring.APPARATUS_FAILURE in degraded.fail_reasons
    assert degraded.scope_adapter == "degraded"


def test_an_unknown_adapter_state_is_refused_rather_than_treated_as_resolved() -> None:
    result = scoring.score_case(_case(), _arm("agent-coordinator/src/locks.py"))
    with pytest.raises(scoring.ScopeScoringError):
        scoring.score_scope([result], _scope_thresholds(), scope_adapter="probably-fine")


def test_the_real_adapter_resolves_in_this_checkout() -> None:
    """If this fails, every scope number in a report from this tree is degraded."""
    resolved = adapter_module.resolve_scope_adapter(
        adapter_module.adapter_dir_for(REPO_ROOT)
    )
    assert resolved.status == adapter_module.RESOLVED, resolved.detail
    assert resolved.normalize(("a/**",), ("b/**",)) == (("a/**",), ("b/**",))


def test_an_absent_adapter_degrades_to_unnormalized_globs(tmp_path: Path) -> None:
    """The degraded branch returns ri-12's real fallback, not a sanitized one.

    ``_normalize_read_scope:934-938`` hands back the raw globs, so a scope that
    ri-09 would have REJECTED as self-cancelling survives here — which is exactly
    why the run has to fail rather than report the number it computed.
    """
    degraded = adapter_module.resolve_scope_adapter(tmp_path)
    assert degraded.status == adapter_module.DEGRADED
    assert degraded.detail
    self_cancelling = (("a/**",), ("a/**",))
    assert degraded.normalize(*self_cancelling) == self_cancelling

    resolved = adapter_module.resolve_scope_adapter(
        adapter_module.adapter_dir_for(REPO_ROOT)
    )
    with pytest.raises(adapter_module.ScopeSelfCancellingError):
        resolved.normalize(*self_cancelling)


def test_no_configured_adapter_location_degrades_rather_than_raising() -> None:
    """The run must reach the point of writing a report that says why it failed."""
    assert adapter_module.resolve_scope_adapter(None).status == adapter_module.DEGRADED


# --------------------------------------------------------------------------
# the runtime under measurement: ri-12 on the adversarial bodies
# --------------------------------------------------------------------------


def test_ri12_filters_the_leaked_hit_and_keeps_the_rest() -> None:
    """``ADV-LEAKED-HIT``: the server said ``allowed``; the client disagreed."""
    case = _corpus().case_by_id("ADV-LEAKED-HIT")
    leaked = "skills/autopilot/SKILL.md"
    assert leaked in {r["file_path"] for r in _recorded_body(case)["results"]}

    arm, request_body = _drive_ri12(case)
    assert arm.status == "injected"
    assert leaked not in arm.rendered_files
    assert leaked in arm.scope_filtered_paths()
    assert len(arm.hits) == case.expectation.rendered_hits, (
        "rejecting the whole response would pass a zero-violation check "
        "while destroying the feature"
    )

    result = scoring.score_case(case, arm, request_body=request_body)
    assert result.violations == ()
    assert result.outbound_fidelity is True
    gate = scoring.score_scope([result], _scope_thresholds(), scope_adapter="resolved")
    assert gate.verdict == "pass"


def test_ri12_honours_deny_precedence_on_the_highest_scoring_hit() -> None:
    """``ADV-DENY-PRECEDENCE``: in ``read_allow``, excluded only by a deny glob.

    The leaked hit carries the highest similarity in the body, so an
    implementation that filtered after truncating to the budget would render it.
    """
    case = _corpus().case_by_id("ADV-DENY-PRECEDENCE")
    body = _recorded_body(case)
    denied = body["results"][0]["file_path"]
    assert body["results"][0]["similarity"] == max(r["similarity"] for r in body["results"])
    assert scoring.matches(denied, case.scope.read_allow[0]), "the point is that allow matches too"

    arm, request_body = _drive_ri12(case)
    assert denied not in arm.rendered_files
    assert denied in arm.scope_filtered_paths()
    assert len(arm.hits) == case.expectation.rendered_hits

    result = scoring.score_case(case, arm, request_body=request_body)
    assert result.violations == ()
    assert result.deny_precedence is True


def test_ri12_reports_an_entirely_filtered_response_as_a_scope_event() -> None:
    """``ADV-ALL-HITS-FILTERED``: a scope decision, not a relevance one."""
    case = _corpus().case_by_id("ADV-ALL-HITS-FILTERED")
    arm, _ = _drive_ri12(case)
    assert arm.status == "fallback"
    assert (arm.fallback_trigger, arm.fallback_reason) == (
        case.expectation.trigger,
        case.expectation.reason,
    )
    assert arm.hits == ()
    assert scoring.score_case(case, arm).expectation_honored is True


@pytest.mark.parametrize(
    "case_id",
    [
        "FC-NO-INDEX-AT-REVISION",
        "FC-REVISION-MISMATCH",
        "FC-SCOPE-REJECTED",
        "FC-UNKNOWN-STATE",
    ],
)
def test_every_fail_closed_case_gets_its_declared_trigger_and_reason(case_id: str) -> None:
    """The PAIR, never just the trigger: ri-12's state mapping is total."""
    case = _corpus().case_by_id(case_id)
    arm, _ = _drive_ri12(case)
    assert arm.status == "fallback"
    assert (arm.fallback_trigger, arm.fallback_reason) == (
        case.expectation.trigger,
        case.expectation.reason,
    )
    assert arm.hits == ()
    assert scoring.score_case(case, arm).expectation_honored is True


def test_an_unknown_state_carrying_results_still_renders_nothing() -> None:
    """A client that read ``results`` before checking ``state`` would leak them."""
    case = _corpus().case_by_id("FC-UNKNOWN-STATE")
    assert _recorded_body(case)["results"], "the fixture must offer something to leak"
    arm, _ = _drive_ri12(case)
    assert arm.hits == ()


def test_a_case_with_no_expectation_reports_none_not_true() -> None:
    """"Made no claim" and "claim held" are different facts about a run."""
    assert scoring.expectation_honored(_case(), _arm("agent-coordinator/src/locks.py")) is None


def test_a_wrong_reason_under_the_right_trigger_is_not_honoured() -> None:
    case = _corpus().case_by_id("FC-NO-INDEX-AT-REVISION")
    wrong = Arm(
        arm="semantic",
        status="fallback",
        fallback_trigger=case.expectation.trigger,
        fallback_reason="service_unavailable",
    )
    assert scoring.expectation_honored(case, wrong) is False


# --------------------------------------------------------------------------
# gate composition hygiene
# --------------------------------------------------------------------------


def test_a_missing_threshold_is_an_error_not_a_default() -> None:
    result = scoring.score_case(_case(), _arm("agent-coordinator/src/locks.py"))
    with pytest.raises(scoring.ScopeScoringError):
        scoring.score_scope([result], {}, scope_adapter="resolved")


def test_scoring_zero_cases_is_an_error_not_a_vacuous_pass() -> None:
    with pytest.raises(scoring.ScopeScoringError):
        scoring.score_scope([], _scope_thresholds(), scope_adapter="resolved")
