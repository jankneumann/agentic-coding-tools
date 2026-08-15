"""Composed deterministic context drift gate (ri-10, design D1/D5/D6/D7).

One command that answers one question: *does this revision carry deterministic
context drift a reviewer must fix before merge?* It composes three arms that
exist already and adds the single thing none of them expresses — an exit code
derived from a classification rather than from a collapsed terminal state:

* **deterministic producers** — via :func:`orchestrator.check`, which runs every
  registered producer in ``check`` mode and writes neither the durable store nor
  the working tree. Dispatch is not re-implemented here;
* **architecture freshness** — via the orchestrator's architecture seam, whose
  default compares *committed* provenance with ``check_freshness`` and fails
  closed on unverifiable evidence (D4). Consumed, not re-implemented;
* **work-package context impact** — ri-08's ``validate_context_impact``, invoked
  over the ``work-packages.yaml`` files present in the diff under test and
  **never** with ``--strict-legacy`` (D7).

Ownership boundary. This module owns *composition, classification wiring, and
rendering*. It owns no producer, no result model, and no schema. ``cli.py gate``
is a thin argument-parsing wrapper and ``make context-drift-gate`` is a thin
``make`` call, so a CI failure reproduces verbatim in a developer checkout —
which is the point of putting the rendering in Python instead of assembling it
from shell over job output (D1).

Exit codes (D5), derived from :func:`orchestrator.classify_degradation`'s four
disjoint groups and *not* from ``OperationState``:

=================================================  ====
condition                                          exit
=================================================  ====
any ``failed`` producer or apparatus failure       1
any ``blocking_drift``, no failures                2
only ``informational_drift`` / ``not_configured``  0
all fresh                                          0
=================================================  ====

A surviving ``not-configured`` can only come from an *optional* producer —
``registry._enforce_policy`` rewrites a *required* producer's ``not-configured``
to ``failed`` before it ever reaches here — so it is external degradation and by
decision must not block.

Two reconciliations are recorded rather than left implicit.

**Missing architecture provenance exits 2, not 1.** The exit table's "or
unverifiable architecture provenance" clause reads, in isolation, as though a
missing baseline were an apparatus failure. It is not: D4 maps missing,
malformed, and schema-invalid provenance to ``R.drift``, and the spec scenario
"Missing provenance blocks" requires *the drift exit code*. The ``architecture``
report block still names it ``unverifiable``, keeping "no baseline at all"
distinguishable from "digests disagree", but it is blocking drift. Exit ``1``
covers the case where the architecture producer could not reach a verdict at
all, which arrives as a ``failed`` result.

**The validator's exit ``2`` becomes the gate's exit ``1``.**
``validate_context_impact.py`` returns ``2`` for *usage* errors — a missing file
or an unloadable rule table — which collides with the drift convention where
``2`` means drift. Passing it through would report an apparatus failure as
actionable drift and send a reviewer looking for a stale artifact that does not
exist (D7).

The gate never constructs a semantic indexer and never probes Postgres or an
embedder, even when complete configuration is present in the environment. It
reports ``{"status": "not-attempted"}`` — deliberately not a
``SemanticIndexStatus`` member, because those describe *probe outcomes* and
``not-configured`` would assert that a probe found no configuration. Making no
currency claim is how "stale semantic results are never presented as current" is
satisfied by construction (D6).
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orchestrator
from _runtime import ProducerResult, ProducerStatus, ValidationStatus
from registry import list_producers

# ri-08 lives in ``validate-packages``. Its detector layer is git-free, which is
# what lets the gate hand it an explicit changed-file list instead of a range.
_VALIDATE_PACKAGES_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "validate-packages" / "scripts"
)
if _VALIDATE_PACKAGES_SCRIPTS.is_dir() and str(_VALIDATE_PACKAGES_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_VALIDATE_PACKAGES_SCRIPTS))

from context_impact import SURFACES  # noqa: E402
import validate_context_impact  # noqa: E402

#: Contract version of the emitted report. Pinned by the schema's ``const``.
GATE_SCHEMA_VERSION = 1

#: The semantic block's fixed reason. A constant so a repeat gate run at the same
#: revision is byte-identical, and so the justification is not retyped per call.
SEMANTIC_NOT_ATTEMPTED_REASON = (
    "deterministic-only gate; semantic availability is not deterministic drift"
)
SEMANTIC_STATUS_NOT_ATTEMPTED = "not-attempted"

#: Synthetic producer identity for the context-impact arm. It is not a registered
#: producer — it is a validator — but the report's exit-code derivation reads the
#: four groups and nothing else, so representing its verdict as a group member
#: keeps exactly one place where an exit code is decided.
CONTEXT_IMPACT_PRODUCER_ID = "context.impact"
CONTEXT_IMPACT_OWNER = "validate-packages"

#: Canonical owner of the architecture producer, which is a separate seam rather
#: than an ri-05 registry entry (mirrors ``cli._owner_by_producer_id``).
ARCHITECTURE_OWNER = "refresh-architecture"

#: The committed provenance document the architecture arm compares against.
ARCHITECTURE_PROVENANCE_PATH = "docs/architecture-analysis/architecture.provenance.json"

#: Freshness reason codes that mean "there is no usable committed baseline".
#: ``_default_architecture_producer`` renders each drift validation summary as
#: ``"<CODE>: <detail>"``, so a prefix match recovers the code without importing
#: ``refresh-architecture`` (which may legitimately be absent).
_UNVERIFIABLE_CODES = ("PROVENANCE_MISSING", "PROVENANCE_INVALID")

#: Default base ref for the diff under test.
DEFAULT_BASE = "main"

WORK_PACKAGES_FILENAME = "work-packages.yaml"

OUTCOME_FRESH = "fresh"
OUTCOME_DRIFT = "drift"
OUTCOME_FAILED = "failed"

EXIT_FRESH = 0
EXIT_FAILED = 1
EXIT_DRIFT = 2

#: Bounded like every other reason string in this contract family.
_MAX_REASON = 300

#: ``orchestrator.check``'s call shape, injectable so composition is testable
#: without running real producers against a real checkout.
CheckRunner = Callable[..., orchestrator.RefreshResult]
#: ``(repository, base) -> changed repository-relative paths``.
ChangedFilesResolver = Callable[[Path, str], "tuple[str, ...]"]
#: ``argv -> (exit_code, stdout)`` for one ri-08 validator invocation.
ContextImpactRunner = Callable[[Sequence[str]], "tuple[int, str]"]


class GateError(Exception):
    """A fail-closed gate error raised before a report can be rendered."""


@dataclass(frozen=True, slots=True)
class GateResult:
    """The rendered report and the exit code derived from it.

    ``exit_code`` duplicates ``report["exit_code"]`` on purpose: a caller holding
    the object should not have to reach into the payload, and a log reader should
    not have to re-derive the mapping from the four groups.
    """

    report: dict[str, Any]
    exit_code: int


# --------------------------------------------------------------------------- #
# Owner join (the ri-06 ProducerResult carries no owner field)
# --------------------------------------------------------------------------- #
def owner_by_producer_id() -> dict[str, str]:
    """Map each producer id to its canonical owner.

    Ownership lives on the ri-05 ``ProducerSpec``; the ri-06 ``ProducerResult``
    deliberately does not carry it, so every consumer that wants to *name* an
    owner joins the two. The architecture producer is a separate seam rather than
    a registry entry, so its owner is mapped explicitly, and the context-impact
    arm is a validator rather than a producer, so its owner is too.
    """
    owners = {spec.producer_id: spec.owner for spec in list_producers()}
    owners.setdefault(orchestrator.ARCHITECTURE_PRODUCER_ID, ARCHITECTURE_OWNER)
    owners.setdefault(CONTEXT_IMPACT_PRODUCER_ID, CONTEXT_IMPACT_OWNER)
    return owners


def _outputs_by_producer_id() -> dict[str, tuple[str, ...]]:
    """Declared managed outputs per producer, used only as an artifact fallback."""
    return {spec.producer_id: spec.outputs for spec in list_producers()}


def _bounded(text: str) -> str:
    collapsed = " ".join(str(text).split())
    if not collapsed:
        return "no reason supplied"
    if len(collapsed) <= _MAX_REASON:
        return collapsed
    return collapsed[: _MAX_REASON - 3] + "..."


# --------------------------------------------------------------------------- #
# Group rendering
# --------------------------------------------------------------------------- #
def _artifact_paths(result: ProducerResult, outputs: tuple[str, ...]) -> tuple[str, ...]:
    """Every stale path this result implicates, sorted and de-duplicated.

    A drifted producer that named no artifact falls back to its *declared managed
    outputs*, which is the narrowest honest answer the registry can give. When
    there are none either, the caller reclassifies the result as an apparatus
    failure rather than emitting a drift finding with no path: "the report SHALL
    name every stale artifact by repository-relative path" is not satisfiable by
    a finding that names nothing.
    """
    paths = {artifact.path for artifact in result.artifacts}
    return tuple(sorted(paths)) if paths else tuple(sorted(set(outputs)))


def _remediation_entries(result: ProducerResult) -> list[dict[str, str]]:
    entries = [
        {
            key: value
            for key, value in (
                ("summary", remediation.summary),
                ("command", remediation.command),
                ("documentation", remediation.documentation),
            )
            if value
        }
        for remediation in result.remediation
    ]
    # ri-06 already rejects a non-fresh result with no remediation, so this
    # fallback is unreachable through the registry; it exists so a hand-built
    # result can never produce a report that violates the schema's minItems.
    return entries or [
        {"summary": f"re-run the {result.producer_id} producer to refresh its output"}
    ]


def _finding(result: ProducerResult, owner: str, artifacts: tuple[str, ...]) -> dict[str, Any]:
    return {
        "producer_id": result.producer_id,
        "owner": owner,
        "artifacts": list(artifacts),
        "remediation": _remediation_entries(result),
    }


def _reason_of(result: ProducerResult) -> str:
    """The bounded, never-a-traceback explanation for a degraded result."""
    if result.error is not None:
        return _bounded(f"{result.error.error_class}: {result.error.summary}")
    if result.fallback is not None:
        return _bounded(result.fallback.reason)
    failed = [
        validation.summary
        for validation in result.validations
        if validation.status is ValidationStatus.FAILED
    ]
    if failed:
        return _bounded("; ".join(failed))
    return _bounded(f"{result.producer_id} reported {result.status.value}")


def _failed_validation_summaries(result: ProducerResult) -> str:
    """The result's failed-validation text, which is where drift codes live.

    Deliberately not :func:`_reason_of`: that prefers ``fallback.reason``, and a
    drifted producer's fallback is boilerplate about write behaviour ("check mode
    performed no checkout write"). For explaining *why* a result drifted, the
    failed validations are the only field that carries the reason codes.
    """
    summaries = [
        validation.summary
        for validation in result.validations
        if validation.status is ValidationStatus.FAILED
    ]
    return "; ".join(summaries) if summaries else _reason_of(result)


def _degradation(
    result: ProducerResult, owner: str, reason: str | None = None
) -> dict[str, Any]:
    return {
        "producer_id": result.producer_id,
        "owner": owner,
        "reason": reason if reason is not None else _reason_of(result),
    }


# --------------------------------------------------------------------------- #
# The architecture block
# --------------------------------------------------------------------------- #
def _architecture_result(results: Iterable[ProducerResult]) -> ProducerResult | None:
    for result in results:
        if result.producer_id == orchestrator.ARCHITECTURE_PRODUCER_ID:
            return result
    return None


def provenance_state(repository: Path) -> str:
    """State of the committed provenance document itself: present/missing/malformed.

    Read from the file rather than inferred from the producer's verdict, so
    "digests disagree" and "there is no baseline at all" can never be confused —
    which is the whole reason the schema reports it separately from ``freshness``.
    """
    try:
        raw = (repository / ARCHITECTURE_PROVENANCE_PATH).read_bytes()
    except OSError:
        return "missing"
    try:
        json.loads(raw)
    except ValueError:
        return "malformed"
    return "present"


def architecture_freshness(result: ProducerResult | None) -> str:
    """Map the architecture producer's result onto the report's freshness enum.

    ``unverifiable`` is deliberately *not* folded into ``not-configured``:
    unverifiable evidence blocks, an absent optional owner does not (D4). It
    covers a missing or malformed committed baseline and a producer that could
    not reach a verdict at all.
    """
    if result is None:
        return "not-configured"
    if result.status is ProducerStatus.FRESH:
        return "fresh"
    if result.status is ProducerStatus.NOT_CONFIGURED:
        return "not-configured"
    if result.status is ProducerStatus.FAILED:
        return "unverifiable"
    unverifiable = any(
        validation.summary.startswith(_UNVERIFIABLE_CODES)
        for validation in result.validations
    )
    if unverifiable or not result.artifacts:
        return "unverifiable"
    return "stale"


# --------------------------------------------------------------------------- #
# The context-impact arm (D7)
# --------------------------------------------------------------------------- #
def work_package_files(changed_files: Iterable[str]) -> tuple[str, ...]:
    """The ``work-packages.yaml`` paths present in the diff under test.

    Scoped rather than repository-wide because a blocking gate cannot afford to
    report on packages the diff never touched, and because 65 of this
    repository's 70 work-package files predate the declaration contract —
    reporting on all of them would make the gate noise on arrival.
    """
    return tuple(
        sorted({path for path in changed_files if Path(path).name == WORK_PACKAGES_FILENAME})
    )


def _default_changed_files(repository: Path, base: str) -> tuple[str, ...]:
    """``git diff --name-only <base>...HEAD``, or empty when the base is unknown.

    An unresolvable base is not an apparatus failure. It names a branch that may
    legitimately be absent from a shallow or detached CI checkout, and the
    deterministic arms — the gate's actual yield — do not depend on it. The empty
    result stays visible in the report as an empty ``evaluated`` list.
    """
    completed = subprocess.run(
        ["git", "-C", str(repository), "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ()
    return tuple(line for line in completed.stdout.splitlines() if line)


def _default_context_impact_runner(argv: Sequence[str]) -> tuple[int, str]:
    """Invoke ri-08's validator in-process, capturing its exit code and stdout.

    In-process rather than as a subprocess so the gate does not pay an
    interpreter start per changed work-package file, and so a usage error is a
    return value instead of a parsed stderr string. ``SystemExit`` is caught
    because the validator raises it for a failed ``git diff`` and argparse raises
    it for a malformed argv; both are usage errors, which the caller maps to the
    gate's apparatus-failure exit code rather than to drift.
    """
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = validate_context_impact.main(list(argv))
    except SystemExit as exc:
        code = 0 if exc.code in (0, None) else 2
    except Exception:  # noqa: BLE001 - an apparatus crash is a usage error, not drift
        code = 2
    return int(code), buffer.getvalue()


def _finding_surfaces(package: dict[str, Any]) -> list[str]:
    """The surfaces a finding is *about*, which depends on its status.

    For a failing status the offending surfaces are what a reader must act on;
    for ``unmigrated`` the inferred ones are what adopting the block would
    declare; otherwise the declared set describes the package. Each is
    well-defined for its status, and unknown surfaces are dropped so the report
    can never carry a value outside the schema's enum.
    """
    status = package.get("status")
    if status == "undeclared":
        chosen: Iterable[Any] = package.get("undeclared") or ()
    elif status == "spurious_rationale":
        chosen = package.get("spurious") or ()
    elif status == "unmigrated":
        chosen = package.get("implied") or {}
    else:
        chosen = package.get("declared") or ()
    return sorted({str(surface) for surface in chosen} & set(SURFACES))


@dataclass(frozen=True, slots=True)
class ContextImpactOutcome:
    """The context-impact arm's verdict, kept separate from the four groups.

    ``blocking`` and ``failure_reason`` are what reach the groups;
    ``evaluated``/``findings`` are the detail block. Keeping them apart is what
    lets ``unmigrated`` be reported explicitly while never failing the gate.
    """

    evaluated: tuple[str, ...] = ()
    findings: tuple[dict[str, Any], ...] = ()
    blocking: tuple[str, ...] = ()
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"evaluated": list(self.evaluated), "findings": list(self.findings)}


def run_context_impact(
    repository: Path,
    changed_files: Sequence[str],
    *,
    rules: Path | str | None = None,
    runner: ContextImpactRunner | None = None,
) -> ContextImpactOutcome:
    """Validate every changed work-package declaration; never ``--strict-legacy``.

    ``--strict-legacy`` promotes ``unmigrated`` to a failure, which would make the
    gate red on 65 of this repository's 70 work-package files the day it lands.
    ri-08's progressive enforcement — keyed on whether a declaration block exists,
    so declaring is opt-in but one-way — is deliberate, and closing it is a
    separate migration. The flag is therefore not merely left at its default; it
    is never constructed, and a test asserts the argv.

    *repository* is accepted for symmetry with the other arms and because the
    validator's paths are repository-relative; the detector itself is git-free.
    """
    targets = work_package_files(changed_files)
    if not targets:
        return ContextImpactOutcome()

    invoke = runner or _default_context_impact_runner
    findings: list[dict[str, Any]] = []
    blocking: list[str] = []
    failures: list[str] = []

    for target in targets:
        argv: list[str] = [str(Path(repository) / target), "--json"]
        if rules is not None:
            argv += ["--rules", str(rules)]
        for changed in changed_files:
            argv += ["--changed-file", changed]

        code, stdout = invoke(argv)
        if code == 2:
            failures.append(f"{target}: validator reported a usage or configuration error")
            continue
        try:
            packages = json.loads(stdout)["packages"]
        except (ValueError, KeyError, TypeError):
            failures.append(f"{target}: validator emitted no parsable JSON report")
            continue

        for package in packages:
            status = str(package.get("status", ""))
            findings.append(
                {
                    "package_id": str(package.get("package_id", "")),
                    "status": status,
                    "surfaces": _finding_surfaces(package),
                }
            )
            if status in validate_context_impact.FAILING_STATUSES:
                blocking.append(target)

    return ContextImpactOutcome(
        evaluated=targets,
        findings=tuple(sorted(findings, key=lambda f: (f["package_id"], f["status"]))),
        blocking=tuple(sorted(set(blocking))),
        failure_reason="; ".join(failures) if failures else None,
    )


def _context_impact_finding(paths: Sequence[str]) -> dict[str, Any]:
    return {
        "producer_id": CONTEXT_IMPACT_PRODUCER_ID,
        "owner": CONTEXT_IMPACT_OWNER,
        "artifacts": list(paths),
        "remediation": [
            {
                "summary": (
                    "A changed work package invalidates context it did not declare; "
                    "add the implied surfaces to its context_impact block, or record "
                    "an approved rationale."
                ),
                "command": (
                    "python3 skills/validate-packages/scripts/validate_context_impact.py "
                    "<work-packages.yaml> --base main"
                ),
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
def _default_check_runner(repository: Path, **kwargs: Any) -> orchestrator.RefreshResult:
    """The real deterministic arm: every registered producer in ``check`` mode.

    A module-level indirection rather than a direct call, so the CLI seam can be
    exercised end to end without running real producers against a real checkout.
    """
    return orchestrator.check(repository, **kwargs)


def run_gate(
    repository: Path | str,
    *,
    revision: str | None = None,
    base: str = DEFAULT_BASE,
    changed_files: Sequence[str] | None = None,
    rules: Path | str | None = None,
    architecture: orchestrator.ArchitectureProducer | None = None,
    check_runner: CheckRunner | None = None,
    changed_files_resolver: ChangedFilesResolver | None = None,
    context_impact_runner: ContextImpactRunner | None = None,
) -> GateResult:
    """Compose the three arms into one report and one exit code.

    Read-only end to end: the deterministic arm is ``orchestrator.check``, which
    records no durable operation and writes no manifest; the architecture arm
    compares committed provenance; the context-impact arm parses YAML. Nothing
    here writes the checkout, and a test digests a deliberately dirty fixture
    before and after to prove it rather than assume it.

    ``changed_files`` is accepted explicitly so the gate works on an uncommitted
    worktree; when omitted it is resolved from ``git diff <base>...HEAD``.
    """
    repo_root = Path(repository).resolve()
    run_check = check_runner or _default_check_runner
    refresh = run_check(repo_root, revision=revision, architecture=architecture)

    if changed_files is None:
        resolve = changed_files_resolver or _default_changed_files
        changed_files = resolve(repo_root, base)

    impact = run_context_impact(
        repo_root, list(changed_files), rules=rules, runner=context_impact_runner
    )
    report = render_report(repo_root, refresh, impact, revision=revision)
    return GateResult(report=report, exit_code=report["exit_code"])


def render_report(
    repository: Path,
    refresh: orchestrator.RefreshResult,
    impact: ContextImpactOutcome,
    *,
    revision: str | None = None,
) -> dict[str, Any]:
    """Render the gate report, joining every result with its canonical owner.

    Every group is sorted by producer id and every artifact list by path, so a
    repeat run at the same revision is byte-identical and a diff of two reports
    shows only what actually changed.
    """
    breakdown = orchestrator.classify_degradation(
        tuple(refresh.producer_results), refresh.semantic_index
    )
    owners = owner_by_producer_id()
    outputs = _outputs_by_producer_id()

    blocking: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = [
        _degradation(result, owners.get(result.producer_id, result.producer_id))
        for result in breakdown.failed
    ]
    not_configured: list[dict[str, Any]] = [
        _degradation(result, owners.get(result.producer_id, result.producer_id))
        for result in breakdown.not_configured
    ]

    for group, target in (
        (breakdown.blocking_drift, blocking),
        (breakdown.informational_drift, informational),
    ):
        for result in group:
            owner = owners.get(result.producer_id, result.producer_id)
            artifacts = _artifact_paths(result, outputs.get(result.producer_id, ()))
            if artifacts:
                target.append(_finding(result, owner, artifacts))
            else:
                # Drift the report cannot name is not a precise artifact list, so
                # it is reported as an apparatus failure rather than as drift with
                # an empty list or an invented path. The producer's own failed
                # validations are carried through rather than replaced: refusing
                # to name an artifact is not a reason to also discard the reason
                # codes, which are the only thing left that tells a reader what
                # to look at.
                failed.append(
                    _degradation(
                        result,
                        owner,
                        _bounded(
                            f"{result.producer_id} reported drift without naming any "
                            "artifact, so the gate cannot report a precise stale "
                            f"list — reported: {_failed_validation_summaries(result)}"
                        ),
                    )
                )

    if impact.blocking:
        blocking.append(_context_impact_finding(impact.blocking))
    if impact.failure_reason:
        failed.append(
            {
                "producer_id": CONTEXT_IMPACT_PRODUCER_ID,
                "owner": CONTEXT_IMPACT_OWNER,
                "reason": _bounded(impact.failure_reason),
            }
        )

    for group_list in (blocking, informational, not_configured, failed):
        group_list.sort(key=lambda entry: entry["producer_id"])

    if failed:
        outcome, exit_code = OUTCOME_FAILED, EXIT_FAILED
    elif blocking:
        outcome, exit_code = OUTCOME_DRIFT, EXIT_DRIFT
    else:
        outcome, exit_code = OUTCOME_FRESH, EXIT_FRESH

    architecture = _architecture_result(refresh.producer_results)
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "source_revision": revision or _resolve_revision(repository),
        "outcome": outcome,
        "exit_code": exit_code,
        "blocking_drift": blocking,
        "informational_drift": informational,
        "not_configured": not_configured,
        "failed": failed,
        "architecture": {
            "freshness": architecture_freshness(architecture),
            "provenance": provenance_state(repository),
        },
        "context_impact": impact.to_dict(),
        "semantic": {
            "status": SEMANTIC_STATUS_NOT_ATTEMPTED,
            "reason": SEMANTIC_NOT_ATTEMPTED_REASON,
        },
    }


def _resolve_revision(repository: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = completed.stdout.strip() if completed.returncode == 0 else ""
    if not revision:
        raise GateError("could not resolve HEAD; pass an explicit full-SHA revision")
    return revision


# --------------------------------------------------------------------------- #
# Human rendering
# --------------------------------------------------------------------------- #
def render_text(report: dict[str, Any]) -> str:
    """A human summary naming every stale artifact on its own line.

    The JSON report is the machine contract; this is what a reader sees in a
    failing CI log, and the acceptance outcome is a *precise artifact list*, so
    every path appears individually rather than as a count.
    """
    lines = [
        f"context drift gate: {report['outcome']} (exit {report['exit_code']}) "
        f"at {report['source_revision'][:12]}"
    ]
    for group, label in (
        ("blocking_drift", "BLOCKING"),
        ("informational_drift", "informational"),
    ):
        for finding in report[group]:
            lines.append(f"  [{label}] {finding['producer_id']} — owner {finding['owner']}")
            lines.extend(f"      {path}" for path in finding["artifacts"])
            for remediation in finding["remediation"]:
                command = remediation.get("command")
                lines.append(
                    f"      fix: {remediation['summary']}"
                    + (f" ({command})" if command else "")
                )
    lines.extend(
        f"  [FAILED] {entry['producer_id']} — {entry['reason']}"
        for entry in report["failed"]
    )
    lines.extend(
        f"  [not-configured] {entry['producer_id']} — {entry['reason']}"
        for entry in report["not_configured"]
    )

    architecture = report["architecture"]
    lines.append(
        f"  architecture: {architecture['freshness']} "
        f"(committed provenance {architecture['provenance']})"
    )
    impact = report["context_impact"]
    lines.append(
        f"  context-impact: {len(impact['evaluated'])} changed work-package file(s) "
        "validated, strict-legacy off"
    )
    lines.extend(
        f"      {finding['package_id']}: {finding['status']}"
        for finding in impact["findings"]
    )
    lines.append(
        f"  semantic: {report['semantic']['status']} — {report['semantic']['reason']}"
    )
    return "\n".join(lines)


__all__ = [
    "ARCHITECTURE_OWNER",
    "ARCHITECTURE_PROVENANCE_PATH",
    "CONTEXT_IMPACT_OWNER",
    "CONTEXT_IMPACT_PRODUCER_ID",
    "DEFAULT_BASE",
    "EXIT_DRIFT",
    "EXIT_FAILED",
    "EXIT_FRESH",
    "GATE_SCHEMA_VERSION",
    "SEMANTIC_NOT_ATTEMPTED_REASON",
    "SEMANTIC_STATUS_NOT_ATTEMPTED",
    "ContextImpactOutcome",
    "GateError",
    "GateResult",
    "architecture_freshness",
    "owner_by_producer_id",
    "provenance_state",
    "render_report",
    "render_text",
    "run_context_impact",
    "run_gate",
    "work_package_files",
]
