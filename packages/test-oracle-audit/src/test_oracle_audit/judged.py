"""Judged stage: shadow-mode oracle-source assessment (spec: Judged Oracle Assessment; design D7).

Per test it asks three questions through ``system_one_decisions.decide()`` (site
``test-oracle-audit.judge``), keyed ``t<i>.<q>``:

- ``oracle_source``: a ``choice`` over the D2 vocabulary,
- ``survives_refactor``: a ``noul`` ("would still pass if every private helper were renamed"),
- ``boundary``: a ``choice`` over :data:`BOUNDARIES`; descriptive only, never a decision input.

The stage is *blind* (the state is the test, the fixtures it uses, the covered source bodies, the module
docstring and any cited spec scenario -- never static flags, mutation, rename, history or human labels),
*batched* (one ``decide()`` call per test file when its state fits the 32K-token budget, otherwise one
per test) and *shadow-only* (answers are stored as probabilities with ``evidence_class: judgment``; the
stage never raises, never exits, and nothing downstream gates on it).

``system_one_decisions`` is imported as a module and ``decide`` is looked up at call time, so
``system_one_decisions.testing.stub_decide`` reaches it. The SDK is never imported here.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import system_one_decisions

from test_oracle_audit.records import StageRecord, TestEntry, TestId
from test_oracle_audit.vocabulary import DESCRIPTIONS, ORACLE_SOURCES

STAGE = "judged"
SITE = "test-oracle-audit.judge"

BOUNDARIES: tuple[str, ...] = ("pure_function", "module_api", "service_api", "ui", "mixed")
BOUNDARY_DESCRIPTIONS: dict[str, str] = {
    "pure_function": "The test exercises a pure function: inputs in, value out, no collaborators",
    "module_api": "The test exercises a module's public API within one process",
    "service_api": "The test exercises a service boundary: HTTP, RPC, database or another process",
    "ui": "The test exercises a user interface",
    "mixed": "The test spans several of the boundaries above",
}

# Mirror of decide()'s documented budget (~4 chars/token, 32K tokens). Only used to choose between a
# per-file batch and one call per test; decide() itself enforces the budget and returns None over it.
_CHARS_PER_TOKEN = 4
_TOKEN_BUDGET = 32_000

# Size caps for the covered-source part of the state. Exceeding either truncates (head kept) and sets
# the record's ``truncated`` flag; the test, fixtures and spec text are never cut silently.
MAX_FUNCTION_CHARS = 4_000
MAX_COVERED_CHARS = 12_000
MAX_SPEC_CHARS = 3_000
_TRUNCATION_MARKER = "# ... [truncated]"

_FIXTURE_DEPTH = 3

_SURVIVES_INSTRUCTIONS = (
    "This test would still pass if every private helper in the code under test were renamed."
)
_ORACLE_INSTRUCTIONS = (
    "Where do this test's expected values come from? Answer `none` if no listed source matches."
)
_BOUNDARY_INSTRUCTIONS = "At which boundary does this test exercise the code under test?"

_SPEC_PATH_RE = re.compile(r"specs/([\w.\-]+)")
_REQUIREMENT_RE = re.compile(r"Requirement:\s*([^,;\n]+)")
_SCENARIO_RE = re.compile(r"Scenario:\s*([^,;\n]+)")


# --------------------------------------------------------------------------- state


class _ModuleIndex:
    """Lazy list of the repository's Python files, for resolving dotted module names."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._files: list[str] | None = None

    def files(self) -> list[str]:
        if self._files is None:
            self._files = self._list()
        return self._files

    def _list(self) -> list[str]:
        try:
            out = subprocess.run(
                ["git", "ls-files", "-z", "*.py"],
                cwd=self.repo_root,
                capture_output=True,
                check=True,
                text=True,
            ).stdout
            found = [p for p in out.split("\0") if p]
            if found:
                return sorted(found)
        except (OSError, subprocess.CalledProcessError):
            pass
        found = []
        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"node_modules", "__pycache__"}]
            for name in filenames:
                if name.endswith(".py"):
                    found.append((Path(dirpath) / name).relative_to(self.repo_root).as_posix())
        return sorted(found)

    def resolve(self, module: str) -> Path | None:
        """A repo-relative ``.py`` path as-is, or a dotted name matched by path suffix (shortest wins)."""
        if module.endswith(".py"):
            path = self.repo_root / module
            return path if path.is_file() else None
        rel = module.replace(".", "/")
        wanted = (f"{rel}.py", f"{rel}/__init__.py")
        matches = [f for f in self.files() if any(f == w or f.endswith("/" + w) for w in wanted)]
        if not matches:
            return None
        return self.repo_root / min(matches, key=lambda f: (len(f), f))


def _truncate_head(text: str, limit: int) -> tuple[str, bool]:
    """Keep whole leading lines up to ``limit`` chars; mark the cut."""
    if len(text) <= limit:
        return text, False
    kept: list[str] = []
    used = 0
    for line in text.splitlines():
        if used + len(line) + 1 > limit:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join([*kept, _TRUNCATION_MARKER]), True


def _segment(lines: Sequence[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    for deco in getattr(node, "decorator_list", ()):
        start = min(start, deco.lineno)
    end = getattr(node, "end_lineno", None) or start
    return "\n".join(lines[start - 1 : end])


def _defs(tree: ast.AST) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    return (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))


def _fixture_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The fixture's name if ``node`` is decorated with ``*fixture``; honours ``name=``."""
    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        text = ast.unparse(target)
        if text.split(".")[-1] != "fixture":
            continue
        if isinstance(deco, ast.Call):
            for kw in deco.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    return kw.value.value
        return node.name
    return None


def _find_test(tree: ast.Module, entry: TestEntry) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    scopes: list[Sequence[ast.stmt]] = []
    if entry.class_name:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == entry.class_name), None)
        if cls is not None:
            scopes.append(cls.body)
    scopes.append(tree.body)
    for body in scopes:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == entry.function_name:
                return node
    return next((n for n in _defs(tree) if n.name == entry.function_name), None)


def _parse(path: Path) -> tuple[ast.Module, list[str]] | None:
    try:
        text = path.read_text("utf-8")
        return ast.parse(text), text.splitlines()
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _used_names(*nodes: ast.AST) -> set[str]:
    names: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
    return names


def _fixture_sources(
    entry: TestEntry,
    test_node: ast.AST,
    tree: ast.Module,
    lines: Sequence[str],
    repo_root: Path,
) -> list[dict[str, str]]:
    """Sources of the fixtures the test uses (and, a few levels deep, the fixtures they request)."""
    test_path = repo_root / entry.path
    pools: list[tuple[ast.Module, Sequence[str], str]] = [(tree, lines, entry.path)]
    directory = test_path.parent
    while True:
        conftest = directory / "conftest.py"
        if conftest.is_file() and conftest != test_path:
            parsed = _parse(conftest)
            if parsed is not None:
                pools.append((parsed[0], parsed[1], conftest.relative_to(repo_root).as_posix()))
        if directory == repo_root or repo_root not in directory.parents:
            break
        directory = directory.parent

    wanted = list(entry.fixtures)
    if isinstance(test_node, ast.FunctionDef | ast.AsyncFunctionDef):
        wanted += [a.arg for a in (*test_node.args.args, *test_node.args.kwonlyargs)]
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _depth in range(_FIXTURE_DEPTH):
        next_wanted: list[str] = []
        for name in wanted:
            if name in seen:
                continue
            for pool_tree, pool_lines, origin in pools:
                node = next((d for d in _defs(pool_tree) if _fixture_name(d) == name), None)
                if node is None:
                    continue
                seen.add(name)
                out.append({"name": name, "origin": origin, "source": _segment(pool_lines, node)})
                next_wanted += [a.arg for a in (*node.args.args, *node.args.kwonlyargs)]
                break
        wanted = next_wanted
        if not wanted:
            break
    return out


def _covered_sources(
    modules: Iterable[str], used: set[str], index: _ModuleIndex
) -> tuple[list[dict[str, str]], bool]:
    """Bodies of the covered functions/classes the test refers to, truncated; flag if anything was cut."""
    out: list[dict[str, str]] = []
    truncated = False
    budget = MAX_COVERED_CHARS
    for module in modules:
        path = index.resolve(module)
        parsed = _parse(path) if path is not None else None
        if path is None or parsed is None:
            continue
        tree, lines = parsed
        rel = path.relative_to(index.repo_root).as_posix()
        units = [n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)]
        chosen = [n for n in units if n.name in used] or units
        for node in chosen:
            if budget <= 0:
                truncated = True
                break
            body, cut = _truncate_head(_segment(lines, node), min(MAX_FUNCTION_CHARS, budget))
            truncated = truncated or cut
            budget -= len(body)
            out.append({"module": module, "path": rel, "name": node.name, "source": body})
    return out, truncated


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" \t*`\"'.")).casefold()


def _spec_files(repo_root: Path, capability: str) -> list[Path]:
    candidates = [repo_root / "openspec" / "specs" / capability / "spec.md"]
    changes = repo_root / "openspec" / "changes"
    if changes.is_dir():
        candidates += sorted(
            p / "specs" / capability / "spec.md" for p in changes.iterdir() if p.is_dir() and p.name != "archive"
        )
    return [p for p in candidates if p.is_file()]


def _spec_blocks(text: str, marker: str, level: int) -> list[tuple[str, str]]:
    """``(heading, block)`` for every ``<level hashes> <marker> <heading>`` block, up to the next heading."""
    hashes = "#" * level
    heading_re = re.compile(rf"^{hashes}\s+{marker}:\s*(.+?)\s*$", re.MULTILINE)
    stop_re = re.compile(rf"^#{{1,{level}}}\s", re.MULTILINE)
    blocks = []
    for match in heading_re.finditer(text):
        stop = stop_re.search(text, match.end())
        blocks.append((match.group(1), text[match.start() : stop.start() if stop else len(text)].rstrip()))
    return blocks


def _cited_specs(docstring: str, repo_root: Path) -> list[dict[str, str]]:
    """Spec text for the requirement/scenario a docstring cites as ``specs/<cap> ... Requirement: ... Scenario: ...``."""
    cap_match = _SPEC_PATH_RE.search(docstring)
    if cap_match is None:
        return []
    capability = cap_match.group(1)
    req = _REQUIREMENT_RE.search(docstring)
    scen = _SCENARIO_RE.search(docstring)
    if req is None and scen is None:
        return []
    for path in _spec_files(repo_root, capability):
        text = path.read_text("utf-8")
        block = None
        if scen is not None:
            for _heading, scenario in _spec_blocks(text, "Scenario", 4):
                if _norm(_heading) == _norm(scen.group(1)):
                    block = scenario
                    break
        if block is None and req is not None:
            for heading, requirement in _spec_blocks(text, "Requirement", 3):
                if _norm(heading) == _norm(req.group(1)):
                    block = requirement
                    break
        if block is not None:
            body, cut = _truncate_head(block, MAX_SPEC_CHARS)
            rel = path.relative_to(repo_root).as_posix()
            return [{"source": rel, "text": body, "cut": "yes" if cut else "no"}]
    return []


def _build(entry: TestEntry, repo_root: Path, index: _ModuleIndex) -> tuple[dict[str, Any], bool]:
    parsed = _parse(repo_root / entry.path)
    if parsed is None:
        raise LookupError(f"test file {entry.path} is unreadable")
    tree, lines = parsed
    node = _find_test(tree, entry)
    if node is None:
        raise LookupError(f"{entry.function_name} not found in {entry.path}")

    test_source = _segment(lines, node)
    fixtures = _fixture_sources(entry, node, tree, lines, repo_root)
    used = _used_names(node, *(n for n in (ast.parse(f["source"]) for f in fixtures if f["source"].strip())))
    covered, truncated = _covered_sources(entry.covered_modules, used, index)

    docstrings = [ast.get_docstring(node) or ""]
    if entry.class_name:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == entry.class_name), None)
        docstrings.append((ast.get_docstring(cls) if cls else None) or "")
    specs: list[dict[str, str]] = []
    for doc in docstrings:
        specs += _cited_specs(doc, repo_root)
    spec_cut = any(s.pop("cut") == "yes" for s in specs)

    state: dict[str, Any] = {
        "test": {"node_id": entry.test_id.node_id, "path": entry.path, "source": test_source},
        "module_docstring": ast.get_docstring(tree) or "",
        "fixtures": fixtures,
        "covered_source": covered,
        "cited_spec": specs,
    }
    return state, truncated or spec_cut


def build_state(entry: TestEntry, *, repo_root: Path) -> dict[str, Any]:
    """The blind state for one test (design D7): read-only, deterministic, and free of other approaches' output.

    Raises ``LookupError`` if the test cannot be located in its file.
    """
    return _build(entry, Path(repo_root), _ModuleIndex(Path(repo_root)))[0]


# --------------------------------------------------------------------------- questions


def _questions(index: int) -> dict[str, dict[str, Any]]:
    return {
        f"t{index}.oracle_source": {
            "type": "choice",
            "instructions": _ORACLE_INSTRUCTIONS,
            "criteria": {label: DESCRIPTIONS[label] for label in ORACLE_SOURCES},
        },
        f"t{index}.survives_refactor": {"type": "noul", "instructions": _SURVIVES_INSTRUCTIONS},
        f"t{index}.boundary": {
            "type": "choice",
            "instructions": _BOUNDARY_INSTRUCTIONS,
            "criteria": dict(BOUNDARY_DESCRIPTIONS),
        },
    }


def _estimate_tokens(state: Mapping[str, Any], questions: Mapping[str, Any]) -> int:
    longest = max((len(repr(q)) for q in questions.values()), default=0)
    return math.ceil((len(json.dumps(state, default=str)) + longest) / _CHARS_PER_TOKEN)


# --------------------------------------------------------------------------- answers


def _field(answer: Any, name: str) -> Any:
    if isinstance(answer, Mapping):
        return answer.get(name)
    return getattr(answer, name, None)


def _is_prob(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and 0.0 <= value <= 1.0


def _distribution(answer: Any) -> dict[str, float] | None:
    probs = _field(answer, "probabilities")
    if not isinstance(probs, Mapping) or not probs or not all(_is_prob(v) for v in probs.values()):
        return None
    return {str(k): float(v) for k, v in probs.items()}


def _payload(answers: Mapping[str, Any], index: int, truncated: bool) -> dict[str, Any] | None:
    oracle = _distribution(answers.get(f"t{index}.oracle_source"))
    boundary = _distribution(answers.get(f"t{index}.boundary"))
    survives = _field(answers.get(f"t{index}.survives_refactor"), "noul")
    if oracle is None or boundary is None or not _is_prob(survives):
        return None
    return {
        "oracle_source": oracle,
        "survives_refactor": float(survives),
        "boundary": boundary,
        "truncated": truncated,
    }


def _record(test_id: TestId, status: str, payload: dict[str, Any] | None = None, reason: str | None = None) -> StageRecord:
    return StageRecord(test_id=test_id, stage=STAGE, status=status, payload=payload or {}, reason=reason)


def _unavailable_reason(dry_run: bool) -> str:
    """Why ``decide()`` returned ``None``: dry run, no key, or (the remaining cause) the budget."""
    if dry_run:
        return "dry_run"
    if not os.environ.get("TYPESAFE_API_KEY"):
        return "no_key"
    return "over_budget"


# --------------------------------------------------------------------------- stage


def _judge_batch(
    batch: Sequence[tuple[int, TestEntry, dict[str, Any], bool]],
    *,
    dry_run: bool,
    event_sink: Callable[[dict[str, Any]], None] | None,
) -> dict[int, StageRecord]:
    """One ``decide()`` call over ``batch`` -> records keyed by entry index."""
    state = {f"t{i}": s for i, _e, s, _t in batch}
    questions: dict[str, dict[str, Any]] = {}
    for i, _e, _s, _t in batch:
        questions.update(_questions(i))
    try:
        answers = system_one_decisions.decide(state, questions, site=SITE, event_sink=event_sink, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - shadow stage: a judge failure is data, never an exit
        reason = f"decide_failed: {type(exc).__name__}"
        return {i: _record(e.test_id, "error", reason=reason) for i, e, _s, _t in batch}
    if answers is None:
        reason = _unavailable_reason(dry_run)
        return {i: _record(e.test_id, "degraded", reason=reason) for i, e, _s, _t in batch}
    out: dict[int, StageRecord] = {}
    for i, e, _s, truncated in batch:
        payload = _payload(answers, i, truncated) if isinstance(answers, Mapping) else None
        if payload is None:
            out[i] = _record(e.test_id, "degraded", reason="malformed_answer")
        else:
            out[i] = _record(e.test_id, "ok", payload)
    return out


def run_judged(
    entries: Sequence[TestEntry],
    *,
    repo_root: Path,
    dry_run: bool = False,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    extra_context: Mapping[str, Any] | None = None,
) -> list[StageRecord]:
    """Judged records for ``entries``, in order. Never raises; never gates anything.

    ``extra_context`` (other stages' output keyed by node id) is accepted for caller symmetry and
    deliberately ignored: the judged state is blind to every other approach (design D7).
    """
    del extra_context
    repo_root = Path(repo_root)
    index = _ModuleIndex(repo_root)
    records: dict[int, StageRecord] = {}

    by_file: dict[str, list[tuple[int, TestEntry, dict[str, Any], bool]]] = {}
    for i, entry in enumerate(entries):
        try:
            state, truncated = _build(entry, repo_root, index)
        except Exception as exc:  # noqa: BLE001 - unreadable/missing test source: record, keep going
            records[i] = _record(entry.test_id, "error", reason=f"state_unavailable: {type(exc).__name__}")
            continue
        by_file.setdefault(entry.path, []).append((i, entry, state, truncated))

    for group in by_file.values():
        merged_questions: dict[str, Any] = {}
        for i, _e, _s, _t in group:
            merged_questions.update(_questions(i))
        merged_state = {f"t{i}": s for i, _e, s, _t in group}
        fits = _estimate_tokens(merged_state, merged_questions) <= _TOKEN_BUDGET
        batches = [group] if fits else [[item] for item in group]
        for batch in batches:
            records.update(_judge_batch(batch, dry_run=dry_run, event_sink=event_sink))

    return [records[i] for i in range(len(entries))]
