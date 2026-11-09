#!/usr/bin/env python3
"""Implementation strategy selector for the automated-dev-loop feature.

Per-package decision logic for choosing between:
- "alternatives": 3 independent implementations + synthesis
- "lead_review": 1 implements + others review

Scoring criteria (each 0-1, threshold >= 2.0 for alternatives):
1. loc_estimate < 200 → 1.0
2. alternatives_count >= 2 → 1.0
3. package_kind in (algorithm, data_model) → 1.0
4. len(available_vendors) >= 3 → 1.0

Run via skills venv:
  skills/.venv/bin/python scripts/implementation_strategy_selector.py <work-packages.yaml>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None


ALTERNATIVES_THRESHOLD = 2.0
ALTERNATIVES_KINDS = frozenset({"algorithm", "data_model"})
INTEGRATION_TYPES = frozenset({"integration", "integrate"})

_STRATEGIES = ("alternatives", "lead_review")
_STRATEGY_CRITERIA = {
    "alternatives": (
        "Worth three independent implementations plus synthesis -- there "
        "are genuinely different plausible designs worth comparing."
    ),
    "lead_review": (
        "One implementation plus review is enough -- the design space is "
        "narrow or the package is straightforward."
    ),
}

DEFAULT_STRATEGY_CONFIDENCE_FLOOR = 0.5
_STRATEGY_JUDGMENT_CONFIG_PATH = _SCRIPTS_DIR / "implementation-strategy-judgment.json"

_HEADING_RE = re.compile(r"^#+\s+(.*)$", re.MULTILINE)


def _score_loc(metadata: dict[str, Any]) -> float:
    """Score based on lines-of-code estimate."""
    loc = metadata.get("loc_estimate")
    if loc is None:
        return 0.0
    return 1.0 if loc < 200 else 0.0


def _score_alternatives_count(metadata: dict[str, Any]) -> float:
    """Score based on number of known alternative approaches."""
    count = metadata.get("alternatives_count")
    if count is None:
        return 0.0
    return 1.0 if count >= 2 else 0.0


def _score_package_kind(metadata: dict[str, Any]) -> float:
    """Score based on package kind (algorithm/data_model favors alternatives)."""
    kind = metadata.get("package_kind")
    if kind is None:
        return 0.0
    return 1.0 if kind in ALTERNATIVES_KINDS else 0.0


def _score_vendor_count(available_vendors: list[str]) -> float:
    """Score based on number of available vendors."""
    return 1.0 if len(available_vendors) >= 3 else 0.0


def _is_integration_package(package: dict[str, Any]) -> bool:
    """Check if a package is an integration-type package."""
    pkg_type = package.get("task_type", package.get("type", ""))
    pkg_id = package.get("package_id", package.get("id", ""))
    return pkg_type in INTEGRATION_TYPES or pkg_id.startswith("wp-integration")


def _compute_score(
    metadata: dict[str, Any],
    available_vendors: list[str],
) -> float:
    """Compute total strategy score for a package."""
    return (
        _score_loc(metadata)
        + _score_alternatives_count(metadata)
        + _score_package_kind(metadata)
        + _score_vendor_count(available_vendors)
    )


def select_lead_vendor(
    available_vendors: list[str],
    recall_fn: Callable[..., Any] | None = None,
) -> str:
    """Select the best vendor to be lead implementer.

    If recall_fn is provided, queries for recent loop_completion memories
    to find vendor effectiveness stats. Selects vendor with highest fix
    success rate.

    Falls back to first available vendor if recall_fn is None or returns
    no useful data.
    """
    if not available_vendors:
        return ""

    if recall_fn is not None:
        try:
            memories = recall_fn("loop_completion")
            if memories and isinstance(memories, list):
                # Extract vendor stats from memories
                vendor_scores: dict[str, float] = {}
                for memory in memories:
                    data = memory if isinstance(memory, dict) else {}
                    vendor = data.get("vendor")
                    success_rate = data.get("fix_success_rate")
                    if (
                        vendor
                        and vendor in available_vendors
                        and isinstance(success_rate, (int, float))
                    ):
                        # Keep best score per vendor
                        if vendor not in vendor_scores or success_rate > vendor_scores[vendor]:
                            vendor_scores[vendor] = success_rate

                if vendor_scores:
                    return max(vendor_scores, key=lambda v: vendor_scores[v])
        except Exception:
            pass  # Fall through to default

    return available_vendors[0]


def load_strategy_confidence_floor(config_path: Path | None = None) -> float:
    """Read the optional sidecar JSON, falling back to the module default.

    Mirrors gatekeeper_shadow.load_shadow_thresholds and
    triage.load_deep_analysis_floor: a malformed or missing sidecar
    degrades to the default rather than raising.
    """
    path = config_path or _STRATEGY_JUDGMENT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_STRATEGY_CONFIDENCE_FLOOR
    if not isinstance(raw, dict):
        return DEFAULT_STRATEGY_CONFIDENCE_FLOOR
    try:
        return float(raw.get("confidence_floor", DEFAULT_STRATEGY_CONFIDENCE_FLOOR))
    except (TypeError, ValueError):
        return DEFAULT_STRATEGY_CONFIDENCE_FLOOR


def _design_section_for_package(design_text: str, pkg_id: str) -> str | None:
    """The body of the design.md section whose heading names *pkg_id*.

    Splits on top-level markdown headings and returns the text between a
    heading containing `pkg_id` (case-insensitive substring) and the next
    heading. Mirrors review_ledger.derive_spec_file's heuristic shape:
    explicit substring match, `None` when nothing matches, never raises.
    """
    matches = list(_HEADING_RE.finditer(design_text))
    pkg_id_lower = pkg_id.lower()
    for idx, match in enumerate(matches):
        if pkg_id_lower not in match.group(1).lower():
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(design_text)
        return design_text[start:end].strip()
    return None


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _classify_package(
    pkg_id: str,
    metadata: dict[str, Any],
    design_section: str | None,
    available_vendors: list[str],
) -> str | None:
    """Ask one calibrated judgment for this package's strategy.

    Returns `None` on any unavailability (module missing, `decide()`
    returns no usable answer, or its confidence is below the configured
    floor) -- never raises, never guesses. Callers fall back to the
    existing weighted-sum rule. `available_vendors` is judgment context
    (D1) -- never a pre-check that runs before this function is called;
    the existing weighted-sum fallback's own (non-gated) treatment of
    vendor count is untouched regardless of what happens here.
    """
    if system_one_decisions is None:
        return None

    state: dict[str, Any] = {
        "metadata": dict(metadata),
        "available_vendor_count": len(available_vendors),
    }
    if design_section:
        state["design_section"] = design_section
    questions = {
        "strategy": {
            "type": "choice",
            "instructions": (
                "Given this package's metadata and design excerpt, is it "
                "worth three independent implementations, or is one "
                "implementation plus review enough?"
            ),
            "criteria": _STRATEGY_CRITERIA,
        },
    }

    answers = system_one_decisions.decide(
        state, questions, site="autopilot.implementation_strategy_selector",
    )
    if not answers:
        return None

    answer = answers.get("strategy") if hasattr(answers, "get") else None
    if answer is None:
        return None
    strategy = _answer_field(answer, "choice")
    if strategy not in _STRATEGIES:
        return None
    confidence = _answer_field(answer, "confidence")
    if not isinstance(confidence, (int, float)):
        return None
    if confidence < load_strategy_confidence_floor():
        return None
    return strategy


def select_strategies(
    work_packages_path: Path,
    design_path: Path | None = None,
    available_vendors: list[str] | None = None,
    recall_fn: Callable[..., Any] | None = None,
) -> dict[str, str]:
    """Select implementation strategy for each work package.

    Args:
        work_packages_path: Path to work-packages.yaml.
        design_path: Optional path to design.md. Read for a per-package
            matching section (D2) that forms part of the judgment's state.
        available_vendors: List of available vendor names.
        recall_fn: Optional function to recall vendor effectiveness from
            coordinator memory.

    Returns:
        Mapping of package_id to strategy ("alternatives" or "lead_review").
    """
    if available_vendors is None:
        available_vendors = []

    with open(work_packages_path) as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    packages = data.get("packages", [])
    if not packages:
        return {}

    design_text: str | None = None
    if design_path is not None:
        try:
            design_text = design_path.read_text(encoding="utf-8")
        except OSError:
            design_text = None

    strategies: dict[str, str] = {}

    for package in packages:
        pkg_id = package.get("package_id", package.get("id", ""))
        if not pkg_id:
            continue

        # Integration packages always use lead_review
        if _is_integration_package(package):
            strategies[pkg_id] = "lead_review"
            continue

        metadata = package.get("metadata", {})
        if not metadata:
            # No metadata → default to lead_review
            strategies[pkg_id] = "lead_review"
            continue

        design_section = (
            _design_section_for_package(design_text, pkg_id)
            if design_text is not None else None
        )
        judged = _classify_package(pkg_id, metadata, design_section, available_vendors)
        if judged is not None:
            strategies[pkg_id] = judged
            continue

        score = _compute_score(metadata, available_vendors)
        strategies[pkg_id] = "alternatives" if score >= ALTERNATIVES_THRESHOLD else "lead_review"

    return strategies


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Select implementation strategy per work package.",
    )
    parser.add_argument(
        "work_packages",
        type=Path,
        help="Path to work-packages.yaml",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=None,
        help="Path to design.md (optional)",
    )
    parser.add_argument(
        "--vendors",
        nargs="*",
        default=[],
        help="Available vendor names",
    )
    args = parser.parse_args()

    strategies = select_strategies(
        work_packages_path=args.work_packages,
        design_path=args.design,
        available_vendors=args.vendors,
    )

    print(json.dumps(strategies, indent=2))


if __name__ == "__main__":
    main()
