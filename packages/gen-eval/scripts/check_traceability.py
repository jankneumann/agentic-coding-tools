#!/usr/bin/env python3
"""Bidirectional requirement <-> contract traceability gate (design D3-D13).

Four checks, deliberately not a fifth (D5): a cited requirement resolves; a
contracted operation cites something (or is excluded); a requirement subject
to reverse enforcement is cited by something (or is excused); every exclusion
carries a reason. **Never** whether the cited operation actually satisfies
the requirement — nothing static can decide that, and this gate's output is
worded so it cannot be misread as trying to.

One script, one ``--scope`` argument (D12), not two:

- ``--scope change --change <id>``: only the operations and requirements
  ``<id>`` touches. Pre-existing gaps are reported, never failed — this is
  the ``/validate-feature`` invocation.
- ``--scope capability``: every capability, in full. ``--change <id>``
  shadows the archive with that one delta (used by every BLOCKING CI
  invocation); omitting it unions every on-branch delta under
  ``openspec/changes/`` excluding ``archive/`` (used by exactly one run, the
  non-blocking post-merge sweep). The gate does not know or infer which CI
  job called it or whether its result blocks anything (D12) — it always
  reports the same way; CI wiring (task 5.7) decides what to do with the
  exit code.

Mirrors ``check_coverage_completeness.py``'s shape: repo-relative default
roots, ``yaml.safe_load`` exclusively, every failure reported in one run
rather than the first.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PACKAGE_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from gen_eval.descriptor import _cli_unit  # noqa: E402
from gen_eval.service_descriptor import _traceability_block  # noqa: E402
from gen_eval.traceability import (  # noqa: E402
    RequirementResolver,
    TraceabilityBlock,
    UnresolvedRequirementError,
    parse_delta,
    requirement_id,
    slugify,
)

_REPO_ROOT = _PACKAGE_ROOT.parent.parent

DEFAULT_CONTRACTS_ROOT = _REPO_ROOT / "openspec" / "contracts"
DEFAULT_SPECS_ROOT = _REPO_ROOT / "openspec" / "specs"
DEFAULT_CHANGES_ROOT = _REPO_ROOT / "openspec" / "changes"
DEFAULT_REPO_ROOT = _REPO_ROOT
DEFAULT_BASE_REF = "main"

#: D7 — a display trigger, never an exit-code input. Changing this constant
#: can never change what the gate reports as pass/fail, only what it
#: additionally flags as "concentrated" in its (always-informational)
#: concentration section.
CONCENTRATION_REPORT_SHARE = 0.5

#: D5's pinned canonical line. The wording test asserts the SPEC's phrase,
#: not a literal this module invents.
_NO_SATISFACTION_CLAIM = "This gate does not check that any requirement is satisfied."

_YAML_SUFFIXES = (".yaml", ".yml", ".json")
_ROOT_NON_INSTANCE_NAMES = frozenset({"README.md", "traceability-exclusions.yaml"})
_MISSING = object()  # sentinel: "this unit did not exist before"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Unit:
    """One traceable coverage unit: an operation, flag, positional, or named command."""

    unit_id: str
    block: TraceabilityBlock | None
    resolved: list[str] = field(default_factory=list)  # populated after resolution


@dataclass
class Document:
    path: Path
    rel_path: str
    capability: str
    kind: str  # "openapi" | "cli"
    location: str  # "openapi" | "cli" | "root"
    units: list[Unit]

    @property
    def opted_in(self) -> bool:
        return any(u.block is not None for u in self.units)


@dataclass
class MalformedFile:
    rel_path: str
    reason: str


@dataclass
class GateResult:
    errors: list[str] = field(default_factory=list)
    forward_failures: list[str] = field(default_factory=list)
    reverse_failures: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)
    cross_capability: list[str] = field(default_factory=list)
    concentration: list[str] = field(default_factory=list)
    operations_cited: int = 0
    requirements_cited: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if (self.errors or self.forward_failures or self.reverse_failures) else 0


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_yaml_or_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _instance_kind(raw: Any) -> str | None:
    """'openapi' or 'cli' if ``raw`` structurally is a contract instance (D6)."""
    if not isinstance(raw, dict):
        return None
    if "openapi" in raw:
        return "openapi"
    if "tool" in raw:
        return "cli"
    return None


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _units_from_openapi(raw: dict[str, Any], source: Path) -> list[Unit]:
    """Extract (operation_id, traceability) pairs without building a full
    ``ServiceDescriptor`` — this gate cannot write under ``openspec/contracts/**``
    (denied to wp-gate), and every fixture is under ``tmp_path``, so parsing
    the raw document in place (rather than round-tripping through a temp
    file) keeps every test self-contained.
    """
    from gen_eval.openapi import iter_operations

    units: list[Unit] = []
    for found in iter_operations(raw):
        operation_id = found.raw.get("operationId")
        if not operation_id:
            raise ValueError(
                f"{source}: an operation with no operationId cannot be a citation target"
            )
        block = _traceability_block(found.raw)
        units.append(Unit(unit_id=operation_id, block=block))
    return units


def _units_from_cli(raw: dict[str, Any]) -> list[Unit]:
    units: list[Unit] = []
    for command_dict in raw.get("commands") or []:
        command_dict = dict(command_dict)
        flags = command_dict.pop("flags", None)
        positionals = command_dict.pop("positionals", None)
        traceability = command_dict.pop("traceability", None)
        name = command_dict.get("name", "")
        if name:
            units.append(
                Unit(unit_id=_cli_unit(name), block=_parse_block(traceability))
            )
        for flag in flags or []:
            flag = dict(flag)
            fblock = flag.pop("traceability", None)
            units.append(
                Unit(unit_id=_cli_unit(name, flag["name"]), block=_parse_block(fblock))
            )
        for positional in positionals or []:
            positional = dict(positional)
            pblock = positional.pop("traceability", None)
            units.append(
                Unit(
                    unit_id=_cli_unit(name, f"<{positional['name']}>"),
                    block=_parse_block(pblock),
                )
            )
    return units


def _parse_block(declared: Any) -> TraceabilityBlock | None:
    if declared is None:
        return None
    return TraceabilityBlock(**declared)


def _load_document(
    path: Path, capability: str, location: str, repo_root: Path
) -> Document | MalformedFile:
    try:
        raw = _load_yaml_or_json(path)
    except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
        return MalformedFile(_rel(path, repo_root), str(exc))
    kind = _instance_kind(raw)
    if kind is None:
        # Not structurally an instance (e.g. a helper YAML dropped in the
        # directory by mistake) — not this gate's concern.
        return MalformedFile("", "")  # sentinel handled by caller (ignored)
    try:
        if kind == "openapi":
            units = _units_from_openapi(raw, path)
        else:
            units = _units_from_cli(raw)
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        return MalformedFile(_rel(path, repo_root), str(exc))
    return Document(
        path=path,
        rel_path=_rel(path, repo_root),
        capability=capability,
        kind=kind,
        location=location,
        units=units,
    )


def discover_capability(
    contracts_root: Path, capability: str, repo_root: Path
) -> tuple[list[Document], list[Document], list[MalformedFile]]:
    """Returns ``(documents, misplaced, malformed)`` for one capability.

    ``documents`` holds instances under ``openapi/`` or ``cli/``;
    ``misplaced`` holds structural instances found at the capability root
    (D6's ratchet — reported, not skipped); ``malformed`` holds every file
    that failed to parse or failed to construct valid units, wherever found.
    """
    cap_dir = contracts_root / capability
    documents: list[Document] = []
    misplaced: list[Document] = []
    malformed: list[MalformedFile] = []

    for location in ("openapi", "cli"):
        subdir = cap_dir / location
        if not subdir.is_dir():
            continue
        for candidate in sorted(subdir.rglob("*")):
            if not candidate.is_file() or candidate.suffix not in _YAML_SUFFIXES:
                continue
            result = _load_document(candidate, capability, location, repo_root)
            if isinstance(result, Document):
                documents.append(result)
            elif result.rel_path:  # real malformed file, not the "not an instance" sentinel
                malformed.append(result)

    if cap_dir.is_dir():
        for candidate in sorted(cap_dir.glob("*")):
            if not candidate.is_file() or candidate.name in _ROOT_NON_INSTANCE_NAMES:
                continue
            if candidate.suffix not in _YAML_SUFFIXES:
                continue
            result = _load_document(candidate, capability, "root", repo_root)
            if isinstance(result, Document):
                misplaced.append(result)
            elif result.rel_path:
                malformed.append(result)

    return documents, misplaced, malformed


# ---------------------------------------------------------------------------
# Exclusions file (D4, D13)
# ---------------------------------------------------------------------------


@dataclass
class ExclusionsFile:
    capability: str
    rel_path: str
    entries: list[tuple[str, str]]  # (requirement_id, reason)


def load_exclusions_file(
    contracts_root: Path, capability: str, repo_root: Path
) -> ExclusionsFile | None | str:
    """Returns the parsed file, ``None`` if absent (reverse not opted in), or
    an error string if it exists but is unreadable/unparseable/invalid (D13:
    an accident must never read as an absent switch).
    """
    path = contracts_root / capability / "traceability-exclusions.yaml"
    if not path.is_file():
        return None
    rel = _rel(path, repo_root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"{rel}: cannot be read ({exc})"
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return f"{rel}: not valid YAML ({exc})"
    if document is None:
        return (
            f"{rel}: is empty — an exclusions file must declare `exclusions` "
            f"(even as an empty list)"
        )
    if not isinstance(document, dict) or "exclusions" not in document:
        return f"{rel}: does not declare `exclusions`"
    entries_raw = document["exclusions"]
    if not isinstance(entries_raw, list):
        return f"{rel}: `exclusions` must be a list"
    entries: list[tuple[str, str]] = []
    for entry in entries_raw:
        if not isinstance(entry, dict) or "requirement" not in entry or "reason" not in entry:
            return f"{rel}: every exclusion needs `requirement` and `reason`, got {entry!r}"
        entries.append((str(entry["requirement"]), str(entry["reason"])))
    return ExclusionsFile(capability=capability, rel_path=rel, entries=entries)


# ---------------------------------------------------------------------------
# Git plumbing (change scope only)
# ---------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False
    )


def resolve_merge_base(repo_root: Path, base_ref: str, revision: str = "HEAD") -> str | None:
    """The merge base against ``base_ref``, or ``None`` when unresolvable.

    Mirrors the shape of ``project-context-refresh/scripts/checkpoint.py``'s
    ``resolve_merge_base`` (task 3.16's note) rather than growing a third
    implementation of the same idea — reimplemented here (not imported)
    because that module lives under ``skills/`` and this package is
    installed standalone by consumers with no ``skills/`` tree.
    """
    result = _git(repo_root, "merge-base", base_ref, revision)
    sha = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return None
    return sha


def _changed_paths(repo_root: Path, merge_base: str, *, under: str) -> list[str]:
    result = _git(
        repo_root,
        "diff",
        "--no-renames",
        "--name-only",
        merge_base,
        "HEAD",
        "--",
        under,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_show(repo_root: Path, revision: str, rel_path: str) -> str | None:
    result = _git(repo_root, "show", f"{revision}:{rel_path}")
    return result.stdout if result.returncode == 0 else None


# ---------------------------------------------------------------------------
# Change-scope: the touched set (D12)
# ---------------------------------------------------------------------------


@dataclass
class TouchedSet:
    units: set[tuple[str, str]] = field(default_factory=set)  # (rel_path, unit_id)
    requirements: set[str] = field(default_factory=set)
    newly_misplaced: set[str] = field(default_factory=set)  # rel_path


def compute_touched_set(
    *,
    repo_root: Path,
    contracts_root: Path,
    changes_root: Path,
    resolver: RequirementResolver,
    change_id: str,
    merge_base: str,
    documents_by_rel: dict[str, Document],
    misplaced_by_rel: dict[str, Document],
) -> TouchedSet:
    touched = TouchedSet()
    contracts_rel = _rel(contracts_root, repo_root)

    changed_contract_paths = set(_changed_paths(repo_root, merge_base, under=contracts_rel))

    for rel_path in changed_contract_paths:
        if rel_path in misplaced_by_rel:
            touched.newly_misplaced.add(rel_path)
            continue
        doc = documents_by_rel.get(rel_path)
        if doc is None:
            continue  # deleted, or not a recognised instance — nothing to touch
        old_text = _git_show(repo_root, merge_base, rel_path)
        old_units: dict[str, Any] = {}
        old_opted_in = False
        if old_text is not None:
            try:
                old_raw = (
                    json.loads(old_text)
                    if rel_path.endswith(".json")
                    else yaml.safe_load(old_text)
                )
                kind = _instance_kind(old_raw)
                if kind == "openapi":
                    old_list = _units_from_openapi(old_raw, doc.path)
                elif kind == "cli":
                    old_list = _units_from_cli(old_raw)
                else:
                    old_list = []
                old_units = {u.unit_id: _block_repr(u.block) for u in old_list}
                old_opted_in = any(u.block is not None for u in old_list)
            except Exception:  # noqa: BLE001 — best-effort prior-state read
                old_units = {}
                old_opted_in = False

        if (not old_opted_in) and doc.opted_in:
            # Widening rule: opting the whole document in touches every unit.
            for unit in doc.units:
                touched.units.add((rel_path, unit.unit_id))
        else:
            for unit in doc.units:
                if old_units.get(unit.unit_id, _MISSING) != _block_repr(unit.block):
                    touched.units.add((rel_path, unit.unit_id))

    # Requirement-level touch: this change's own delta (ADDED/MODIFIED/RENAMED-new).
    change_specs_dir = changes_root / change_id / "specs"
    if change_specs_dir.is_dir():
        for spec_file in sorted(change_specs_dir.rglob("spec.md")):
            capability = spec_file.parent.name
            delta = parse_delta(spec_file.read_text(encoding="utf-8"))
            for heading, _ in delta.added:
                touched.requirements.add(requirement_id(capability, heading))
            for heading, _ in delta.modified:
                touched.requirements.add(requirement_id(capability, heading))
            for _old, new in delta.renamed:
                touched.requirements.add(requirement_id(capability, new))

    # Reverse opt-in widening: a newly-created exclusions file touches every
    # requirement of its capability.
    exclusions_changed = _changed_paths(repo_root, merge_base, under=contracts_rel)
    for rel_path in exclusions_changed:
        if not rel_path.endswith("traceability-exclusions.yaml"):
            continue
        old_text = _git_show(repo_root, merge_base, rel_path)
        if old_text is not None:
            continue  # already existed before this change — not a new opt-in
        capability = Path(rel_path).parent.name
        try:
            effective = resolver.effective_headings(capability, change_id=change_id)
        except Exception:  # noqa: BLE001 — malformed delta reported elsewhere
            continue
        for slug in effective:
            touched.requirements.add(f"{capability}.{slug}")

    # New citations reaching an untouched requirement widen touched-ness too
    # (best-effort: only for units already identified as touched above).
    for rel_path, unit_id in list(touched.units):
        doc = documents_by_rel.get(rel_path)
        if doc is None:
            continue
        unit = next((u for u in doc.units if u.unit_id == unit_id), None)
        if unit is not None and unit.block is not None and unit.block.requirements:
            for req_id in unit.block.requirements:
                touched.requirements.add(req_id)

    return touched


def _block_repr(block: TraceabilityBlock | None) -> Any:
    if block is None:
        return None
    return block.model_dump(exclude_defaults=True)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Union resolution mode (D12) — omitting --change at capability scope
# ---------------------------------------------------------------------------
#
# ``RequirementResolver`` (gen_eval/traceability.py, wp-resolver/wp-model's
# module) shadows the archive with exactly one change's delta, or none at
# all. Union mode — the archive shadowed by *every* non-archive change delta
# at once — is a wp-gate-only concept: it is not implemented on the shared
# resolver because traceability.py is outside this package's write_allow.
# Deliberately lenient (unlike the resolver's archiver-mirroring strictness):
# a MODIFIED/REMOVED/RENAMED operation naming something outside the current
# union set is skipped rather than raised, because this mode combines every
# in-flight change's delta at once and one change's malformed or
# order-sensitive delta must not take down the debt-visibility sweep for
# every other change (D12: "union mode is deliberately the looser of the
# two").


def _union_effective_headings(
    resolver: RequirementResolver, changes_root: Path, capability: str
) -> dict[str, str]:
    names = list(resolver.archived_headings(capability))
    name_set = set(names)
    if changes_root.is_dir():
        for change_dir in sorted(changes_root.iterdir(), key=lambda p: p.name):
            if not change_dir.is_dir() or change_dir.name == "archive":
                continue
            spec_file = change_dir / "specs" / capability / "spec.md"
            if not spec_file.is_file():
                continue
            try:
                delta = parse_delta(spec_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — one change's malformed delta is not fatal here
                continue
            for old, new in delta.renamed:
                if old in name_set and new not in name_set:
                    names = [new if n == old else n for n in names]
                    name_set.discard(old)
                    name_set.add(new)
            for name in delta.removed:
                if name in name_set:
                    names = [n for n in names if n != name]
                    name_set.discard(name)
            for name, _body in delta.added:
                if name not in name_set:
                    names.append(name)
                    name_set.add(name)
            # MODIFIED changes only the body, never the name set.
    by_slug: dict[str, str] = {}
    for heading in names:
        by_slug[slugify(heading)] = heading  # last writer wins on a real collision
    return by_slug


def _nearest_headings(slug: str, headings: list[str], limit: int = 5) -> list[str]:
    by_slug = {slugify(h): h for h in headings}
    matches = difflib.get_close_matches(slug, list(by_slug), n=limit, cutoff=0.0)
    return [by_slug[m] for m in matches]


def _effective_headings_in_scope(
    resolver: RequirementResolver,
    changes_root: Path,
    capability: str,
    change_id: str | None,
) -> dict[str, str]:
    """``slug -> heading`` under this run's resolution mode.

    ``change_id`` given: the archive shadowed by that one change's delta
    (the resolver's own shape). ``change_id`` omitted: the union of every
    on-branch delta, excluding ``archive/`` (D12's non-blocking mode).
    """
    if change_id is not None:
        return resolver.effective_headings(capability, change_id=change_id)
    return _union_effective_headings(resolver, changes_root, capability)


def _resolve_id_in_scope(
    req_id: str,
    *,
    resolver: RequirementResolver,
    changes_root: Path,
    change_id: str | None,
) -> str:
    """Resolve ``req_id`` under this run's resolution mode, fail closed (D2)."""
    capability, sep, slug = req_id.partition(".")
    if not sep or not capability or not slug:
        raise UnresolvedRequirementError(req_id, [])
    by_slug = _effective_headings_in_scope(resolver, changes_root, capability, change_id)
    heading = by_slug.get(slug)
    if heading is not None:
        return heading
    raise UnresolvedRequirementError(req_id, _nearest_headings(slug, list(by_slug.values())))


def run_gate(
    *,
    contracts_root: Path,
    specs_root: Path,
    changes_root: Path,
    repo_root: Path,
    scope: str,
    change_id: str | None,
    base_ref: str = DEFAULT_BASE_REF,
) -> tuple[GateResult, TouchedSet | None]:
    result = GateResult()
    resolver = RequirementResolver(specs_root, changes_root)

    if scope not in ("change", "capability"):
        result.errors.append(f"--scope must be 'change' or 'capability', got {scope!r}")
        return result, None
    if scope == "change" and not change_id:
        result.errors.append(
            "--scope change requires --change <id> — an unresolved scope is an "
            "error, never an empty one"
        )
        return result, None

    capabilities = (
        sorted(p.name for p in contracts_root.iterdir() if p.is_dir())
        if contracts_root.is_dir()
        else []
    )

    all_documents: list[Document] = []
    all_misplaced: list[Document] = []
    all_malformed: list[MalformedFile] = []
    per_capability_docs: dict[str, list[Document]] = {}
    per_capability_misplaced: dict[str, list[Document]] = {}

    for capability in capabilities:
        docs, misplaced, malformed = discover_capability(contracts_root, capability, repo_root)
        per_capability_docs[capability] = docs
        per_capability_misplaced[capability] = misplaced
        all_documents.extend(docs)
        all_misplaced.extend(misplaced)
        all_malformed.extend(malformed)

    for m in all_malformed:
        result.errors.append(
            f"{m.rel_path}: cannot be parsed ({m.reason}) — not recorded as untraced"
        )

    # -- change scope: compute the touched set -----------------------------
    touched: TouchedSet | None = None
    if scope == "change":
        merge_base = resolve_merge_base(repo_root, base_ref)
        if merge_base is None:
            result.errors.append(
                f"cannot resolve the merge base against '{base_ref}' — an "
                f"unresolvable base is an error, never an empty scope"
            )
            return result, None
        documents_by_rel = {d.rel_path: d for d in all_documents}
        misplaced_by_rel = {d.rel_path: d for d in all_misplaced}
        touched = compute_touched_set(
            repo_root=repo_root,
            contracts_root=contracts_root,
            changes_root=changes_root,
            resolver=resolver,
            change_id=change_id,  # type: ignore[arg-type]
            merge_base=merge_base,
            documents_by_rel=documents_by_rel,
            misplaced_by_rel=misplaced_by_rel,
        )

    resolve_change_id = change_id  # single-change shadow mode (scope-independent)

    # -- resolve every unit's citations -------------------------------------
    # (capability -> requirement_id -> [(citing_capability, unit descriptor)])
    citations_by_requirement: dict[str, list[tuple[str, str, str]]] = {}
    cross_capability_entries: list[str] = []

    for doc in all_documents + all_misplaced:
        # Capabilities with contract documents but no spec — resolved before
        # attempting citation resolution so the message is distinguishable
        # from a generic unresolved-id failure (D6/3.6).
        if doc.opted_in and not (specs_root / doc.capability / "spec.md").is_file():
            result.errors.append(
                f"{doc.rel_path}: capability {doc.capability!r} declares traceability "
                f"but has no spec at openspec/specs/{doc.capability}/spec.md"
            )
            continue
        for unit in doc.units:
            if unit.block is None:
                continue
            if unit.block.excluded is not None:
                continue
            for req_id in unit.block.requirements or []:
                try:
                    _resolve_id_in_scope(
                        req_id,
                        resolver=resolver,
                        changes_root=changes_root,
                        change_id=resolve_change_id,
                    )
                except UnresolvedRequirementError as exc:
                    result.errors.append(
                        f"{doc.rel_path} ({unit.unit_id}): {exc}"
                    )
                    continue
                unit.resolved.append(req_id)
                cited_capability = req_id.partition(".")[0]
                citations_by_requirement.setdefault(req_id, []).append(
                    (doc.capability, doc.rel_path, unit.unit_id)
                )
                if cited_capability != doc.capability:
                    cross_capability_entries.append(
                        f"{doc.rel_path} ({unit.unit_id}) -> {req_id}"
                    )

    result.cross_capability = sorted(set(cross_capability_entries))

    # -- forward completeness (D6), per document -----------------------------
    total_operations_cited = 0
    for doc in all_documents + all_misplaced:
        if not doc.opted_in:
            result.reports.append(f"{doc.rel_path}: untraced (no traceability block declared)")
            continue
        for unit in doc.units:
            key = (doc.rel_path, unit.unit_id)
            is_touched = touched is None or key in touched.units or doc.rel_path in (
                touched.newly_misplaced if touched else set()
            )
            if unit.block is None:
                message = (
                    f"{doc.rel_path}: {unit.unit_id} cites no requirement and carries no exclusion"
                )
                if scope == "capability" or is_touched:
                    result.forward_failures.append(message)
                else:
                    result.reports.append(f"{message} (pre-existing, not touched by this change)")
            elif unit.block.excluded is not None:
                result.reports.append(
                    f"{doc.rel_path}: {unit.unit_id} excluded — {unit.block.excluded.reason}"
                )
            else:
                total_operations_cited += 1

    result.operations_cited = total_operations_cited

    # -- newly misplaced instances fail change scope; sweep only reports -----
    for doc in all_misplaced:
        expected = "openapi/" if doc.kind == "openapi" else "cli/"
        message = (
            f"{doc.rel_path}: misplaced contract instance, expected under "
            f"{doc.capability}/{expected}"
        )
        if touched is not None and doc.rel_path in touched.newly_misplaced:
            result.forward_failures.append(message)
        else:
            result.reports.append(message)

    # -- exclusions files + reverse completeness, per capability --------------
    total_requirements_cited = 0
    for capability in capabilities:
        exclusions = load_exclusions_file(contracts_root, capability, repo_root)
        docs_and_misplaced = per_capability_docs.get(capability, []) + per_capability_misplaced.get(
            capability, []
        )
        has_documents = bool(docs_and_misplaced)
        has_spec = (specs_root / capability / "spec.md").is_file()

        if isinstance(exclusions, str):
            result.errors.append(exclusions)
            # D13: an unreadable file is never read as "not opted in" — do
            # not additionally report a not-opted-in status for it below.
            continue

        if not has_spec:
            if has_documents and any(d.opted_in for d in docs_and_misplaced):
                pass  # already reported above (missing-spec-with-traceability error)
            elif has_documents:
                result.reports.append(
                    f"{capability}: contract documents present but no spec at "
                    f"openspec/specs/{capability}/spec.md"
                )
            continue

        try:
            effective = _effective_headings_in_scope(
                resolver, changes_root, capability, resolve_change_id
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{capability}: cannot resolve effective requirement set ({exc})")
            continue

        excluded_by_slug: dict[str, str] = {}
        if exclusions is not None:
            for req_id, reason in exclusions.entries:
                owning_capability = req_id.partition(".")[0]
                if owning_capability != capability:
                    result.errors.append(
                        f"{exclusions.rel_path}: excludes {req_id!r}, whose capability is "
                        f"{owning_capability!r} — an exclusions file may only excuse its own "
                        f"capability ({capability!r})'s requirements"
                    )
                    continue
                if not reason.strip():
                    result.errors.append(
                        f"{exclusions.rel_path}: exclusion of {req_id!r} has a blank reason"
                    )
                    continue
                slug = req_id.partition(".")[2]
                if slug not in effective:
                    result.errors.append(
                        f"{exclusions.rel_path}: excludes {req_id!r}, which is not in the "
                        f"effective requirement set (stale exclusion)"
                    )
                    continue
                excluded_by_slug[slug] = reason

        for slug, heading in sorted(effective.items()):
            full_id = f"{capability}.{slug}"
            citers = citations_by_requirement.get(full_id, [])
            if citers:
                total_requirements_cited += 1
                continue
            if slug in excluded_by_slug:
                result.reports.append(
                    f"{capability}: {full_id} ({heading!r}) excluded — {excluded_by_slug[slug]}"
                )
                continue
            message = f"{capability}: {full_id} ({heading!r}) is cited by no operation"
            reverse_enforced = exclusions is not None
            is_touched = touched is None or full_id in touched.requirements
            if reverse_enforced and (scope == "capability" or is_touched):
                result.reverse_failures.append(message)
            elif reverse_enforced:
                result.reports.append(f"{message} (pre-existing, not touched by this change)")
            else:
                result.reports.append(f"{message} (capability not opted into reverse enforcement)")

        if exclusions is None:
            result.reports.append(
                f"{capability}: reverse completeness not opted in "
                f"(no traceability-exclusions.yaml)"
            )

    result.requirements_cited = total_requirements_cited

    # -- concentration (D7) — informational only ------------------------------
    for capability in capabilities:
        docs = per_capability_docs.get(capability, []) + per_capability_misplaced.get(
            capability, []
        )
        traced_units = [u for d in docs for u in d.units if u.resolved]
        denominator = len(traced_units)
        if denominator == 0:
            continue
        counts: dict[str, int] = {}
        for unit in traced_units:
            for req_id in unit.resolved:
                counts[req_id] = counts.get(req_id, 0) + 1
        for req_id, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            share = count / denominator
            marker = " (concentrated)" if share >= CONCENTRATION_REPORT_SHARE else ""
            result.concentration.append(
                f"{capability}: {req_id} cited by {count}/{denominator} traced operations "
                f"({share:.0%}){marker}"
            )

    return result, touched


def _format_report(result: GateResult, *, scope: str, change_id: str | None) -> str:
    lines: list[str] = []
    if scope == "change":
        lines.append(
            f"scope: change ({change_id}) — touched operations and requirements only; "
            f"capability completeness not evaluated"
        )
    else:
        lines.append(
            f"scope: capability (change={change_id!r})"
            if change_id
            else "scope: capability (union of on-branch deltas)"
        )

    for section_name, entries in (
        ("errors", result.errors),
        ("forward failures", result.forward_failures),
        ("reverse failures", result.reverse_failures),
        ("cross-capability citations", result.cross_capability),
        ("concentration", result.concentration),
        ("reports", result.reports),
    ):
        if entries:
            lines.append(f"\n{section_name}:")
            lines.extend(f"  - {e}" for e in entries)

    if result.exit_code == 0:
        lines.append(
            f"\n{result.operations_cited} operations cite {result.requirements_cited} "
            f"requirements. {_NO_SATISFACTION_CLAIM}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contracts-root", type=Path, default=DEFAULT_CONTRACTS_ROOT)
    parser.add_argument("--specs-root", type=Path, default=DEFAULT_SPECS_ROOT)
    parser.add_argument("--changes-root", type=Path, default=DEFAULT_CHANGES_ROOT)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument(
        "--base-ref", default=DEFAULT_BASE_REF, help="Integration branch (default: main)"
    )
    parser.add_argument("--scope", required=True, choices=["change", "capability"])
    parser.add_argument("--change", dest="change_id", default=None)
    args = parser.parse_args(argv)

    outcome = run_gate(
        contracts_root=args.contracts_root,
        specs_root=args.specs_root,
        changes_root=args.changes_root,
        repo_root=args.repo_root,
        scope=args.scope,
        change_id=args.change_id,
        base_ref=args.base_ref,
    )
    result, _touched = outcome
    print(_format_report(result, scope=args.scope, change_id=args.change_id))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
