#!/usr/bin/env python3
"""skill-audit CLI: audit a SKILL.md for model-tier fit.

    skill_audit.py <skill-name> | --all
        [--evidence-window <days>] [--convention rightsizing|current]
        [--propose] [--check-freshness] [--output-dir <path>]

Read-only over the audited skill: the only writes are the report, the
findings ledger, and candidate-work stubs under ``--output-dir``. Exit codes:
``0`` ok, ``1`` stale (``--check-freshness``) or input error.

Model backend: ``SKILL_AUDIT_MODEL_CMD`` names a shell command that reads the
classification prompt on stdin and prints ``{section_id: label}`` JSON. Unset,
no model is called and undecided prose is reported ``unclassified``.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_paths import SKILLS_ROOT, default_archetypes_path, ensure_sibling_paths, find_repo_root, load_bridge  # noqa: E402
from classifier import (  # noqa: E402
    CommandBackend,
    ModelBackend,
    NullBackend,
    classify_sections,
    collect_test_texts,
    generate_findings,
    parse_skill,
    resolve_analyst,
)
from conventions import CONVENTIONS, lint  # noqa: E402
from dispatch_profile import build_dispatch_profile  # noqa: E402
from evidence_join import (  # noqa: E402
    EvidenceResult,
    collect_evidence,
    fetch_discovery_sessions,
    fetch_memory_entries,
    load_loop_states,
)
from audit_findings import Finding, build_ledger, write_ledger  # noqa: E402
from report import (  # noqa: E402
    freshness_stamp,
    newest_report,
    parse_stamp,
    render_report,
    report_filename,
    reviewed_dates,
    sha256_file,
    utc_now_iso,
)

ensure_sibling_paths()

log = logging.getLogger("skill_audit")
DEFAULT_OUTPUT_DIR = Path("docs/reports/skill-audit")
SEVERITY_BY_KIND = {
    "tier_concentrated_failure": "high",
    "contract_unpinned": "high",
    "constraint_without_reason": "medium",
    "procedure_without_probe": "medium",
    "missing_deviation_protocol": "medium",
    "convention_drift": "medium",
    "teaching_inferable": "low",
}


@dataclass
class EvidenceInputs:
    """Memory entries fetched once per process so ``--all`` makes one query."""

    entries: list[dict[str, Any]] | None
    reason: str | None
    sessions: list[dict[str, Any]] = field(default_factory=list)
    loop_states: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class AuditOutcome:
    skill: str
    report_path: Path
    ledger_path: Path
    ledger: dict[str, Any]
    candidate_path: Path | None = None
    model_calls: int = 0


def prepare_evidence_inputs(bridge: Any | None, *, window_days: int, repo_root: Path | None) -> EvidenceInputs:
    entries, reason = fetch_memory_entries(bridge, window_days=window_days)
    sessions = fetch_discovery_sessions(bridge) if entries is not None else []
    return EvidenceInputs(entries=entries, reason=reason, sessions=sessions, loop_states=load_loop_states(repo_root))


def default_backend() -> ModelBackend:
    command = os.environ.get("SKILL_AUDIT_MODEL_CMD", "").strip()
    return CommandBackend(command) if command else NullBackend()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "section"


def _relative(path: Path, repo_root: Path | None) -> str:
    if repo_root is not None:
        try:
            return str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            pass
    return str(path)


def propose(ledger: dict[str, Any], *, report_path: Path, output_dir: Path, repo_root: Path | None) -> Path | None:
    """Write one candidate-work stub per non-``keep`` ``(kind, section)`` (design D8)."""
    from improve_candidate_work import write_projection  # noqa: E402  (sibling skill)

    skill = ledger["skill"]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for f in ledger["findings"]:
        if f["remediation"] == "keep":
            continue
        groups.setdefault((f["kind"], f["section_id"]), []).append(f)
    if not groups:
        return None
    ranked: list[dict[str, Any]] = []
    for (kind, section_id), members in groups.items():
        ranked.append(
            {
                "capability_gap": f"rightsize {skill}: {kind} in {section_id}",
                "max_severity": SEVERITY_BY_KIND.get(kind, "low"),
                "frequency": len(members),
                "entries": [{"id": m["id"]} for m in members],
                "affected_skills": [skill],
                "suggested_change_id": f"rightsize-{skill}-{kind}-{_slug(section_id)}",
            }
        )
    destination = output_dir / f"{skill}-candidate-work.json"
    return write_projection(ranked, destination, _relative(report_path, repo_root))


def audit_skill(
    name: str,
    *,
    skills_root: Path,
    output_dir: Path,
    archetypes_path: Path,
    convention: str = "rightsizing",
    window_days: int = 30,
    do_propose: bool = False,
    backend: ModelBackend | None = None,
    bridge: Any | None = None,
    evidence_inputs: EvidenceInputs | None = None,
    repo_root: Path | None = None,
    now: datetime | None = None,
) -> AuditOutcome:
    skill_dir = skills_root / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"no SKILL.md for skill {name!r} under {skills_root}")
    backend = backend or default_backend()
    generated_at = utc_now_iso(now)

    sections = parse_skill(skill_dir)
    model = None if isinstance(backend, NullBackend) else resolve_analyst(bridge=bridge, roster_path=archetypes_path)
    classification = classify_sections(name, sections, backend, model=model)
    findings: list[Finding] = generate_findings(
        sections, classification, test_texts=collect_test_texts(skill_dir, skills_root)
    )

    profile = build_dispatch_profile(name, skill_md.read_text(encoding="utf-8"), roster_path=archetypes_path)

    if evidence_inputs is None:
        evidence = collect_evidence(
            name, window_days=window_days, bridge=bridge, repo_root=repo_root, roster_path=archetypes_path, now=now
        )
    elif evidence_inputs.entries is None:
        evidence = EvidenceResult(status="unavailable", reason=evidence_inputs.reason or "coordinator_unreachable")
    else:
        evidence = collect_evidence(
            name,
            window_days=window_days,
            entries=evidence_inputs.entries,
            sessions=evidence_inputs.sessions,
            loop_states=evidence_inputs.loop_states,
            roster_path=archetypes_path,
            now=now,
        )
    findings.extend(evidence.findings)
    findings.extend(lint(skill_dir, convention))

    stamp = freshness_stamp(archetypes_path, evidence_window_days=window_days, generated_at=generated_at)
    ledger = build_ledger(
        skill=name,
        convention=convention,
        generated_at=generated_at,
        freshness=stamp,
        layers=[label.to_dict() for label in classification.labels],
        dispatch_profile=profile,
        evidence=evidence.to_ledger(),
        findings=findings,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = write_ledger(ledger, output_dir / f"{name}-findings.json")
    report_path = output_dir / report_filename(name, generated_at)
    report_path.write_text(
        render_report(
            ledger=ledger,
            sections=sections,
            evidence_reason=evidence.reason,
            multi_source_count=evidence.multi_source_count,
            evidence_total=evidence.total,
            model_calls=classification.model_calls,
            batch_size=classification.batch_size,
            warnings=classification.warnings,
        ),
        encoding="utf-8",
    )
    candidate_path = None
    if do_propose:
        candidate_path = propose(ledger, report_path=report_path, output_dir=output_dir, repo_root=repo_root)
    return AuditOutcome(name, report_path, ledger_path, ledger, candidate_path, classification.model_calls)


def check_freshness(names: list[str], *, output_dir: Path, archetypes_path: Path, out=None) -> int:
    """Exit ``1`` when any named skill's newest report is missing or stale."""
    out = out or sys.stdout  # resolved at call time so redirected stdout is honoured
    current_hash = sha256_file(archetypes_path)
    current_dates = reviewed_dates(archetypes_path)
    stale = 0
    for name in names:
        report = newest_report(output_dir, name)
        if report is None:
            print(f"{name}: STALE — no report under {output_dir}; current archetypes_sha256={current_hash}", file=out)
            stale += 1
            continue
        stamp = parse_stamp(report.read_text(encoding="utf-8"))
        recorded = str(stamp.get("archetypes_sha256", ""))
        recorded_dates = list(stamp.get("reviewed_dates", []))
        added = sorted(set(current_dates) - set(recorded_dates))
        removed = sorted(set(recorded_dates) - set(current_dates))
        delta = f"reviewed_dates +{added or []} -{removed or []}"
        if recorded != current_hash:
            print(
                f"{name}: STALE — report {report.name} archetypes_sha256={recorded or '(missing)'} "
                f"!= current {current_hash}; {delta}",
                file=out,
            )
            stale += 1
        else:
            print(f"{name}: fresh — {report.name} archetypes_sha256={current_hash}; {delta}", file=out)
    return 1 if stale else 0


def list_skills(skills_root: Path) -> list[str]:
    return sorted(p.parent.name for p in skills_root.glob("*/SKILL.md"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill_audit.py", description="Audit a SKILL.md for model-tier fit.")
    parser.add_argument("skill", nargs="?", help="skill name (directory under the skills root)")
    parser.add_argument("--all", action="store_true", help="audit every skill under the skills root")
    parser.add_argument("--evidence-window", type=int, default=30, metavar="DAYS")
    parser.add_argument("--convention", choices=CONVENTIONS, default="rightsizing")
    parser.add_argument("--propose", action="store_true", help="also write candidate-work stubs")
    parser.add_argument("--check-freshness", action="store_true", help="exit 1 when the newest report is stale")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, metavar="PATH")
    parser.add_argument("--skills-root", type=Path, default=SKILLS_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--archetypes", type=Path, default=None, help="path to archetypes.yaml (default: agent-coordinator/archetypes.yaml)")
    parser.add_argument("--repo-root", type=Path, default=None, help="repository root for the loop-state scan (default: auto)")
    return parser


def main(argv: list[str] | None = None, *, backend: ModelBackend | None = None, bridge: Any | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    args = build_parser().parse_args(argv)
    if bool(args.skill) == bool(args.all):
        print("error: give exactly one skill name or --all", file=sys.stderr)
        return 1
    if args.evidence_window < 1:
        print("error: --evidence-window must be at least 1", file=sys.stderr)
        return 1
    skills_root: Path = args.skills_root
    names = list_skills(skills_root) if args.all else [args.skill]
    if not names:
        print(f"error: no skills under {skills_root}", file=sys.stderr)
        return 1
    missing = [n for n in names if not (skills_root / n / "SKILL.md").is_file()]
    if missing:
        print(f"error: unknown skill(s) {missing} under {skills_root}", file=sys.stderr)
        return 1
    archetypes_path = args.archetypes or (Path(os.environ["ARCHETYPES_YAML"]) if os.environ.get("ARCHETYPES_YAML") else default_archetypes_path())
    if archetypes_path is None or not Path(archetypes_path).is_file():
        print("error: archetypes.yaml not found; pass --archetypes or set ARCHETYPES_YAML", file=sys.stderr)
        return 1
    archetypes_path = Path(archetypes_path)
    output_dir: Path = args.output_dir

    if args.check_freshness:
        return check_freshness(names, output_dir=output_dir, archetypes_path=archetypes_path)

    repo_root = args.repo_root or find_repo_root(skills_root) or find_repo_root()
    if bridge is None:
        bridge = load_bridge()
    inputs = prepare_evidence_inputs(bridge, window_days=args.evidence_window, repo_root=repo_root)
    if inputs.entries is None:
        log.warning("skill-audit: evidence unavailable (%s); auditing on layer findings alone", inputs.reason)

    failures = 0
    for name in names:
        try:
            outcome = audit_skill(
                name,
                skills_root=skills_root,
                output_dir=output_dir,
                archetypes_path=archetypes_path,
                convention=args.convention,
                window_days=args.evidence_window,
                do_propose=args.propose,
                backend=backend,
                bridge=bridge,
                evidence_inputs=inputs,
                repo_root=repo_root,
            )
        except Exception as exc:
            failures += 1
            print(f"{name}: error — {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        summary = (
            f"{name}: {len(outcome.ledger['findings'])} finding(s), evidence {outcome.ledger['evidence']['status']}, "
            f"report {outcome.report_path}, ledger {outcome.ledger_path}"
        )
        if outcome.candidate_path:
            summary += f", candidate-work {outcome.candidate_path}"
        print(summary)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
