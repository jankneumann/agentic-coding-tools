#!/usr/bin/env python3
"""CI wall-clock measurement and run verification (design D8).

Pure functions over JSON-shaped data, plus a thin CLI that shells out to ``gh api`` for
read-only GETs when the OPERATOR runs it. Standard library plus PyYAML only.

Functions
    median_wallclock(runs, *, conclusion="success")
    compare(baseline, candidate, *, threshold=0.85, min_n=5, ...)
    verify_run(jobs, manifest, workflow, *, workflow_file=None, expected_lane="self-hosted")

CLI
    ci_wallclock.py median     --workflow F [--head-sha S] [--event E] [--since D] [--until D] [--limit N]
    ci_wallclock.py compare    --baseline-lane L --candidate-lane L --workflow F [filters] [--threshold X]
    ci_wallclock.py verify-run RUN_ID --workflow F [--expect-lane self-hosted|hosted] [--workflow-file PATH]

Nothing here mutates GitHub, the host, or repository settings.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / ".github" / "runner-lanes.yaml"
SELF_HOSTED_MARKER = "gx10"
# A job on a self-hosted runner that is NOT the GX10 pool. Never a valid placement: it is
# neither GitHub-hosted nor the lane this change routes to.
OTHER_SELF_HOSTED = "other-self-hosted"


# ------------------------------------------------------------------------------ helpers


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _duration(run: dict[str, Any]) -> float | None:
    start, end = run.get("run_started_at"), run.get("updated_at")
    if not start or not end:
        return None
    return (_ts(end) - _ts(start)).total_seconds()


def _labels(job: dict[str, Any]) -> set[str]:
    return {str(x).lower() for x in (job.get("labels") or [])}


def job_lane(job: dict[str, Any]) -> str | None:
    """'self-hosted' if the job asked for the gx10 runner, OTHER_SELF_HOSTED if it asked for
    some other self-hosted runner, 'hosted' if it ran on a GitHub-hosted label, None if no
    runner was assigned (no labels recorded)."""
    labels = _labels(job)
    if not labels:
        return None
    if SELF_HOSTED_MARKER in labels:
        return "self-hosted"
    if "self-hosted" in labels:
        return OTHER_SELF_HOSTED
    return "hosted"


def _workflow_jobs(workflow: dict[str, Any]) -> dict[str, Any]:
    return (workflow or {}).get("jobs") or {}


def _display_name(job_id: str, definition: Any) -> str:
    if isinstance(definition, dict) and isinstance(definition.get("name"), str):
        return definition["name"]
    return job_id


def correlate(
    api_jobs: list[dict[str, Any]], workflow: dict[str, Any], job_ids: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Map manifest job ids to jobs-API entries via the derived display name (D8).

    A job is displayed as its id, or as its literal ``name:``. A matrix job expands to
    ``<display> (<v1>, ...)`` entries, matched by the ``<display> (`` prefix. Returns
    (matched by id, unmatched entries).
    """
    defs = _workflow_jobs(workflow)
    names = {jid: _display_name(jid, defs.get(jid)) for jid in job_ids}
    matched: dict[str, list[dict[str, Any]]] = {jid: [] for jid in job_ids}
    unmatched: list[dict[str, Any]] = []
    for entry in api_jobs:
        name = str(entry.get("name", ""))
        exact = [j for j, n in names.items() if n == name]
        if exact:
            matched[exact[0]].append(entry)
            continue
        prefixed = sorted(
            (j for j, n in names.items() if name.startswith(n + " (")),
            key=lambda j: len(names[j]),
            reverse=True,
        )
        if prefixed:
            matched[prefixed[0]].append(entry)
        else:
            unmatched.append(entry)
    return matched, unmatched


def _infer_workflow_file(manifest: dict[str, Any], workflow: dict[str, Any]) -> str:
    ids = set(_workflow_jobs(workflow))
    hits = [w for w, spec in manifest["workflows"].items() if set(spec["jobs"]) == ids]
    if len(hits) != 1:
        raise ValueError("cannot infer the manifest workflow; pass workflow_file=")
    return hits[0]


# ----------------------------------------------------------------------------- median


def median_wallclock(
    runs: list[dict[str, Any]], *, conclusion: str = "success"
) -> float | None:
    """Median ``run_started_at -> updated_at`` seconds over runs with ``conclusion``."""
    values = [
        d
        for r in runs
        if r.get("conclusion") == conclusion and (d := _duration(r)) is not None
    ]
    return statistics.median(values) if values else None


# ----------------------------------------------------------------------------- compare


def run_lane(
    run: dict[str, Any],
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    workflow_file: str,
) -> tuple[str | None, str]:
    """Derive a run's lane from where its routed jobs actually ran.

    Returns (lane, reason). ``lane`` is None when the run cannot be classified: mixed
    placement, or no routed job was assigned a runner.
    """
    spec = manifest["workflows"][workflow_file]["jobs"]
    routed = [j for j, e in spec.items() if e["lane"] == "routed"]
    matched, _ = correlate(run.get("jobs") or [], workflow, routed)
    lanes = {
        lane
        for entries in matched.values()
        for entry in entries
        if entry.get("conclusion") != "skipped"
        and (lane := job_lane(entry)) is not None
    }
    if not lanes:
        return None, "no routed job was assigned a runner"
    if len(lanes) > 1:
        return None, "mixed placement across routed jobs"
    return lanes.pop(), "ok"


def compare(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    threshold: float = 0.85,
    min_n: int = 5,
    manifest: dict[str, Any] | None = None,
    workflow: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    workflow_file: str | None = None,
    baseline_lane: str = "hosted",
    candidate_lane: str = "self-hosted",
) -> dict[str, Any]:
    """Pass only if ``candidate_median <= threshold * baseline_median`` and both n >= min_n.

    When ``manifest`` is given and runs carry a ``jobs`` list, each run's lane is derived
    from its routed jobs; runs with mixed or no routed placement are excluded from both
    samples and listed in ``excluded_runs``.
    """
    excluded: dict[Any, str] = {}

    def lane_of(r: dict[str, Any]) -> str | None:
        wf = workflow(r) if callable(workflow) else (workflow or {})
        wf_file = workflow_file or _infer_workflow_file(manifest, wf)  # type: ignore[arg-type]
        lane, why = run_lane(r, manifest, wf, wf_file)  # type: ignore[arg-type]
        if lane is None:
            excluded[r["id"]] = why
        return lane

    def select(runs: list[dict[str, Any]], want: str, other: list[dict[str, Any]]):
        if manifest is None:
            return runs
        other_ids = {r.get("id") for r in other}
        kept = []
        for r in runs:
            if "jobs" not in r:
                kept.append(r)
                continue
            lane = lane_of(r)
            if lane == want:
                kept.append(r)
            elif lane is not None and r["id"] not in other_ids:
                excluded[r["id"]] = f"ran on the {lane} lane, expected {want}"
        return kept

    base = select(baseline, baseline_lane, candidate)
    cand = select(candidate, candidate_lane, baseline)
    b_med, c_med = median_wallclock(base), median_wallclock(cand)
    n_b = sum(
        1 for r in base if r.get("conclusion") == "success" and _duration(r) is not None
    )
    n_c = sum(
        1 for r in cand if r.get("conclusion") == "success" and _duration(r) is not None
    )
    result: dict[str, Any] = {
        "passed": False,
        "threshold": threshold,
        "min_n": min_n,
        "baseline_median": b_med,
        "candidate_median": c_med,
        "n_baseline": n_b,
        "n_candidate": n_c,
        "ratio": (c_med / b_med) if b_med and c_med is not None else None,
        "excluded_runs": [{"run_id": k, "reason": v} for k, v in excluded.items()],
    }
    if n_b < min_n or n_c < min_n:
        result["reason"] = (
            f"insufficient samples: n_baseline={n_b}, n_candidate={n_c}, need {min_n}"
        )
    elif c_med <= threshold * b_med:  # type: ignore[operator]
        result["passed"] = True
        result["reason"] = (
            f"candidate median {c_med:g}s <= {threshold} x baseline {b_med:g}s"
        )
    else:
        result["reason"] = (
            f"candidate median {c_med:g}s > {threshold} x baseline {b_med:g}s"
        )
    return result


# -------------------------------------------------------------------------- verify_run


def verify_run(
    jobs: list[dict[str, Any]],
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    *,
    workflow_file: str | None = None,
    expected_lane: str = "self-hosted",
) -> dict[str, list[dict[str, str]]]:
    """Check one run's jobs-API entries against the lane manifest (D8)."""
    if expected_lane not in ("self-hosted", "hosted"):
        raise ValueError("expected_lane must be 'self-hosted' or 'hosted'")
    wf_file = workflow_file or _infer_workflow_file(manifest, workflow)
    spec = manifest["workflows"][wf_file]["jobs"]
    defs = _workflow_jobs(workflow)
    matched, unmatched = correlate(jobs, workflow, list(spec))
    violations: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def violation(name: str, kind: str, message: str) -> None:
        violations.append({"job": name, "kind": kind, "message": message})

    for entry in unmatched:
        violation(
            str(entry.get("name")), "unknown", "unknown job: matches no manifest job"
        )

    for job_id, entries in matched.items():
        lane = spec[job_id]["lane"]
        definition = defs.get(job_id) or {}
        if not entries:
            violation(
                job_id, "missing", f"manifest job {job_id!r} is missing from the run"
            )
            continue
        for entry in entries:
            name = str(entry.get("name"))
            conclusion = entry.get("conclusion")
            if conclusion == "skipped":
                if "if" not in definition:
                    violation(
                        name,
                        "skipped",
                        "skipped although it has no job-level if: (an upstream job failed)",
                    )
                continue  # a skipped job never had a runner assigned: placement not checked
            if conclusion != "success":
                coe = definition.get("continue-on-error")
                item = {
                    "job": name,
                    "kind": "conclusion",
                    "message": f"concluded {conclusion}",
                }
                if coe is True or str(coe).lower() == "true":
                    item["message"] += " (continue-on-error)"
                    warnings.append(item)
                else:
                    violations.append(item)
            actual = job_lane(entry)
            if lane == "hosted":
                if actual is not None and actual != "hosted":
                    violation(
                        name,
                        "placement",
                        f"hosted job ran on a self-hosted runner ({actual})",
                    )
            elif actual is not None and actual != expected_lane:
                violation(
                    name,
                    "placement",
                    f"routed job ran on the {actual} lane; expected the {expected_lane} lane",
                )
    return {"violations": violations, "warnings": warnings}


# ------------------------------------------------------------------------------- CLI


class GhError(RuntimeError):
    pass


def gh_get(path: str, *, raw: bool = False) -> Any:
    """A read-only ``gh api`` GET. ``path`` may carry a query string."""
    cmd = ["gh", "api", "-X", "GET", path]
    if raw:
        cmd += ["-H", "Accept: application/vnd.github.raw+json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise GhError(f"gh api {path} failed: {proc.stderr.strip()}")
    return proc.stdout if raw else json.loads(proc.stdout)


def _created_filter(since: str | None, until: str | None) -> str | None:
    if since and until:
        return f"{since}..{until}"
    if since:
        return f">={since}"
    if until:
        return f"<={until}"
    return None


def fetch_runs(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Page through workflow runs with explicit filters, stopping at ``--limit``.

    ``per_page`` stays fixed across pages: GitHub serves page N as the offset
    ``(N-1)*per_page``, so shrinking it on the last page would re-fetch earlier runs.
    """
    runs: list[dict[str, Any]] = []
    page = 1
    per_page = min(100, args.limit)
    while len(runs) < args.limit:
        params = [f"per_page={per_page}", f"page={page}", "status=completed"]
        for key, val in (("event", args.event), ("head_sha", args.head_sha)):
            if val:
                params.append(f"{key}={val}")
        created = _created_filter(args.since, args.until)
        if created:
            params.append(f"created={created}")
        data = gh_get(
            f"repos/{{owner}}/{{repo}}/actions/workflows/{args.workflow}/runs?"
            + "&".join(params)
        )
        batch = data.get("workflow_runs", [])
        runs.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return runs[: args.limit]


def fetch_jobs(run_id: Any) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    page = 1
    while True:
        data = gh_get(
            f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs?per_page=100&page={page}&filter=latest"
        )
        batch = data.get("jobs", [])
        jobs.extend(batch)
        if len(batch) < 100:
            return jobs
        page += 1


def fetch_definition(workflow: str, sha: str) -> dict[str, Any]:
    text = gh_get(
        f"repos/{{owner}}/{{repo}}/contents/.github/workflows/{workflow}?ref={sha}",
        raw=True,
    )
    return yaml.safe_load(text)


def _load_manifest(path: str | None) -> dict[str, Any]:
    return yaml.safe_load(Path(path or DEFAULT_MANIFEST).read_text())


def _add_selection(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workflow", required=True, help="workflow file name, e.g. ci.yml")
    p.add_argument("--head-sha")
    p.add_argument("--event")
    p.add_argument("--since", help="ISO date, inclusive")
    p.add_argument("--until", help="ISO date, inclusive")
    p.add_argument("--limit", type=int, default=200)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    med = sub.add_parser("median", help="median wall-clock of successful runs")
    _add_selection(med)

    cmp_ = sub.add_parser("compare", help="compare two lanes' median wall-clock")
    _add_selection(cmp_)
    cmp_.add_argument(
        "--baseline-lane", default="hosted", choices=["hosted", "self-hosted"]
    )
    cmp_.add_argument(
        "--candidate-lane", default="self-hosted", choices=["hosted", "self-hosted"]
    )
    cmp_.add_argument("--threshold", type=float, default=0.85)
    cmp_.add_argument("--min-n", type=int, default=5)
    cmp_.add_argument("--manifest")
    cmp_.add_argument(
        "--workflow-file", help="local workflow definition (skips fetching by sha)"
    )

    ver = sub.add_parser(
        "verify-run", help="check one run's job placement against the manifest"
    )
    ver.add_argument("run_id")
    ver.add_argument("--workflow", required=True)
    ver.add_argument(
        "--expect-lane", default="self-hosted", choices=["self-hosted", "hosted"]
    )
    ver.add_argument("--manifest")
    ver.add_argument(
        "--workflow-file", help="local workflow definition (skips fetching by sha)"
    )
    return parser


def cmd_median(args: argparse.Namespace) -> int:
    runs = fetch_runs(args)
    ok = [
        r for r in runs if r.get("conclusion") == "success" and _duration(r) is not None
    ]
    print(
        json.dumps(
            {
                "n": len(ok),
                "fetched": len(runs),
                "median_seconds": median_wallclock(runs),
            }
        )
    )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    runs = fetch_runs(args)
    for r in runs:
        r["jobs"] = fetch_jobs(r["id"])
    cache: dict[str, dict[str, Any]] = {}
    local = (
        yaml.safe_load(Path(args.workflow_file).read_text())
        if args.workflow_file
        else None
    )

    def definition(run: dict[str, Any]) -> dict[str, Any]:
        if local is not None:
            return local
        sha = run["head_sha"]
        if sha not in cache:
            cache[sha] = fetch_definition(args.workflow, sha)
        return cache[sha]

    result = compare(
        runs,
        runs,
        threshold=args.threshold,
        min_n=args.min_n,
        manifest=manifest,
        workflow=definition,
        workflow_file=args.workflow,
        baseline_lane=args.baseline_lane,
        candidate_lane=args.candidate_lane,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


def cmd_verify_run(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    if args.workflow_file:
        definition = yaml.safe_load(Path(args.workflow_file).read_text())
    else:
        run = gh_get(f"repos/{{owner}}/{{repo}}/actions/runs/{args.run_id}")
        definition = fetch_definition(args.workflow, run["head_sha"])
    result = verify_run(
        fetch_jobs(args.run_id),
        manifest,
        definition,
        workflow_file=args.workflow,
        expected_lane=args.expect_lane,
    )
    for w in result["warnings"]:
        print(f"warning: {w['job']}: {w['message']}")
    for v in result["violations"]:
        print(f"violation: {v['job']}: {v['message']}")
    print(
        f"{len(result['violations'])} violation(s), {len(result['warnings'])} warning(s) "
        f"(expected lane: {args.expect_lane})"
    )
    return 1 if result["violations"] else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {
            "median": cmd_median,
            "compare": cmd_compare,
            "verify-run": cmd_verify_run,
        }[args.cmd](args)
    except (GhError, OSError, yaml.YAMLError, KeyError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
