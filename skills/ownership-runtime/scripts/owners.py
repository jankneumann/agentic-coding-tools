"""Ownership map loader and resolver (design D3, D4, D5, D6, D13).

``load_ownership()`` reads ``openspec/owners.yaml`` and the principal registry and
returns an :class:`OwnershipContext`. An absent map is valid and means solo mode;
a present-but-invalid map raises :class:`OwnershipConfigError` (fail closed -- callers
must not catch it and fall back to solo).

Nothing here imports from the coordinator or opens a network connection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from principals import (
    OwnershipConfigError,
    Principal,
    default_repo_root,
    derive_mode,
    derive_solo_principal,
    read_registry,
)

__all__ = [
    "OwnerSet",
    "OwnershipConfigError",
    "OwnershipContext",
    "Principal",
    "Problem",
    "Rule",
    "collect_problems",
    "load_ownership",
    "pattern_matches",
]

OWNERS_RELPATH = "openspec/owners.yaml"
OWNERS_SCHEMA_NAME = "owners.schema.json"
PATTERN_SUBSET = (
    "supported path patterns use only `*`, `**` (as a whole path segment), `?`, "
    "an optional leading `/` and an optional trailing `/`; no `!` negation, "
    "no `[...]` classes, no whitespace"
)


@dataclass(frozen=True)
class OwnerSet:
    """Who owns a subject, and how that was decided."""

    owners: tuple[Principal, ...]
    decision_rights: tuple[Principal, ...]
    acceptance_rights: tuple[Principal, ...]
    source: str  # explicit | default_owner | solo
    matched_rule: str | None = None

    @property
    def owner_ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.owners)


@dataclass(frozen=True)
class Problem:
    """A configuration problem (always an error in the check)."""

    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class _Assignment:
    owners: tuple[Principal, ...]
    decision_rights: tuple[Principal, ...]
    acceptance_rights: tuple[Principal, ...]

    def owner_set(self, matched_rule: str) -> OwnerSet:
        return OwnerSet(
            self.owners, self.decision_rights, self.acceptance_rights, "explicit", matched_rule
        )


@dataclass(frozen=True)
class Rule:
    """One path rule: an explicit ``paths`` entry or one implied by a capability."""

    pattern: str
    label: str  # matched_rule reported on a hit
    assignment: _Assignment = field(repr=False)
    implied: bool
    order: int
    regex: re.Pattern[str] = field(repr=False)

    @property
    def literal_length(self) -> int:
        cut = [i for i in (self.pattern.find("*"), self.pattern.find("?")) if i >= 0]
        return min(cut) if cut else len(self.pattern)

    @property
    def sort_key(self) -> tuple[int, int, int]:
        """Specificity then rule order; the greatest key wins (D4)."""
        return (self.literal_length, len(self.pattern), self.order)


# --------------------------------------------------------------------------- patterns


def _segment_regex(segment: str) -> str:
    out: list[str] = []
    for ch in segment:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a restricted glob with the CODEOWNERS/gitignore semantics of D3."""
    dir_only = pattern.endswith("/")
    segments = pattern.strip("/").split("/")
    for segment in segments:
        if "**" in segment and segment != "**":
            raise OwnershipConfigError(
                "invalid_map",
                f"path pattern '{pattern}': `**` must be a whole path segment",
                pattern,
            )
    anchored = pattern.startswith("/") or len(segments) > 1
    count = len(segments)
    out = "" if anchored else "(?:.*/)?"
    skip_sep = False
    for index, segment in enumerate(segments):
        last = index == count - 1
        sep = "" if index == 0 or skip_sep else "/"
        skip_sep = False
        if segment == "**":
            if last:
                out = out + ".+" if count == 1 else out + "/.+"
            elif index == 0:
                out += "(?:.*/)?"
                skip_sep = True
            else:
                out += "/(?:.*/)?"
                skip_sep = True
        else:
            out += sep + _segment_regex(segment)
    if dir_only:
        out += "/.+"
    elif segments[-1] != "**":
        out += "(?:/.+)?"
    return re.compile(out, re.DOTALL)


def pattern_matches(pattern: str, path: str) -> bool:
    """Whether ``pattern`` selects the repo-relative file ``path`` (D3 table)."""
    return compile_pattern(pattern).fullmatch(_normalise(path)) is not None


def _normalise(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


# --------------------------------------------------------------------------- context


@dataclass(frozen=True)
class OwnershipContext:
    """Resolved ownership for one repository."""

    repo_root: Path
    mode: str  # solo | team
    has_map: bool
    default_owner: Principal | None
    humans: tuple[Principal, ...]
    solo_principal: Principal | None
    agent_names: frozenset[str]
    registry_path: Path | None
    capabilities: dict[str, _Assignment] = field(default_factory=dict, repr=False)
    roadmap_items: dict[str, _Assignment] = field(default_factory=dict, repr=False)
    rules: tuple[Rule, ...] = ()  # implied rules first, then explicit, in file order
    _ranked: tuple[Rule, ...] = field(default=(), repr=False)

    def _solo(self) -> OwnerSet:
        assert self.solo_principal is not None
        p = (self.solo_principal,)
        return OwnerSet(p, p, p, "solo", None)

    def _default(self) -> OwnerSet:
        assert self.default_owner is not None
        p = (self.default_owner,)
        return OwnerSet(p, p, p, "default_owner", None)

    def resolve_capability(self, name: str) -> OwnerSet:
        if not self.has_map:
            return self._solo()
        found = self.capabilities.get(name)
        return found.owner_set(name) if found else self._default()

    def resolve_roadmap_item(self, roadmap_id: str, item_id: str) -> OwnerSet:
        if not self.has_map:
            return self._solo()
        key = f"{roadmap_id}/{item_id}"
        found = self.roadmap_items.get(key)
        return found.owner_set(key) if found else self._default()

    def resolve_path(self, path: str) -> OwnerSet:
        if not self.has_map:
            return self._solo()
        normalised = _normalise(path)
        for rule in self._ranked:
            if rule.regex.fullmatch(normalised):
                return rule.assignment.owner_set(rule.label)
        return self._default()


# --------------------------------------------------------------------------- loading


def _load_schema(repo_root: Path) -> dict[str, Any]:
    here = Path(__file__).resolve().parent.parent
    for candidate in (
        here / "install_assets" / "openspec" / "schemas" / OWNERS_SCHEMA_NAME,
        repo_root / "openspec" / "schemas" / OWNERS_SCHEMA_NAME,
    ):
        if candidate.is_file():
            loaded: dict[str, Any] = json.loads(candidate.read_text(encoding="utf-8"))
            return loaded
    raise OwnershipConfigError(
        "invalid_map", f"{OWNERS_SCHEMA_NAME} is not installed", OWNERS_SCHEMA_NAME
    )


def _schema_problems(raw: Any, repo_root: Path) -> list[Problem]:
    validator = Draft202012Validator(_load_schema(repo_root))
    problems: list[Problem] = []
    for error in sorted(validator.iter_errors(raw), key=lambda e: [str(p) for p in e.absolute_path]):
        where = "/".join(str(p) for p in error.absolute_path) or "<root>"
        message = f"{OWNERS_RELPATH}: {where}: {error.message}"
        if list(error.absolute_path)[:2] == ["assignments", "paths"]:
            message += f" ({PATTERN_SUBSET})"
        problems.append(Problem("invalid_map", where, message))
    return problems


def _owner_lists(doc: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    """``(assignment description, field, ids)`` for every owner list in the map."""
    found: list[tuple[str, str, list[str]]] = [
        ("default_owner", "default_owner", [doc["default_owner"]])
    ]
    for kind, table in (doc.get("assignments") or {}).items():
        for key, entry in table.items():
            for fld in ("owners", "decision_rights", "acceptance_rights"):
                if fld in entry:
                    found.append((f"assignments.{kind}.{key}", fld, list(entry[fld])))
    return found


def collect_problems(
    repo_root: Path | None = None,
) -> tuple[OwnershipContext | None, list[Problem]]:
    """Build the context; return every configuration problem instead of raising.

    The context is ``None`` when any problem prevents resolution.
    """
    root = (repo_root or default_repo_root()).resolve()
    map_path = root / OWNERS_RELPATH
    doc: dict[str, Any] | None = None
    problems: list[Problem] = []

    if map_path.is_file():
        try:
            raw = yaml.safe_load(map_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            return None, [Problem("invalid_map", OWNERS_RELPATH, f"cannot parse {OWNERS_RELPATH}: {exc}")]
        problems = _schema_problems(raw, root)
        if problems:
            return None, problems
        doc = raw
        for pattern in (doc.get("assignments") or {}).get("paths", {}):
            try:
                compile_pattern(pattern)
            except OwnershipConfigError as exc:
                problems.append(Problem(exc.code, pattern, exc.message))
        if problems:
            return None, problems

    try:
        humans, agent_names, registry_path = read_registry(
            root, doc.get("registry") if doc else None
        )
    except OwnershipConfigError as exc:
        return None, [Problem(exc.code, exc.subject or "registry", exc.message)]

    mode = derive_mode(humans)

    if doc is None:
        if mode == "team":
            return None, [
                Problem(
                    "team_registry_without_map",
                    "openspec/owners.yaml",
                    f"the registry declares {len(humans)} human principals but "
                    f"{OWNERS_RELPATH} does not exist; author {OWNERS_RELPATH} with a "
                    f"`default_owner` (an error, not a fallback: a multi-human repository "
                    f"has no sole principal)",
                )
            ]
        ctx = OwnershipContext(
            repo_root=root,
            mode=mode,
            has_map=False,
            default_owner=None,
            humans=tuple(humans),
            solo_principal=derive_solo_principal(root, humans),
            agent_names=frozenset(agent_names),
            registry_path=registry_path,
        )
        return ctx, []

    by_id = {h.id: h for h in humans}
    for where, fld, ids in _owner_lists(doc):
        for owner_id in ids:
            if owner_id in by_id:
                continue
            if owner_id in agent_names:
                problems.append(
                    Problem(
                        "agent_as_owner",
                        owner_id,
                        f"{where}.{fld}: '{owner_id}' is an agent; owners must be human principals",
                    )
                )
            else:
                problems.append(
                    Problem(
                        "unknown_owner",
                        owner_id,
                        f"{where}.{fld}: '{owner_id}' is not a registered human principal",
                    )
                )
    if problems:
        return None, problems

    def assignment(entry: dict[str, Any]) -> _Assignment:
        owners = tuple(by_id[i] for i in entry["owners"])
        return _Assignment(
            owners,
            tuple(by_id[i] for i in entry.get("decision_rights", entry["owners"])),
            tuple(by_id[i] for i in entry.get("acceptance_rights", entry["owners"])),
        )

    assignments = doc.get("assignments") or {}
    capabilities = {k: assignment(v) for k, v in (assignments.get("capabilities") or {}).items()}
    roadmap_items = {k: assignment(v) for k, v in (assignments.get("roadmap_items") or {}).items()}
    rules: list[Rule] = []
    for cap, assigned in capabilities.items():
        for base in ("openspec/specs", "openspec/contracts"):
            pattern = f"{base}/{cap}/"
            rules.append(
                Rule(pattern, f"capability:{cap}", assigned, True, len(rules), compile_pattern(pattern))
            )
    for pattern, entry in (assignments.get("paths") or {}).items():
        rules.append(
            Rule(pattern, pattern, assignment(entry), False, len(rules), compile_pattern(pattern))
        )

    ctx = OwnershipContext(
        repo_root=root,
        mode=mode,
        has_map=True,
        default_owner=by_id[doc["default_owner"]],
        humans=tuple(humans),
        solo_principal=None,
        agent_names=frozenset(agent_names),
        registry_path=registry_path,
        capabilities=capabilities,
        roadmap_items=roadmap_items,
        rules=tuple(rules),
        _ranked=tuple(sorted(rules, key=lambda r: r.sort_key, reverse=True)),
    )
    return ctx, []


def load_ownership(repo_root: Path | None = None) -> OwnershipContext:
    """Load ownership for ``repo_root`` (default: git toplevel, else the cwd).

    Never raises on an absent map. Raises :class:`OwnershipConfigError` for any
    present-but-invalid input; callers must not fall back to solo mode.
    """
    ctx, problems = collect_problems(repo_root)
    if problems:
        first = problems[0]
        raise OwnershipConfigError(first.code, first.message, first.subject)
    assert ctx is not None
    return ctx
