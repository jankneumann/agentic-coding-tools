"""Entry gate for the automated dev loop.

Historically this module deterministically *blocked* automation by counting
lines of code and work packages against hard thresholds. That proved too
aggressive: autopilot already has strong downstream safeguards (multi-vendor
PLAN/IMPL review convergence, a VALIDATE phase, and a mandatory human merge
gate), so pre-blocking on raw size was redundant friction.

The gate now does two cheap, deterministic things:

1. **Scope-safety floor** — the *only* remaining hard block. A package that can
   write the entire repository (``**``, ``*``, ``.``) defeats worktree scope
   isolation, which no amount of downstream review recovers cleanly. This still
   requires ``--force``.

2. **Signal gathering** — it assembles a structured *risk + verifiability
   profile* of the change (``gather_signals``) without mapping any count to a
   verdict. That profile is handed to the GATEKEEPER judge sub-agent, which
   evaluates the change's *verifiability of outcomes* and *associated risk* and
   returns ``proceed`` / ``proceed_with_review`` / ``escalate``.

Former hard blockers (LOC, package count, external deps, db-migration signals)
are demoted to ``val_review_enabled`` + scheduling ``checkpoints`` +
informational ``warnings``. They inform the judge; they no longer gate.

``default_gate_verdict`` provides the permissive headless fallback used when no
judge model is reachable (CI, coordinator down, unit tests): proceed, enabling
validation review when any risk signal is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Scheduling thresholds. These NO LONGER block automation — they only decide
# when to inject wave/limit scheduling checkpoints and a dependency-review
# checkpoint. They are deliberately advisory.
DEFAULT_MAX_PACKAGES = 4
DEFAULT_MAX_EXTERNAL_DEPS = 2

# Signal keywords (informational — feed the judge, never force).
DB_MIGRATION_SIGNALS = {"migration", "db:"}
SECURITY_SIGNALS = {"auth", "crypto", "secret", "token"}
BROAD_WRITE_SCOPES = {"**", "**/*", "*", ".", "./"}


@dataclass
class GateResult:
    """Result of the entry gate assessment.

    ``force_required`` is now set by exactly one condition — a broad write
    scope — so it represents a genuine scope-safety concern rather than a
    complexity threshold. ``signals`` carries the risk + verifiability profile
    consumed by the GATEKEEPER judge.
    """

    allowed: bool = True
    warnings: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    val_review_enabled: bool = False
    force_required: bool = False
    signals: dict[str, Any] = field(default_factory=dict)


def _load_work_packages(work_packages_path: Path) -> dict[str, Any]:
    """Load and return parsed work-packages.yaml (empty dict if missing)."""
    path = Path(work_packages_path)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _get_thresholds(data: dict[str, Any]) -> tuple[int, int]:
    """Extract scheduling thresholds from work-packages.yaml or use built-ins."""
    defaults = data.get("defaults", {})
    auto_loop = defaults.get("auto_loop", {}) if isinstance(defaults, dict) else {}
    if not isinstance(auto_loop, dict):
        auto_loop = {}

    max_packages = auto_loop.get("max_packages", DEFAULT_MAX_PACKAGES)
    max_external_deps = auto_loop.get("max_external_deps", DEFAULT_MAX_EXTERNAL_DEPS)

    return int(max_packages), int(max_external_deps)


def _get_packages(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the list of packages from work-packages.yaml."""
    packages = data.get("packages", [])
    if not isinstance(packages, list):
        return []
    return [p for p in packages if isinstance(p, dict)]


def _sum_loc(packages: list[dict[str, Any]]) -> int | None:
    """Sum metadata.loc_estimate across packages. None if no package has it.

    Reported as a signal only — it never gates automation.
    """
    total = 0
    found_any = False
    for pkg in packages:
        metadata = pkg.get("metadata", {})
        if isinstance(metadata, dict) and "loc_estimate" in metadata:
            total += int(metadata["loc_estimate"])
            found_any = True
    return total if found_any else None


def _count_impl_packages(packages: list[dict[str, Any]]) -> int:
    """Count implementation packages, excluding wp-integration type."""
    count = 0
    for pkg in packages:
        pkg_type = pkg.get("task_type", pkg.get("type", ""))
        pkg_id = pkg.get("package_id", pkg.get("id", ""))
        # Exclude integration packages by type or id pattern
        if pkg_type in ("integration", "integrate") or pkg_id == "wp-integration":
            continue
        count += 1
    return count


def _count_external_deps(packages: list[dict[str, Any]]) -> int:
    """Count new external dependencies across all packages."""
    deps: set[str] = set()
    for pkg in packages:
        metadata = pkg.get("metadata", {})
        if isinstance(metadata, dict):
            pkg_deps = metadata.get("external_deps", [])
            if isinstance(pkg_deps, list):
                deps.update(pkg_deps)
    return len(deps)


def _text_contains_signal(text: str, signals: set[str]) -> bool:
    """Check if text contains any of the signal keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(signal in text_lower for signal in signals)


def _check_signals(packages: list[dict[str, Any]], signals: set[str]) -> bool:
    """Check package descriptions and lock keys for signal keywords."""
    for pkg in packages:
        description = pkg.get("description", "")
        if isinstance(description, str) and _text_contains_signal(description, signals):
            return True
        # Check lock keys — locks is an object {files: [], keys: []} in the schema
        locks = pkg.get("locks", {})
        if isinstance(locks, dict):
            for key in locks.get("keys", []):
                if isinstance(key, str) and _text_contains_signal(key, signals):
                    return True
            for fp in locks.get("files", []):
                if isinstance(fp, str) and _text_contains_signal(fp, signals):
                    return True
        elif isinstance(locks, list):
            # Backward compat: treat as flat list of strings
            for lock in locks:
                lock_str = str(lock) if not isinstance(lock, str) else lock
                if _text_contains_signal(lock_str, signals):
                    return True
    return False


def _has_broad_write_scope(packages: list[dict[str, Any]]) -> bool:
    """Return True when any package can write the whole repository."""
    for pkg in packages:
        scope = pkg.get("scope", {})
        if not isinstance(scope, dict):
            continue
        write_allow = scope.get("write_allow", [])
        if not isinstance(write_allow, list):
            continue
        for path in write_allow:
            if isinstance(path, str) and path.strip() in BROAD_WRITE_SCOPES:
                return True
    return False


def _add_checkpoint(result: GateResult, checkpoint: str) -> None:
    """Append checkpoint once while preserving insertion order."""
    if checkpoint not in result.checkpoints:
        result.checkpoints.append(checkpoint)


def gather_signals(
    work_packages_path: Path,
    proposal_path: Path | None = None,
) -> dict[str, Any]:
    """Assemble the risk + verifiability profile for the GATEKEEPER judge.

    This is pure observation: counts and booleans, never a verdict. The judge
    weighs these against the downstream safeguards (review convergence,
    validation, human merge gate) to decide whether outcomes are verifiable and
    the risk acceptable for autonomous execution.

    Verifiability facts (``has_proposal`` / ``has_specs`` / ``has_tasks``) are
    derived from the change directory — a change with specs and a task
    breakdown is materially easier to verify than a bare description.
    """
    data = _load_work_packages(work_packages_path)
    packages = _get_packages(data)
    change_dir = Path(work_packages_path).parent

    proposal = proposal_path if proposal_path is not None else change_dir / "proposal.md"

    return {
        # Risk surface
        "package_count": _count_impl_packages(packages),
        "total_loc_estimate": _sum_loc(packages),
        "external_dep_count": _count_external_deps(packages),
        "has_db_migration": _check_signals(packages, DB_MIGRATION_SIGNALS),
        "has_security_signal": _check_signals(packages, SECURITY_SIGNALS),
        "has_broad_write_scope": _has_broad_write_scope(packages),
        # Verifiability surface — what evidence exists to check outcomes against
        "has_proposal": Path(proposal).exists(),
        "has_specs": (change_dir / "specs").is_dir(),
        "has_tasks": (change_dir / "tasks.md").exists(),
        "has_work_packages": Path(work_packages_path).exists(),
    }


# Signal keys that, when truthy, indicate elevated risk worth a validation
# review even on the permissive path.
_RISK_SIGNAL_KEYS = (
    "has_db_migration",
    "has_security_signal",
    "has_broad_write_scope",
)


def default_gate_verdict(signals: dict[str, Any]) -> str:
    """Permissive fallback verdict when no judge model is reachable.

    Returns ``"proceed_with_review"`` when any risk signal is present (cheap
    insurance via the VAL_REVIEW phase), otherwise ``"proceed"``. It never
    returns ``"escalate"`` — blocking is reserved for the scope-safety floor
    (handled in ``assess_complexity``) and for an actual judge verdict.
    """
    if any(bool(signals.get(k)) for k in _RISK_SIGNAL_KEYS):
        return "proceed_with_review"
    return "proceed"


def assess_complexity(
    work_packages_path: Path,
    proposal_path: Path | None = None,
    force: bool = False,
) -> GateResult:
    """Assess a feature at the INIT gate.

    Applies the deterministic scope-safety floor (the only hard block),
    gathers the risk + verifiability ``signals`` profile, and surfaces
    advisory warnings / scheduling checkpoints. It does NOT block on size:
    LOC, package count, external deps, and db-migration signals are reported
    for the GATEKEEPER judge to weigh, not used to force ``--force``.

    Args:
        work_packages_path: Path to work-packages.yaml (may not exist yet).
        proposal_path: Optional path to proposal.md.
        force: Whether --force was provided (bypasses the scope-safety floor).

    Returns:
        GateResult with the permissive decision, signals, warnings, and
        scheduling checkpoints.
    """
    data = _load_work_packages(work_packages_path)
    max_packages, max_external_deps = _get_thresholds(data)
    packages = _get_packages(data)

    result = GateResult()
    result.signals = gather_signals(work_packages_path, proposal_path)

    # 1. Scope-safety floor — the ONLY hard block. A package that can write the
    #    whole repository defeats worktree scope isolation.
    if result.signals.get("has_broad_write_scope"):
        result.force_required = True
        result.warnings.append("Broad write scope detected; require --force")

    # 2. Package count is purely a scheduling signal now: a higher count usually
    #    means the work was decomposed well. Emit wave/limit checkpoints so the
    #    DAG scheduler paces itself; never force.
    impl_count = result.signals["package_count"]
    if impl_count > max_packages:
        result.warnings.append(
            f"Package count ({impl_count}) exceeds scheduling threshold "
            f"({max_packages}); pacing validation in waves"
        )
        _add_checkpoint(result, "wave-validation")
        if impl_count > max_packages * 2:
            _add_checkpoint(result, "limit-concurrency")

    # 3. External dependencies — informational + a dependency-review checkpoint.
    ext_deps = result.signals["external_dep_count"]
    if ext_deps > max_external_deps:
        result.warnings.append(
            f"External dependencies ({ext_deps}) exceeds threshold "
            f"({max_external_deps})"
        )
        _add_checkpoint(result, "dependency-review")

    # 4. Risk signals enable validation review (and a focused checkpoint) but no
    #    longer block — the judge and the downstream gates handle them.
    if result.signals.get("has_db_migration"):
        result.warnings.append("Database migration signal detected; enabling val review")
        result.val_review_enabled = True
        _add_checkpoint(result, "db-migration-review")

    if result.signals.get("has_security_signal"):
        result.val_review_enabled = True
        _add_checkpoint(result, "security-review")

    # Final decision — only the scope-safety floor can flip this.
    if result.force_required and not force:
        result.allowed = False

    return result
