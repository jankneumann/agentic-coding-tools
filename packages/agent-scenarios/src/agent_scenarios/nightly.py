"""Nightly cross-vendor parity runner (design D4).

``agent-scenarios nightly --config <path> [--dry-run]`` runs the seed suite across a vendor
allowlist under explicit size and time caps and does nothing unless explicitly enabled.

Ordered guards (each writes a ``run`` record and exits as noted):

0. config missing / unparsable / schema-invalid -> stderr, exit 2, **no record**
1. ``enabled: false``                           -> ``disabled``, exit 0, no executor built
2. kill-file present                            -> ``disabled``, exit 0
3. run lock held                                -> ``locked``, exit 0
4. < 2 effective vendors                        -> ``config_error``, exit 2
5. planned pairs over a cap                     -> ``cap_exceeded``, exit 2, nothing launched
6. wall-clock budget reached mid-run            -> remaining pairs ``skipped_budget``

Exit codes (highest precedence first): 2 config/cap error; 1 any scenario ``fail``; 3 no
``fail`` but an ``error`` result or an exhausted budget (the night is not green); 0 otherwise.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .executor import (
    COORDINATION_URL_VAR,
    HERMETIC_SCRUB,
    CLIVendorExecutor,
    ScenarioExecutor,
)
from .findings_emitter import emit_findings
from .gap_emitter import (
    CoordinatorMemorySink,
    MemorySink,
    SpoolMemorySink,
    build_gap_entries,
    default_spool_path,
    emit_gaps,
    flush_spool,
)
from .gh_shim import bin_dir_for, origin_path_for
from .judge import TrajectoryJudgeBackend
from .loader import ScenarioLoadError, load_scenarios
from .materialize import skills_sha as compute_skills_sha
from .models import AgentScenario, ParityMatrix
from .results_store import (
    JsonlResultsStore,
    ResultRecord,
    RunRecord,
    RunStatus,
    default_results_path,
    lock_path_for,
    records_from_matrices,
    skipped_budget_record,
    utc_now,
)
from .runner import run_scenario
from .suite import skill_family

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "~/.config/agent-scenarios/nightly.yaml"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2
EXIT_NOT_GREEN = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class Caps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_pairs: int = Field(default=30, ge=1)
    max_pairs_per_vendor: int = Field(default=15, ge=1)
    max_wall_clock_minutes: int = Field(default=240, ge=1)
    per_pair_timeout_seconds: int = Field(default=1200, ge=30)


class ResultsCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None


class FindingsCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None


class GapsCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    spool_path: str | None = None
    agent_id: str = "agent-scenarios-nightly"
    coordinator_url_env: str = "COORDINATION_API_URL"
    api_key_env: str = "COORDINATION_API_KEY"


class JudgeCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False


class NightlyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    disable_file: str | None = "~/.config/agent-scenarios/DISABLED"
    scenarios_dir: str
    repo_root: str
    skills_root: str | None = "skills"
    vendors: list[str] = Field(min_length=2)
    vendor_commands: dict[str, str]
    env_scrub: list[str] = Field(default_factory=list)
    env_set: dict[str, str] = Field(default_factory=dict)
    workspaces_root: str | None = None
    retain_failed_runs: int = Field(default=7, ge=0)
    caps: Caps = Field(default_factory=lambda: Caps())
    results: ResultsCfg = Field(default_factory=lambda: ResultsCfg())
    findings: FindingsCfg = Field(default_factory=lambda: FindingsCfg())
    gaps: GapsCfg = Field(default_factory=lambda: GapsCfg())
    judge: JudgeCfg = Field(default_factory=lambda: JudgeCfg())

    @model_validator(mode="after")
    def _check(self) -> NightlyConfig:
        if len(set(self.vendors)) != len(self.vendors):
            raise ValueError("vendors must be unique")
        missing = [v for v in self.vendors if not self.vendor_commands.get(v, "").strip()]
        if missing:
            raise ValueError(f"vendors without a vendor_commands entry: {', '.join(missing)}")
        protected = (
            set(HERMETIC_SCRUB)
            | {COORDINATION_URL_VAR}
            | set(self.env_scrub)
            | {self.gaps.api_key_env, self.gaps.coordinator_url_env}
        )
        clash = sorted(set(self.env_set) & protected)
        if clash:
            raise ValueError(
                "env_set may not name scrubbed or protected variables: " + ", ".join(clash)
            )
        return self

    # -- derived paths ---------------------------------------------------------
    def results_path(self) -> Path:
        return _expand(self.results.path) if self.results.path else default_results_path()

    def state_dir(self) -> Path:
        return self.results_path().parent

    def workspaces_dir(self) -> Path:
        if self.workspaces_root:
            return _expand(self.workspaces_root)
        return self.state_dir() / "workspaces"

    def spool_path(self) -> Path:
        if self.gaps.spool_path:
            return _expand(self.gaps.spool_path)
        return self.state_dir() / "gap-spool.jsonl" if self.results.path else default_spool_path()

    def findings_path(self, run_id: str) -> Path:
        template = self.findings.path or str(self.state_dir() / "findings" / "{run_id}.json")
        return _expand(template.replace("{run_id}", run_id))

    def skills_dir(self) -> Path | None:
        if self.skills_root is None:
            return None
        root = _expand(self.skills_root)
        return root if root.is_absolute() else _expand(self.repo_root) / root

    def digest(self) -> str:
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


def _expand(value: str) -> Path:
    return Path(os.path.expanduser(value))


class ConfigError(ValueError):
    """Guard 0: the config file is missing, unparsable or schema-invalid."""


def load_config(path: str | Path) -> NightlyConfig:
    p = _expand(str(path))
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read config {p}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"config {p} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config {p} must be a YAML mapping")
    try:
        return NightlyConfig.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(x) for x in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()
        )
        raise ConfigError(f"config {p} is invalid: {problems}") from exc


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


Pair = tuple[AgentScenario, str]


def plan_pairs(scenarios: list[AgentScenario], vendors: list[str]) -> list[Pair]:
    """Deterministic order: scenarios sorted by id, then vendors in config order."""
    pairs: list[Pair] = []
    for scenario in sorted(scenarios, key=lambda s: s.id):
        for vendor in vendors:
            if vendor in scenario.vendors:
                pairs.append((scenario, vendor))
    return pairs


def effective_vendors(scenarios: list[AgentScenario], vendors: list[str]) -> list[str]:
    declared = {v for s in scenarios for v in s.vendors}
    return [v for v in vendors if v in declared]


def evaluate_caps(pairs: list[Pair], caps: Caps) -> dict[str, Any]:
    per_vendor: dict[str, int] = {}
    for _, vendor in pairs:
        per_vendor[vendor] = per_vendor.get(vendor, 0) + 1
    problems: list[str] = []
    if len(pairs) > caps.max_pairs:
        problems.append(f"{len(pairs)} planned pairs > max_pairs {caps.max_pairs}")
    for vendor, n in sorted(per_vendor.items()):
        if n > caps.max_pairs_per_vendor:
            problems.append(
                f"vendor {vendor}: {n} pairs > max_pairs_per_vendor {caps.max_pairs_per_vendor}"
            )
    return {
        "planned_pairs": len(pairs),
        "per_vendor": per_vendor,
        "caps": caps.model_dump(),
        "exceeded": problems,
        "ok": not problems,
    }


def _git_head(path: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@contextmanager
def _run_lock(lock_path: Path) -> Iterator[bool]:
    """Non-blocking exclusive flock; yields whether it was acquired."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def default_executor_factory(cfg: NightlyConfig) -> ScenarioExecutor:
    return CLIVendorExecutor(
        cfg.vendor_commands,
        timeout_seconds=cfg.caps.per_pair_timeout_seconds,
        skills_root=cfg.skills_dir(),
        env_scrub=cfg.env_scrub,
        env_set=cfg.env_set,
        always_scrub=[cfg.gaps.api_key_env, cfg.gaps.coordinator_url_env],
    )


def _new_run_id(now: datetime) -> str:
    return f"nightly-{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def _prune_run_dirs(workspaces_root: Path, keep: int) -> None:
    if not workspaces_root.is_dir():
        return
    runs = sorted((d for d in workspaces_root.iterdir() if d.is_dir()), key=lambda d: d.name)
    stale = runs[: max(0, len(runs) - keep)]
    for d in stale:
        shutil.rmtree(d, ignore_errors=True)


def _remove_workspace(workdir: Path) -> None:
    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(origin_path_for(workdir), ignore_errors=True)
    shutil.rmtree(bin_dir_for(workdir), ignore_errors=True)


def _load_suite(cfg: NightlyConfig) -> list[AgentScenario]:
    scenarios = load_scenarios(_expand(cfg.scenarios_dir))
    if not scenarios:
        raise ScenarioLoadError(f"no scenarios found under {cfg.scenarios_dir}")
    return scenarios


def dry_run(cfg: NightlyConfig) -> int:
    """Evaluate guards 1-5 without acting on them (design D4)."""
    kill = _expand(cfg.disable_file).exists() if cfg.disable_file else False
    report: dict[str, Any] = {
        "enabled": cfg.enabled,
        "kill_file_present": kill,
        "would_run": cfg.enabled and not kill,
    }
    code = EXIT_OK
    try:
        scenarios = _load_suite(cfg)
    except ScenarioLoadError as exc:
        print(json.dumps({**report, "error": str(exc)}, indent=2))
        return EXIT_CONFIG
    vendors = effective_vendors(scenarios, cfg.vendors)
    pairs = plan_pairs(scenarios, cfg.vendors)
    caps = evaluate_caps(pairs, cfg.caps)
    report["effective_vendors"] = vendors
    report["planned_pairs"] = [[s.id, v] for s, v in pairs]
    report["cap_evaluation"] = caps
    if len(vendors) < 2:
        report["error"] = "fewer than 2 effective vendors"
        code = EXIT_CONFIG
    elif not caps["ok"]:
        report["error"] = "; ".join(caps["exceeded"])
        code = EXIT_CONFIG
    print(json.dumps(report, indent=2))
    return code


def run_nightly(
    config_path: str | Path,
    *,
    dry: bool = False,
    executor_factory: Callable[[NightlyConfig], ScenarioExecutor] = default_executor_factory,
    coordinator_sink: MemorySink | None = None,
    judge_backend: TrajectoryJudgeBackend | None = None,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = utc_now,
) -> int:
    """Run the nightly suite and return the process exit code."""
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        print(f"agent-scenarios nightly: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if dry:
        return dry_run(cfg)

    store = JsonlResultsStore(cfg.results_path())
    started = now()
    run_id = _new_run_id(started)
    digest = cfg.digest()

    def finish(
        status: RunStatus,
        *,
        reason: str | None,
        planned: int = 0,
        executed: int = 0,
        repo_sha: str | None = None,
        skills_sha: str | None = None,
    ) -> None:
        store.append([
            RunRecord(
                run_id=run_id, started_at=started.isoformat(), finished_at=now().isoformat(),
                status=status, planned_pairs=planned, executed_pairs=executed,
                vendors=list(cfg.vendors), config_digest=digest, repo_sha=repo_sha,
                skills_sha=skills_sha, reason=reason,
            )
        ])

    # Guard 1 / 2: off-switches. No executor is constructed on these paths.
    if not cfg.enabled:
        finish("disabled", reason="enabled: false")
        print(f"nightly {run_id}: disabled (enabled: false)")
        return EXIT_OK
    if cfg.disable_file and _expand(cfg.disable_file).exists():
        finish("disabled", reason=f"kill-file present: {cfg.disable_file}")
        print(f"nightly {run_id}: disabled (kill-file {cfg.disable_file})")
        return EXIT_OK

    with _run_lock(lock_path_for(store.path)) as acquired:
        if not acquired:  # Guard 3
            finish("locked", reason="another nightly run holds the lock")
            print(f"nightly {run_id}: locked (another run in progress)")
            return EXIT_OK
        return _locked_run(
            cfg, store, run_id, started, finish, executor_factory, coordinator_sink,
            judge_backend, clock, now,
        )


def _locked_run(
    cfg: NightlyConfig,
    store: JsonlResultsStore,
    run_id: str,
    started: datetime,
    finish: Callable[..., None],
    executor_factory: Callable[[NightlyConfig], ScenarioExecutor],
    coordinator_sink: MemorySink | None,
    judge_backend: TrajectoryJudgeBackend | None,
    clock: Callable[[], float],
    now: Callable[[], datetime],
) -> int:
    spool = SpoolMemorySink(cfg.spool_path())
    sink: MemorySink = coordinator_sink or CoordinatorMemorySink.from_env(
        cfg.gaps.coordinator_url_env, cfg.gaps.api_key_env
    )
    if cfg.gaps.enabled:
        try:  # replay what a previous offline night could not deliver
            flush_spool(spool, sink)
        except Exception as exc:
            logger.warning("gap spool flush failed: %s", exc)

    try:
        scenarios = _load_suite(cfg)
    except ScenarioLoadError as exc:
        finish("config_error", reason=str(exc))
        print(f"agent-scenarios nightly: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    vendors = effective_vendors(scenarios, cfg.vendors)
    if len(vendors) < 2:  # Guard 4
        reason = f"fewer than 2 effective vendors: {vendors}"
        finish("config_error", reason=reason)
        print(f"agent-scenarios nightly: {reason}", file=sys.stderr)
        return EXIT_CONFIG

    pairs = plan_pairs(scenarios, cfg.vendors)
    caps = evaluate_caps(pairs, cfg.caps)
    if not caps["ok"]:  # Guard 5
        reason = "; ".join(caps["exceeded"])
        finish("cap_exceeded", reason=reason, planned=len(pairs))
        print(f"agent-scenarios nightly: cap exceeded: {reason}", file=sys.stderr)
        return EXIT_CONFIG

    repo_sha = _git_head(_expand(cfg.repo_root))
    skills_dir = cfg.skills_dir()
    skills_sha = compute_skills_sha(skills_dir) if skills_dir is not None else None
    skill_of = {s.id: s.skill_under_test for s in scenarios}
    source_paths = {s.id: s.source_path or "" for s in scenarios}

    workspaces = cfg.workspaces_dir()
    _prune_run_dirs(workspaces, cfg.retain_failed_runs)
    run_dir = workspaces / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    executor = executor_factory(cfg)
    budget_seconds = cfg.caps.max_wall_clock_minutes * 60
    t0 = clock()
    matrices: dict[str, ParityMatrix] = {}
    statuses: list[str] = []
    executed = 0
    budget_hit = False

    for scenario, vendor in pairs:
        if budget_hit or clock() - t0 >= budget_seconds:
            budget_hit = True
            store.append([
                skipped_budget_record(
                    run_id, scenario.id, scenario.skill_under_test, vendor,
                    family_of=skill_family, repo_sha=repo_sha, skills_sha=skills_sha,
                    recorded_at=now(),
                )
            ])
            statuses.append("skipped_budget")
            continue
        single = scenario.model_copy(update={"vendors": [vendor]})
        pair_start = clock()
        matrix = run_scenario(
            single, executor, judge_backend=judge_backend, workspaces_root=run_dir
        )
        duration = max(0.0, clock() - pair_start)
        executed += 1
        records: list[ResultRecord] = records_from_matrices(
            run_id, [matrix], skill_of=skill_of, family_of=skill_family,
            durations={(scenario.id, vendor): duration}, repo_sha=repo_sha,
            skills_sha=skills_sha, recorded_at=now(),
        )
        store.append(records)  # incremental: a kill mid-run keeps every scored pair
        status = records[0].deterministic_status
        statuses.append(status)
        merged = matrices.setdefault(
            scenario.id,
            ParityMatrix(scenario_id=scenario.id, scenario_name=scenario.name, results=[]),
        )
        merged.results.extend(matrix.results)
        if status == "pass":
            _remove_workspace(run_dir / f"{scenario.id}--{vendor}")

    ordered = [matrices[s.id] for s in sorted(scenarios, key=lambda s: s.id) if s.id in matrices]
    findings_error: str | None = None
    try:
        emit_findings(
            matrices=ordered, output_path=cfg.findings_path(run_id), target=run_id,
            source_paths=source_paths,
        )
    except (OSError, ValueError) as exc:
        # The review artifact is part of the run's contract; losing it is an
        # infrastructure failure, so the run is recorded and exits non-green.
        findings_error = f"findings emission failed: {exc}"
        logger.warning("%s", findings_error)
    if cfg.gaps.enabled:
        entries = build_gap_entries(
            run_id, ordered, skill_of=skill_of, agent_id=cfg.gaps.agent_id,
            repo_sha=repo_sha, skills_sha=skills_sha,
        )
        emit_gaps(entries, sink, spool)

    status_name: RunStatus = "budget_exhausted" if budget_hit else "completed"
    skipped = statuses.count("skipped_budget")
    reasons = [f"{skipped} pair(s) skipped: wall-clock budget exhausted"] if budget_hit else []
    if findings_error:
        reasons.append(findings_error)
    finish(
        status_name,
        reason="; ".join(reasons) or None,
        planned=len(pairs), executed=executed, repo_sha=repo_sha, skills_sha=skills_sha,
    )

    counts = {k: statuses.count(k) for k in ("pass", "fail", "error", "skipped_budget")}
    print(f"nightly {run_id}: {status_name} {json.dumps(counts)}")
    if counts["fail"]:
        return EXIT_FAIL
    if counts["error"] or budget_hit or findings_error:
        if findings_error:
            print(f"nightly {run_id}: {findings_error}")
        return EXIT_NOT_GREEN
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def add_parser(subparsers: Any) -> argparse.ArgumentParser:
    nightly: argparse.ArgumentParser = subparsers.add_parser(
        "nightly", help="run the seed suite across vendors under caps (off by default)"
    )
    nightly.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="nightly config YAML")
    nightly.add_argument(
        "--dry-run", action="store_true",
        help="print the planned pairs and cap evaluation; run nothing, write nothing",
    )
    nightly.set_defaults(func=_cmd_nightly)
    return nightly


def _cmd_nightly(args: argparse.Namespace) -> int:
    return run_nightly(args.config, dry=args.dry_run)


__all__ = [
    "Caps",
    "ConfigError",
    "NightlyConfig",
    "add_parser",
    "default_executor_factory",
    "dry_run",
    "effective_vendors",
    "evaluate_caps",
    "load_config",
    "plan_pairs",
    "run_nightly",
]
