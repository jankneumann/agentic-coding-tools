"""Blind stratified human labelling (spec: Blind Stratified Human Labelling; design D9).

Three pieces:

* :func:`stratified_sample` draws a seeded sample across seven strata: any-static-flag
  (yes/no) x kill-rate tercile (three cells each, six in all) plus one ``insufficient`` stratum for
  tests with no usable kill rate. Every non-empty stratum contributes at least one test.
* :func:`render_card` renders one blind card: the test source, the covered functions' signatures
  and docstrings (bodies cut at 40 lines) and any cited spec requirement or scenario. Its
  parameters accept no stage records, so a card cannot show another approach's output.
* :func:`label_next` and :func:`record_label` are the non-interactive ``label next`` and
  ``label record`` commands. Nothing here prompts; an agent harness relays each card.
"""

from __future__ import annotations

import ast
import random
import re
import textwrap
from collections.abc import Iterable, Sequence
from pathlib import Path

from .ledger import LabelEntry, LabelLedger
from .records import StageRecord, TestEntry, content_hash_of_file, find_function, split_node_id
from .thresholds import TERCILES, tercile_cutpoints, tercile_of
from .vocabulary import DESCRIPTIONS, ORACLE_SOURCES, validate_label

# Design D9: covered functions are shown with their bodies cut at this many lines.
MAX_BODY_LINES = 40

INSUFFICIENT = "insufficient"

# Directories never searched when resolving a dotted module name below the repository root.
_SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache"})

_SPEC_PATH_RE = re.compile(r"openspec/[\w./-]*spec\.md")
_SPEC_HEADING_RE = re.compile(r"^(#{1,6})\s+(Requirement|Scenario):\s*(.+?)\s*$")
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s")


# --------------------------------------------------------------------------- sampling


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def stratum_names() -> list[str]:
    """The seven stratum keys in their fixed order."""
    names = [f"{flag}:{band}" for flag in ("flagged", "unflagged") for band in TERCILES]
    return [*names, INSUFFICIENT]


def _assign_strata(
    entries: Sequence[TestEntry],
    static_records: Iterable[StageRecord],
    mutation_records: Iterable[StageRecord],
) -> dict[str, list[TestEntry]]:
    flagged = {
        r.test_id.node_id: bool(r.payload.get("rules"))
        for r in static_records
        if r.stage == "static" and r.status == "ok"
    }
    rates = {
        r.test_id.node_id: r.payload.get("kill_rate")
        for r in mutation_records
        if r.stage == "mutation" and r.status == "ok"
    }
    numeric = [float(v) for v in rates.values() if _is_number(v)]
    cuts = tercile_cutpoints(numeric) if numeric else None

    strata: dict[str, list[TestEntry]] = {name: [] for name in stratum_names()}
    for entry in entries:
        node_id = entry.test_id.node_id
        rate = rates.get(node_id)
        if cuts is None or not _is_number(rate):
            key = INSUFFICIENT  # no usable kill rate: the seventh stratum, not split by flag
        else:
            key = f"{'flagged' if flagged.get(node_id) else 'unflagged'}:{tercile_of(float(rate), cuts)}"
        strata[key].append(entry)
    for members in strata.values():
        members.sort(key=lambda e: e.test_id.node_id)  # input order must not matter
    return {name: members for name, members in strata.items() if members}


def _allocate(sizes: dict[str, int], n: int, seed: int) -> dict[str, int]:
    """Per-stratum draw counts: one each, then the rest roughly proportional to stratum size."""
    keys = list(sizes)
    target = min(n, sum(sizes.values()))
    if target < len(keys):  # fewer slots than strata: a seeded choice of which strata to represent
        chosen = random.Random(f"{seed}:strata").sample(keys, target)
        return {k: (1 if k in chosen else 0) for k in keys}
    alloc = dict.fromkeys(keys, 1)
    for _ in range(target - len(keys)):
        open_keys = [k for k in keys if alloc[k] < sizes[k]]
        if not open_keys:
            break
        # Largest quotient first (D'Hondt); ties go to the earlier stratum.
        best = max(open_keys, key=lambda k: (sizes[k] / (alloc[k] + 1), -keys.index(k)))
        alloc[best] += 1
    return alloc


def _draw(
    entries: Sequence[TestEntry],
    static_records: Iterable[StageRecord],
    mutation_records: Iterable[StageRecord],
    n: int,
    seed: int,
) -> dict[str, list[TestEntry]]:
    strata = _assign_strata(entries, static_records, mutation_records)
    alloc = _allocate({k: len(v) for k, v in strata.items()}, n, seed)
    drawn: dict[str, list[TestEntry]] = {}
    for key, members in strata.items():
        if alloc[key]:
            drawn[key] = random.Random(f"{seed}:{key}").sample(members, alloc[key])
    return drawn


def stratified_sample(
    entries: Sequence[TestEntry],
    static_records: Iterable[StageRecord],
    mutation_records: Iterable[StageRecord],
    *,
    n: int = 40,
    seed: int = 0,
) -> list[TestEntry]:
    """A seeded sample of ``n`` distinct entries (fewer if fewer exist), grouped by stratum."""
    drawn = _draw(entries, static_records, mutation_records, n, seed)
    return [e for members in drawn.values() for e in members]


# --------------------------------------------------------------------------- cards


def _read_tree(root: Path, rel: str) -> tuple[str, ast.Module] | None:
    path = root / rel
    try:
        source = path.read_text("utf-8")
        return source, ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _segment(source_lines: list[str], node: ast.AST) -> str:
    """Source text of a function node, decorators included."""
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    return "\n".join(source_lines[start - 1 : node.end_lineno])


def _test_source(entry: TestEntry, repo_root: Path) -> str:
    loaded = _read_tree(repo_root, entry.path)
    if loaded is None:
        return "(test source unavailable)"
    source, tree = loaded
    lines = source.splitlines()
    node = find_function(tree, entry.function_name, entry.class_name)
    if node is not None:
        return textwrap.dedent(_segment(lines, node))
    return textwrap.dedent("\n".join(lines[entry.line_start - 1 : entry.line_end]))


def _find_module(repo_root: Path, dotted: str, test_path: str) -> Path | None:
    """Resolve a dotted module name to a file.

    Tried in turn: directly below the repository root, below the project directory holding the
    test (first path segment, with and without ``src``), then a bounded search of that project.
    """
    parts = dotted.split(".")
    project = test_path.split("/")[0] if "/" in test_path else ""
    bases = [repo_root]
    if project:
        bases += [repo_root / project, repo_root / project / "src"]
    for base in bases:
        target = base.joinpath(*parts)
        for candidate in (target.with_suffix(".py"), target / "__init__.py"):
            if candidate.is_file():
                return candidate
    search = repo_root / project if project else repo_root
    tail = "/".join(parts)
    for candidate in sorted(search.rglob(f"{parts[-1]}.py")):
        rel = candidate.relative_to(repo_root).parts
        if _SKIP_DIRS.intersection(rel):
            continue
        if candidate.with_suffix("").as_posix().endswith(tail):
            return candidate
    return None


def _cut(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= MAX_BODY_LINES:
        return text
    return "\n".join([*lines[:MAX_BODY_LINES], "    # ... (cut)"])


def _module_functions(source: str, tree: ast.Module) -> list[tuple[str, str]]:
    """(qualified name, source text cut at 40 lines) for top-level functions and methods."""
    lines = source.splitlines()
    out: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out.append((node.name, _cut(_segment(lines, node))))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    out.append((f"{node.name}.{item.name}", _cut(textwrap.dedent(_segment(lines, item)))))
    return out


def _covered_section(entry: TestEntry, repo_root: Path) -> str:
    blocks: list[str] = []
    for dotted in entry.covered_modules:
        file = _find_module(repo_root, dotted, entry.path)
        loaded = None
        if file is not None:
            loaded = _read_tree(file.parent, file.name)
        if loaded is None:
            blocks.append(f"### {dotted}\n\n(source unavailable)")
            continue
        funcs = _module_functions(*loaded)
        body = "\n\n".join(f"# {name}\n{text}" for name, text in funcs) or "(no functions)"
        blocks.append(f"### {dotted}\n\n```python\n{body}\n```")
    return "\n\n".join(blocks)


def _spec_sections(text: str) -> list[tuple[str, str, str]]:
    """(kind, title, body) for each ``Requirement:`` / ``Scenario:`` heading, body to the next peer."""
    lines = text.splitlines()
    out: list[tuple[str, str, str]] = []
    for i, line in enumerate(lines):
        m = _SPEC_HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        end = len(lines)
        for j in range(i + 1, len(lines)):
            h = _ANY_HEADING_RE.match(lines[j])
            if h and len(h.group(1)) <= level:
                end = j
                break
        out.append((m.group(2), m.group(3), "\n".join(lines[i:end]).rstrip()))
    return out


def _cited_spec_text(test_source: str, repo_root: Path) -> str:
    root = repo_root.resolve()
    parts: list[str] = []
    seen: list[str] = []
    for rel in dict.fromkeys(_SPEC_PATH_RE.findall(test_source)):
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file():
            continue
        for kind, title, body in _spec_sections(path.read_text("utf-8")):
            if f"{kind}: {title}" not in test_source or any(body in prior for prior in seen):
                continue
            seen.append(body)
            parts.append(f"From `{rel}`:\n\n{body}")
    return "\n\n".join(parts)


def render_card(entry: TestEntry, *, repo_root: Path) -> str:
    """One blind card (design D9): the test, the covered signatures and docstrings, any cited spec."""
    repo_root = Path(repo_root)
    test_src = _test_source(entry, repo_root)
    vocabulary = "\n".join(f"- `{label}`: {DESCRIPTIONS[label]}" for label in ORACLE_SOURCES)
    sections = [
        f"# Labelling card: `{entry.test_id.node_id}`",
        "Where do this test's expected values come from? Choose exactly one label:\n\n" + vocabulary,
        f"## Test\n\n```python\n{test_src}\n```",
    ]
    covered = _covered_section(entry, repo_root)
    if covered:
        sections.append(f"## Covered functions\n\n{covered}")
    spec = _cited_spec_text(test_src, repo_root)
    if spec:
        sections.append(f"## Cited spec\n\n{spec}")
    return "\n\n".join(sections) + "\n"


# --------------------------------------------------------------------------- label next / record


def _slug(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", node_id).strip("-")[:80] or "test"


def label_next(
    entries: Sequence[TestEntry],
    static_records: Iterable[StageRecord],
    mutation_records: Iterable[StageRecord],
    *,
    repo_root: Path,
    out_dir: Path,
    ledger_path: Path,
    n: int = 40,
    seed: int = 0,
    dry_run: bool = False,
) -> str | None:
    """The ``label next`` command: write every card, return the first unlabelled card (or ``None``).

    The sample is reloaded from the ledger when one is stored; otherwise it is drawn and, unless
    ``dry_run``, persisted in the ledger. A dry run never creates or modifies the ledger.
    """
    ledger = LabelLedger.load(Path(ledger_path))
    by_id = {e.test_id.node_id: e for e in entries}
    if ledger.sample is not None:
        ordered = [by_id[nid] for ids in ledger.sample["strata"].values() for nid in ids if nid in by_id]
    else:
        drawn = _draw(entries, static_records, mutation_records, n, seed)
        ordered = [e for members in drawn.values() for e in members]
        if not dry_run:
            ledger.sample = {
                "seed": seed,
                "n": n,
                "strata": {k: [e.test_id.node_id for e in v] for k, v in drawn.items()},
            }
            ledger.save(Path(ledger_path))

    cards_dir = Path(out_dir) / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    labelled = ledger.labelled_node_ids()
    first: str | None = None
    for index, entry in enumerate(ordered):
        card = render_card(entry, repo_root=repo_root)
        (cards_dir / f"{index:03d}-{_slug(entry.test_id.node_id)}.md").write_text(card, encoding="utf-8")
        if first is None and entry.test_id.node_id not in labelled:
            first = card
    return first


def record_label(
    node_id: str,
    label: str,
    *,
    repo_root: Path,
    ledger_path: Path,
    labeller: str,
    note: str | None = None,
) -> LabelEntry:
    """The ``label record`` command: hash the current test source and append one ledger entry.

    An unknown label raises ``ValueError`` before anything is read or written.
    """
    validate_label(label)
    path, class_name, function_name = split_node_id(node_id)
    current_hash = content_hash_of_file(Path(repo_root) / path, function_name, class_name)
    ledger = LabelLedger.load(Path(ledger_path))
    entry = ledger.add(node_id, current_hash, label, labeller, note=note)
    ledger.save(Path(ledger_path))
    return entry


__all__ = [
    "MAX_BODY_LINES",
    "label_next",
    "record_label",
    "render_card",
    "stratified_sample",
    "stratum_names",
]
