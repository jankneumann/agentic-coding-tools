"""Path-glob rule resolution for the review packet.

Ported from alibaba/open-code-review's rule-resolution chain
(internal/config/rules/, Apache-2.0 License,
https://github.com/alibaba/open-code-review, read 2026-09-14), narrowed to
two layers: a project file at ``<repo>/.review-rules.json`` over the
embedded default sidecar shipped beside this module
(``review-rules.json``). Within a layer, entries are tried in declaration
order and the first matching glob wins; a project-layer match always
outranks any default-layer match, but the default layer still applies when
the project layer has no match (or does not exist).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

DEFAULT_RULES_PATH = Path(__file__).parent / "review-rules.json"
PROJECT_RULES_FILENAME = ".review-rules.json"
DEFAULT_COVERAGE_QUORUM_THRESHOLD = 0.8
DEFAULT_MATCH_THRESHOLD = 0.6
DEFAULT_RULE_TEXT = (
    "Review for correctness, security, and adherence to this repository's "
    "conventions."
)


@dataclass
class RuleMatch:
    source: str  # "project" | "default"
    pattern: str
    text: str


@dataclass
class RuleConfig:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    generated_paths: list[str] = field(default_factory=list)
    project_rules: list[tuple[str, str]] = field(default_factory=list)
    default_rules: list[tuple[str, str]] = field(default_factory=list)
    coverage_quorum_threshold: float = DEFAULT_COVERAGE_QUORUM_THRESHOLD
    match_threshold: float = DEFAULT_MATCH_THRESHOLD


def _load_layer(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_config(repo_root: Path | None = None) -> RuleConfig:
    """Load the effective two-layer rule config.

    ``include``/``exclude``/``generated_paths``/``coverage_quorum_threshold``
    are overridden per-key by the project layer when it sets that key,
    otherwise inherited from the default layer — not merged, not replaced
    wholesale. Rule lists from both layers are kept separately so
    :func:`resolve_rule` can try project rules first, then fall through to
    default rules, per file.
    """
    default_doc = _load_layer(DEFAULT_RULES_PATH) or {}
    project_doc = (
        _load_layer(Path(repo_root) / PROJECT_RULES_FILENAME)
        if repo_root is not None
        else None
    )

    def _pick(key: str, default: Any) -> Any:
        if project_doc is not None and key in project_doc:
            return project_doc[key]
        return default

    return RuleConfig(
        include=list(_pick("include", default_doc.get("include", []))),
        exclude=list(_pick("exclude", default_doc.get("exclude", []))),
        generated_paths=list(
            _pick("generated_paths", default_doc.get("generated_paths", []))
        ),
        project_rules=[
            (r["path"], r["rule"]) for r in (project_doc or {}).get("rules", [])
        ],
        default_rules=[
            (r["path"], r["rule"]) for r in default_doc.get("rules", [])
        ],
        coverage_quorum_threshold=float(
            _pick(
                "coverage_quorum_threshold",
                default_doc.get(
                    "coverage_quorum_threshold", DEFAULT_COVERAGE_QUORUM_THRESHOLD,
                ),
            )
        ),
        match_threshold=float(
            _pick(
                "match_threshold",
                default_doc.get("match_threshold", DEFAULT_MATCH_THRESHOLD),
            )
        ),
    )


def _glob_match(path: str, pattern: str) -> bool:
    """Case-insensitive glob match, with one gitignore-style convenience.

    Plain :func:`fnmatch.fnmatch` (this project's existing glob convention
    — see ``roadmap-runtime/scripts/scope_overlap.py``) requires a literal
    ``/`` before the filename for a leading ``**/`` to match; it does not
    special-case "at the repository root". A rule pattern like ``**/*.py``
    is written to match a repo-root ``foo.py`` too, so a ``**/`` prefix is
    also tried against the path with that prefix stripped.
    """
    lowered_path, lowered_pattern = path.lower(), pattern.lower()
    if fnmatch(lowered_path, lowered_pattern):
        return True
    return lowered_pattern.startswith("**/") and fnmatch(
        lowered_path, lowered_pattern[3:]
    )


def resolve_rule(path: str, config: RuleConfig) -> RuleMatch:
    """First matching rule for *path*: project layer, then default layer."""
    for pattern, text in config.project_rules:
        if _glob_match(path, pattern):
            return RuleMatch(source="project", pattern=pattern, text=text)
    for pattern, text in config.default_rules:
        if _glob_match(path, pattern):
            return RuleMatch(source="default", pattern=pattern, text=text)
    return RuleMatch(source="default", pattern="(default)", text=DEFAULT_RULE_TEXT)


@dataclass
class RuleGroup:
    group_id: int
    source: str
    pattern: str
    files: list[str]
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "source": self.source,
            "pattern": self.pattern,
            "files": list(self.files),
        }


def group_files_by_rule(paths: list[str], config: RuleConfig) -> list[RuleGroup]:
    """Group *paths* (already in a stable order) by identical rule resolution.

    Files that resolve to the same ``(source, pattern, text)`` share one
    group so the packet renders the rule text once, per D4.
    """
    key_index: dict[tuple[str, str, str], int] = {}
    groups: list[RuleGroup] = []
    for path in paths:
        match = resolve_rule(path, config)
        key = (match.source, match.pattern, match.text)
        idx = key_index.get(key)
        if idx is None:
            idx = len(groups)
            key_index[key] = idx
            groups.append(
                RuleGroup(
                    group_id=idx + 1, source=match.source, pattern=match.pattern,
                    files=[], text=match.text,
                )
            )
        groups[idx].files.append(path)
    return groups
