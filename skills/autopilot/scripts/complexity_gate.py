"""Complexity gate for the automated dev loop.

Entry assessment that determines if a feature is suitable for full automation
based on LOC estimates, package count, external dependencies, and risk signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Built-in default thresholds
DEFAULT_MAX_LOC = 500
DEFAULT_MAX_PACKAGES = 4
DEFAULT_MAX_EXTERNAL_DEPS = 2

# Signal keywords
DB_MIGRATION_SIGNALS = {"migration", "db:"}
SECURITY_SIGNALS = {"auth", "crypto", "secret", "token"}


@dataclass
class GateResult:
    """Result of the complexity gate assessment."""

    allowed: bool = True
    warnings: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    val_review_enabled: bool = False
    force_required: bool = False


def _load_work_packages(work_packages_path: Path) -> dict[str, Any]:
    """Load and return parsed work-packages.yaml."""
    with open(work_packages_path) as f:
        return yaml.safe_load(f) or {}


def _get_thresholds(data: dict[str, Any]) -> tuple[int, int, int]:
    """Extract thresholds from work-packages.yaml defaults or use built-ins."""
    defaults = data.get("defaults", {})
    auto_loop = defaults.get("auto_loop", {}) if isinstance(defaults, dict) else {}
    if not isinstance(auto_loop, dict):
        auto_loop = {}

    max_loc = auto_loop.get("max_loc", DEFAULT_MAX_LOC)
    max_packages = auto_loop.get("max_packages", DEFAULT_MAX_PACKAGES)
    max_external_deps = auto_loop.get("max_external_deps", DEFAULT_MAX_EXTERNAL_DEPS)

    return int(max_loc), int(max_packages), int(max_external_deps)


def _get_packages(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the list of packages from work-packages.yaml."""
    packages = data.get("packages", [])
    if not isinstance(packages, list):
        return []
    return [p for p in packages if isinstance(p, dict)]


def _sum_loc(packages: list[dict[str, Any]]) -> int | None:
    """Sum metadata.loc_estimate across packages. Returns None if no package has it."""
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


def _check_signals(
    packages: list[dict[str, Any]], signals: set[str]
) -> bool:
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


def assess_complexity(
    work_packages_path: Path,
    proposal_path: Path | None = None,
    force: bool = False,
) -> GateResult:
    """Assess feature complexity and determine automation suitability.

    Args:
        work_packages_path: Path to work-packages.yaml
        proposal_path: Optional path to proposal.md (reserved for future use)
        force: Whether --force was provided to bypass thresholds

    Returns:
        GateResult with automation decision, warnings, and checkpoints.
    """
    data = _load_work_packages(work_packages_path)
    max_loc, max_packages, max_external_deps = _get_thresholds(data)
    packages = _get_packages(data)

    result = GateResult()

    # 1. LOC check
    total_loc = _sum_loc(packages)
    if total_loc is not None and total_loc > max_loc:
        result.force_required = True
        result.warnings.append(
            f"Total LOC estimate ({total_loc}) exceeds threshold ({max_loc})"
        )

    # 2. Package count check
    impl_count = _count_impl_packages(packages)
    if impl_count > max_packages:
        result.force_required = True
        result.warnings.append(
            f"Package count ({impl_count}) exceeds threshold ({max_packages})"
        )

    # 3. External dependencies check
    ext_deps = _count_external_deps(packages)
    if ext_deps > max_external_deps:
        result.warnings.append(
            f"External dependencies ({ext_deps}) exceeds threshold ({max_external_deps})"
        )

    # 4. DB migration signals
    if _check_signals(packages, DB_MIGRATION_SIGNALS):
        result.val_review_enabled = True
        result.checkpoints.append("db-migration-review")

    # 5. Security signals
    if _check_signals(packages, SECURITY_SIGNALS):
        result.val_review_enabled = True
        result.checkpoints.append("security-review")

    # Final decision
    if result.force_required and not force:
        result.allowed = False

    return result
