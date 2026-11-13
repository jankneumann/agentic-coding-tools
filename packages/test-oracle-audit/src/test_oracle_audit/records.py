"""Shared record types for every audit stage (design D1).

Every stage emits :class:`StageRecord` lines to ``<out>/<stage>.jsonl``; the
analysis joins them on :class:`TestId`. The JSON shape is defined by
``schemas/stage-record.schema.json`` (a byte-identical runtime copy of the
change's ``contracts/schemas/``), and :func:`validate` checks against it.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_VERSION = 1

STAGES = ("inventory", "static", "judged", "mutation", "rename", "history", "explain")
STATUSES = ("ok", "degraded", "skipped", "error")

# The evidence class each stage's records carry (D7: judged answers are
# judgment evidence only and never deterministic facts).
STAGE_EVIDENCE_CLASS = {
    "inventory": "deterministic",
    "static": "deterministic",
    "judged": "judgment",
    "mutation": "execution",
    "rename": "execution",
    "history": "history",
    "explain": "prose",
}

SCHEMA_NAMES = ("stage-record", "label-ledger", "mutation-result", "analysis-report")


@dataclass(frozen=True)
class TestId:
    """A test's stable identity: pytest node id plus normalized source hash."""

    __test__ = False  # not a pytest test class

    node_id: str
    content_hash: str

    def to_json(self) -> dict[str, str]:
        return {"node_id": self.node_id, "content_hash": self.content_hash}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> TestId:
        return cls(node_id=data["node_id"], content_hash=data["content_hash"])


@dataclass(frozen=True)
class StageRecord:
    """One test's result for one stage."""

    test_id: TestId
    stage: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    evidence_class: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"unknown stage {self.stage!r}; expected one of {STAGES}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}; expected one of {STATUSES}")
        if self.status != "ok" and not self.reason:
            raise ValueError(f"a {self.status!r} record must carry a reason")
        if self.evidence_class is None:
            object.__setattr__(self, "evidence_class", STAGE_EVIDENCE_CLASS[self.stage])

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "test_id": self.test_id.to_json(),
            "stage": self.stage,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "payload": self.payload,
        }
        if self.reason is not None:
            out["reason"] = self.reason
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> StageRecord:
        return cls(
            test_id=TestId.from_json(data["test_id"]),
            stage=data["stage"],
            status=data["status"],
            payload=dict(data.get("payload", {})),
            reason=data.get("reason"),
            evidence_class=data.get("evidence_class"),
        )


@dataclass(frozen=True)
class TestEntry:
    """One collected test, as produced by the inventory stage."""

    __test__ = False

    test_id: TestId
    path: str
    line_start: int
    line_end: int
    function_name: str
    class_name: str | None = None
    fixtures: tuple[str, ...] = ()
    covered_modules: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "function_name": self.function_name,
            "class_name": self.class_name,
            "fixtures": list(self.fixtures),
            "covered_modules": list(self.covered_modules),
        }

    def to_record(self) -> StageRecord:
        return StageRecord(test_id=self.test_id, stage="inventory", status="ok", payload=self.to_payload())

    @classmethod
    def from_record(cls, record: StageRecord) -> TestEntry:
        p = record.payload
        return cls(
            test_id=record.test_id,
            path=p["path"],
            line_start=p["line_start"],
            line_end=p["line_end"],
            function_name=p.get("function_name") or record.test_id.node_id.split("::")[-1].split("[")[0],
            class_name=p.get("class_name"),
            fixtures=tuple(p.get("fixtures", ())),
            covered_modules=tuple(p.get("covered_modules", ())),
        )


def to_entries(records: Iterable[StageRecord]) -> list[TestEntry]:
    """Inventory records with status ``ok`` as :class:`TestEntry` objects."""
    return [TestEntry.from_record(r) for r in records if r.stage == "inventory" and r.status == "ok"]


@dataclass(frozen=True)
class SuiteSpec:
    """A suite to audit (design D1). Paths are relative to the repository root."""

    name: str
    project_root: str
    test_paths: tuple[str, ...]
    source_roots: tuple[str, ...]
    pytest_args: tuple[str, ...] = ()
    # Optional-dependency extras the suite's own project needs to run its tests
    # (`uv run --project <root> --extra <x>`); spike 3.1, design D4.
    uv_extras: tuple[str, ...] = ()


def load_suites(path: Path | None = None) -> dict[str, SuiteSpec]:
    """Load suite specs from ``config/suites.json`` (or ``path``)."""
    if path is None:
        text = resources.files("test_oracle_audit").joinpath("config/suites.json").read_text("utf-8")
    else:
        text = Path(path).read_text("utf-8")
    raw = json.loads(text)["suites"]
    return {
        name: SuiteSpec(
            name=name,
            project_root=spec["project_root"],
            test_paths=tuple(spec["test_paths"]),
            source_roots=tuple(spec["source_roots"]),
            pytest_args=tuple(spec.get("pytest_args", ())),
            uv_extras=tuple(spec.get("uv_extras", ())),
        )
        for name, spec in raw.items()
    }


# --- content hashing ------------------------------------------------------


def normalized_source(node: ast.AST) -> str:
    """``ast.unparse`` of a node: drops comments and formatting, keeps logic."""
    return ast.unparse(node)


def hash_source(normalized: str) -> str:
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_function(tree: ast.Module, function_name: str, class_name: str | None = None) -> ast.AST | None:
    """The (async) function ``function_name``, optionally inside ``class_name``."""
    scope: Sequence[ast.stmt] = tree.body
    if class_name is not None:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if cls is None:
            return None
        scope = cls.body
    for node in scope:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name:
            return node
    return None


def content_hash(source: str, function_name: str, class_name: str | None = None) -> str:
    """Hash of one test function's normalized source, from a module's text.

    Whitespace and comments do not change the hash; any change to the
    function's logic (including its decorators and docstring) does.
    Raises ``LookupError`` if the function is not in the module.
    """
    node = find_function(ast.parse(source), function_name, class_name)
    if node is None:
        where = f"{class_name}.{function_name}" if class_name else function_name
        raise LookupError(f"function {where} not found")
    return hash_source(normalized_source(node))


def content_hash_of_file(path: Path, function_name: str, class_name: str | None = None) -> str:
    return content_hash(Path(path).read_text("utf-8"), function_name, class_name)


def split_node_id(node_id: str) -> tuple[str, str | None, str]:
    """``path::[Class::]func[param]`` -> (path, class or None, func without params)."""
    parts = node_id.split("::")
    path, rest = parts[0], parts[1:]
    func = rest[-1].split("[", 1)[0] if rest else ""
    cls = rest[-2] if len(rest) >= 2 else None
    return path, cls, func


# --- JSONL I/O ------------------------------------------------------------


def write_records(path: Path, records: Iterable[StageRecord]) -> None:
    """Write records as JSONL, one validated record per line."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            data = record.to_json()
            validate(data, "stage-record")
            fh.write(json.dumps(data, sort_keys=True) + "\n")


def read_records(path: Path) -> list[StageRecord]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            out.append(StageRecord.from_json(json.loads(line)))
    return out


# --- schema validation ----------------------------------------------------


@functools.cache
def load_schema(name: str) -> dict[str, Any]:
    """A runtime schema copy by short name, e.g. ``"stage-record"``."""
    filename = name if name.endswith(".json") else f"{name}.schema.json"
    text = resources.files("test_oracle_audit").joinpath("schemas", filename).read_text("utf-8")
    return json.loads(text)


def validate(instance: Mapping[str, Any], schema_name: str) -> None:
    """Raise ``jsonschema.ValidationError`` if ``instance`` violates the schema."""
    jsonschema.Draft202012Validator(load_schema(schema_name)).validate(instance)
