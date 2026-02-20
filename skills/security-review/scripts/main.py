#!/usr/bin/env python3
"""Orchestrate /security-review scan, normalization, and risk gating."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from aggregate_findings import aggregate
from build_scan_plan import build_plan
from detect_profile import detect_profiles
from gate import evaluate_gate
from models import ScannerResult


def _run_json_command(
    cmd: list[str],
    *,
    check: bool = False,
    expect_json: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Run command and parse JSON from stdout when requested."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    payload: dict[str, Any] = {}
    stdout = result.stdout.strip()
    if expect_json:
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = {
                    "status": "error",
                    "message": f"Non-JSON output from command: {' '.join(cmd)}",
                    "stdout": stdout,
                    "stderr": result.stderr.strip(),
                }
    else:
        payload = {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": stdout,
            "stderr": result.stderr.strip(),
        }

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.returncode, payload


def _git_stdout(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_change_artifact_dir(
    *,
    repo: Path,
    change_id: str,
    openspec_root: str,
) -> Path | None:
    if not change_id:
        return None

    if openspec_root:
        root = Path(openspec_root).resolve()
        change_dir = root / "changes" / change_id
        if change_dir.exists():
            return change_dir
        raise RuntimeError(
            f"OpenSpec change directory not found for '{change_id}': {change_dir}"
        )

    candidates: list[Path] = [repo / "openspec"]
    git_root = _git_stdout(repo, "rev-parse", "--show-toplevel")
    if git_root:
        top_level_candidate = Path(git_root).resolve() / "openspec"
        if top_level_candidate not in candidates:
            candidates.append(top_level_candidate)

    for candidate in candidates:
        change_dir = candidate / "changes" / change_id
        if change_dir.exists():
            return change_dir

    searched = ", ".join(str(candidate / "changes" / change_id) for candidate in candidates)
    raise RuntimeError(
        f"Unable to locate OpenSpec change directory for '{change_id}'. "
        f"Searched: {searched}"
    )


def _as_scanner_result(
    scanner: str,
    status: str,
    message: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ScannerResult(
        scanner=scanner,
        status=status,  # type: ignore[arg-type]
        findings=[],
        messages=[message],
        metadata=metadata or {},
    ).to_dict()


def _required_prereqs_from_plan(plan: dict[str, Any]) -> list[str]:
    requirements: set[str] = set()
    for scanner in plan.get("scanners", []):
        if not bool(scanner.get("enabled")):
            continue
        name = str(scanner.get("scanner", ""))
        if name == "dependency-check":
            requirements.add("dependency-check")
        elif name == "zap":
            requirements.add("zap")
    return sorted(requirements)


def _bootstrap_components_from_missing(missing: list[str]) -> list[str]:
    mapping = {
        "java": "java",
        "docker": "docker",
        "dependency-check": "dependency-check",
        "zap": "docker",
    }
    components = {mapping[item] for item in missing if item in mapping}
    return sorted(components)


def _run_dependency_check(
    script_dir: Path,
    repo: Path,
    output_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    run_cmd = [
        str(script_dir / "run_dependency_check.sh"),
        "--repo",
        str(repo),
        "--out",
        str(output_dir),
        "--project",
        repo.name,
    ]
    if dry_run:
        run_cmd.append("--dry-run")

    run_rc, run_payload = _run_json_command(run_cmd)
    if run_rc != 0 or run_payload.get("status") != "ok":
        return _as_scanner_result(
            scanner="dependency-check",
            status=run_payload.get("status", "error"),
            message=run_payload.get("message", "dependency-check execution failed"),
            metadata=run_payload,
        )

    report_path = run_payload.get("report_path")
    parse_cmd = [
        sys.executable,
        str(script_dir / "parse_dependency_check.py"),
        "--input",
        str(report_path),
    ]
    parse_rc, parse_payload = _run_json_command(parse_cmd)
    if parse_rc != 0:
        return _as_scanner_result(
            scanner="dependency-check",
            status="error",
            message="dependency-check parse failed",
            metadata={
                "runner": run_payload,
                "parser": parse_payload,
            },
        )

    parse_payload.setdefault("metadata", {})
    parse_payload["metadata"]["runner"] = run_payload
    return parse_payload


def _run_zap(
    script_dir: Path,
    output_dir: Path,
    target: str,
    mode: str,
    dry_run: bool,
) -> dict[str, Any]:
    run_cmd = [
        str(script_dir / "run_zap_scan.sh"),
        "--target",
        target,
        "--out",
        str(output_dir),
        "--mode",
        mode,
    ]
    if dry_run:
        run_cmd.append("--dry-run")

    run_rc, run_payload = _run_json_command(run_cmd)
    if run_rc != 0 or run_payload.get("status") != "ok":
        return _as_scanner_result(
            scanner="zap",
            status=run_payload.get("status", "error"),
            message=run_payload.get("message", "zap execution failed"),
            metadata=run_payload,
        )

    report_path = run_payload.get("report_path")
    parse_cmd = [
        sys.executable,
        str(script_dir / "parse_zap_results.py"),
        "--input",
        str(report_path),
    ]
    parse_rc, parse_payload = _run_json_command(parse_cmd)
    if parse_rc != 0:
        return _as_scanner_result(
            scanner="zap",
            status="error",
            message="zap parse failed",
            metadata={
                "runner": run_payload,
                "parser": parse_payload,
            },
        )

    parse_payload.setdefault("metadata", {})
    parse_payload["metadata"]["runner"] = run_payload
    return parse_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Target repository path")
    parser.add_argument(
        "--out-dir",
        default="docs/security-review",
        help="Output directory (relative paths resolve from --repo)",
    )
    parser.add_argument(
        "--change",
        default="",
        help="Optional OpenSpec change-id to emit openspec/changes/<id>/security-review-report.md",
    )
    parser.add_argument(
        "--openspec-root",
        default="",
        help="Optional OpenSpec root containing changes/ (default: auto-detect from --repo)",
    )
    parser.add_argument(
        "--profile-override",
        default="",
        help="Comma-separated profile override",
    )
    parser.add_argument(
        "--fail-on",
        choices=["info", "low", "medium", "high", "critical"],
        default="high",
        help="Severity threshold for gate failure",
    )
    parser.add_argument("--zap-target", default="", help="Target URL/spec for ZAP scans")
    parser.add_argument(
        "--zap-mode",
        choices=["baseline", "api", "full"],
        default="baseline",
    )
    parser.add_argument(
        "--bootstrap",
        choices=["auto", "never"],
        default="auto",
        help="Attempt dependency bootstrap when prereqs are missing",
    )
    parser.add_argument(
        "--apply-bootstrap",
        action="store_true",
        help="Run install commands instead of print-only",
    )
    parser.add_argument(
        "--allow-degraded-pass",
        action="store_true",
        help="Allow pass when scanners are degraded and no threshold findings are found",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
    return parser.parse_args()


def _apply_profile_override(profile: dict[str, Any], override: str) -> dict[str, Any]:
    if not override:
        return profile
    parts = [item.strip() for item in override.split(",") if item.strip()]
    if not parts:
        return profile

    return {
        **profile,
        "primary_profile": "mixed" if len(parts) > 1 else parts[0],
        "profiles": sorted(set(parts + (["mixed"] if len(parts) > 1 else []))),
        "confidence": "high",
        "override": True,
    }


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    requested_out_dir = Path(args.out_dir)
    output_dir = requested_out_dir if requested_out_dir.is_absolute() else repo / requested_out_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    script_dir = Path(__file__).resolve().parent
    change_artifact_dir = _resolve_change_artifact_dir(
        repo=repo,
        change_id=args.change,
        openspec_root=args.openspec_root,
    )
    commit_sha = _git_stdout(repo, "rev-parse", "HEAD") or "unknown"
    timestamp = datetime.now(timezone.utc).isoformat()

    profile = _apply_profile_override(detect_profiles(repo), args.profile_override)
    plan = build_plan(
        profile=profile,
        fail_on=args.fail_on,
        zap_target=args.zap_target or None,
        zap_mode=args.zap_mode,
    )

    prereq_requirements = _required_prereqs_from_plan(plan)
    prereq_cmd = [str(script_dir / "check_prereqs.sh"), "--json"]
    if prereq_requirements:
        prereq_cmd.extend(["--require", ",".join(prereq_requirements)])
    prereq_rc, prereq_payload = _run_json_command(prereq_cmd)
    bootstrap_metadata: dict[str, Any] = {
        "attempted": False,
        "mode": args.bootstrap,
        "apply": args.apply_bootstrap,
        "requirements": prereq_requirements,
    }

    if args.bootstrap == "auto" and prereq_rc != 0:
        missing = prereq_payload.get("missing", []) if isinstance(prereq_payload, dict) else []
        components = _bootstrap_components_from_missing([str(item) for item in missing])
        bootstrap_metadata["missing"] = [str(item) for item in missing]
        bootstrap_metadata["components"] = components
        if components:
            bootstrap_cmd = [str(script_dir / "install_deps.sh"), "--components", ",".join(components)]
            if args.apply_bootstrap:
                bootstrap_cmd.append("--apply")
            bootstrap_metadata["attempted"] = True
            bootstrap_rc, bootstrap_payload = _run_json_command(
                bootstrap_cmd,
                expect_json=False,
            )
            bootstrap_metadata["return_code"] = bootstrap_rc
            bootstrap_metadata["output"] = bootstrap_payload
            prereq_rc, prereq_payload = _run_json_command(prereq_cmd)
        else:
            bootstrap_metadata["attempted"] = False
            bootstrap_metadata["output"] = {
                "status": "skipped",
                "message": "No installable components mapped from missing prerequisites",
            }

    scanner_payloads: list[dict[str, Any]] = []
    for scanner in plan.get("scanners", []):
        scanner_name = scanner.get("scanner")
        enabled = bool(scanner.get("enabled"))
        if not enabled:
            scanner_payloads.append(
                _as_scanner_result(
                    scanner=str(scanner_name),
                    status="skipped",
                    message=str(scanner.get("reason", "scanner disabled by plan")),
                    metadata={"plan": scanner},
                )
            )
            continue

        if scanner_name == "dependency-check":
            scanner_payloads.append(
                _run_dependency_check(
                    script_dir=script_dir,
                    repo=repo,
                    output_dir=output_dir,
                    dry_run=args.dry_run,
                )
            )
            continue

        if scanner_name == "zap":
            target = str(scanner.get("target") or args.zap_target or "")
            if not target:
                scanner_payloads.append(
                    _as_scanner_result(
                        scanner="zap",
                        status="unavailable",
                        message="DAST profile requires --zap-target for ZAP execution",
                        metadata={"plan": scanner},
                    )
                )
                continue

            scanner_payloads.append(
                _run_zap(
                    script_dir=script_dir,
                    output_dir=output_dir,
                    target=target,
                    mode=str(scanner.get("mode") or args.zap_mode),
                    dry_run=args.dry_run,
                )
            )
            continue

        scanner_payloads.append(
            _as_scanner_result(
                scanner=str(scanner_name),
                status="skipped",
                message="Unknown scanner entry in plan",
                metadata={"plan": scanner},
            )
        )

    aggregate_payload = aggregate(
        scanner_payloads=scanner_payloads,
        fail_on=args.fail_on,
        profile=profile,
    )
    aggregate_payload["plan"] = plan
    aggregate_payload["prereqs"] = prereq_payload
    aggregate_payload["bootstrap"] = bootstrap_metadata

    gate_result = evaluate_gate(
        scanner_results=aggregate_payload["scanner_results"],
        findings=aggregate_payload["findings"],
        fail_on=args.fail_on,
        allow_degraded_pass=args.allow_degraded_pass,
    )

    aggregate_path = output_dir / "aggregate.json"
    gate_path = output_dir / "gate.json"
    json_report_path = output_dir / "security-review-report.json"
    md_report_path = output_dir / "security-review-report.md"

    aggregate_path.write_text(json.dumps(aggregate_payload, indent=2) + "\n", encoding="utf-8")
    gate_path.write_text(json.dumps(gate_result.to_dict(), indent=2) + "\n", encoding="utf-8")

    render_cmd = [
        sys.executable,
        str(script_dir / "render_report.py"),
        "--aggregate",
        str(aggregate_path),
        "--gate",
        str(gate_path),
        "--json-out",
        str(json_report_path),
        "--md-out",
        str(md_report_path),
        "--commit-sha",
        commit_sha,
        "--timestamp",
        timestamp,
    ]
    if args.change:
        render_cmd.extend(["--change-id", args.change])
    render_rc, render_payload = _run_json_command(render_cmd)
    if render_rc != 0:
        raise RuntimeError(f"Failed to render report: {render_payload}")

    change_report_path: Path | None = None
    if change_artifact_dir is not None:
        change_report_path = change_artifact_dir / "security-review-report.md"
        shutil.copyfile(md_report_path, change_report_path)

    summary = {
        "decision": gate_result.decision,
        "triggered_count": gate_result.triggered_count,
        "json_report": str(json_report_path),
        "markdown_report": str(md_report_path),
    }
    if change_report_path is not None:
        summary["change_artifact"] = str(change_report_path)
    print(json.dumps(summary, indent=2))

    if gate_result.decision == "PASS":
        return 0
    if gate_result.decision == "FAIL":
        return 10
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
