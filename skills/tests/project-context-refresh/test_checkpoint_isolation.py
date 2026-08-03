"""The load-bearing ri-09 invariant: a checkpoint never writes the ri-06 ledger.

Task 3.1. Spec scenarios: pcro "Checkpoint leaves the shared operation ledger
untouched", pcro "A later canonical refresh is unaffected by a prior
checkpoint". Design decisions: D1, D10.

Why this is asserted rather than assumed: ``git rev-parse --git-common-dir``
from a *linked worktree* resolves to the MAIN clone's ``.git``, so a write that
looks worktree-local from ``checkout_policy``'s path-based view (D10) actually
lands in state shared by every worktree of the clone. ri-07 D9 then makes a
recorded producer result immutable for its revision and reuses it verbatim in
later refreshes, so a scope-restricted checkpoint result admitted into that
ledger is unrecoverable within the ri-06 contract.

The ledger location is resolved through ``store.resolve_git_common_dir`` and
``store._STORE_SUBDIR`` — the same code the store itself uses — so this test
cannot drift away from the path it is guarding.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any

import pytest

import checkpoint
import orchestrator
from _runtime import ProducerResult, ProducerStatus, ValidationResult, ValidationStatus
from registry import Producer, ProducerSpec, register
from store import _STORE_SUBDIR, OperationStore, resolve_git_common_dir

CHANGE_ID = "add-branch-local-context-checkpoints"
PACKAGE_ID = "wp-checkpoint"
CHANGED_FILES = ("docs/guide.md",)

#: Names whose presence in ``checkpoint.py`` would mean the module can reach the
#: canonical ledger or emit a manifest (D1).
FORBIDDEN_NAMES = frozenset(
    {
        "OperationStore",
        "create_or_load",
        "begin_attempt",
        "record_producer_result",
        "record_semantic_index",
        "record_manifest",
        "finalize",
        "write_manifest",
        "RefreshManifest",
    }
)


def _rules() -> Any:
    from context_impact import ImpactRules

    return ImpactRules(
        surface_globs={"documentation": ("docs/**", "**/*.md")},
        source=Path("test-rules.yaml"),
    )


def _package() -> dict[str, Any]:
    return {
        "package_id": PACKAGE_ID,
        "scope": {
            "read_allow": ["docs/**"],
            "write_allow": ["docs/**"],
            "deny": ["**/.venv/**"],
        },
        "context_impact": {"surfaces": ["documentation"]},
    }


class _ModeRecordingProducer(Producer):
    """A registry producer that reports the mode it was run in.

    The mode travels in a ``ValidationResult`` summary so it survives into the
    persisted ri-06 record. That is what lets the "a later refresh is
    unaffected" assertion be real: a refresh that reused checkpoint output would
    show ``check`` where it must show ``generate``.
    """

    spec = ProducerSpec(
        producer_id="documentation.inventory",
        producer_version="1.0.0",
        owner="docs",
        inputs=("docs/**",),
        outputs=(),
    )

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version=self.spec.producer_version,
            status=ProducerStatus.FRESH,
            validations=(
                ValidationResult(
                    validation_id="mode",
                    status=ValidationStatus.PASSED,
                    summary=str(mode),
                ),
            ),
        )


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, str]:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", key, value],
            check=True,
            capture_output=True,
        )
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "guide.md").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"], check=True, capture_output=True
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return tmp_path, head


def _ledger_dir(repo_root: Path) -> Path:
    """The exact directory ``OperationStore`` writes into, resolved its way."""
    return resolve_git_common_dir(repo_root).joinpath(*_STORE_SUBDIR)


def _ledger_entries(repo_root: Path) -> set[str]:
    ledger = _ledger_dir(repo_root)
    if not ledger.exists():
        return set()
    return {str(p.relative_to(ledger)) for p in ledger.rglob("*")}


def _run_checkpoint(repo_root: Path, revision: str) -> Any:
    return checkpoint.run_checkpoint(
        repo_root,
        change_id=CHANGE_ID,
        package_id=PACKAGE_ID,
        package=_package(),
        changed_files=CHANGED_FILES,
        revision=revision,
        rules=_rules(),
    )


# --------------------------------------------------------------------------- #
# D1 — the ledger is untouched
# --------------------------------------------------------------------------- #
def test_ledger_path_resolution_matches_the_store(repo: tuple[Path, str]) -> None:
    """Guard the guard: this test must be looking at the store's own directory."""
    repo_root, _head = repo
    assert OperationStore(repo_root).base_dir == _ledger_dir(repo_root)


def test_checkpoint_adds_no_entry_to_the_refresh_operations_directory(
    repo: tuple[Path, str],
) -> None:
    repo_root, head = repo
    register(_ModeRecordingProducer())
    before = _ledger_entries(repo_root)

    result = _run_checkpoint(repo_root, head)

    assert (repo_root / result.report_path).is_file(), "the checkpoint produced no report"
    assert _ledger_entries(repo_root) == before


def test_checkpoint_writes_no_manifest(repo: tuple[Path, str]) -> None:
    repo_root, head = repo
    register(_ModeRecordingProducer())

    _run_checkpoint(repo_root, head)

    assert not (repo_root / orchestrator.DEFAULT_MANIFEST_PATH).exists()
    assert not (repo_root / ".git-context").exists()


def test_checkpoint_leaves_a_pre_existing_ledger_byte_identical(
    repo: tuple[Path, str],
) -> None:
    """A checkpoint must not mutate ledger entries that already exist either."""
    repo_root, head = repo
    register(_ModeRecordingProducer())
    store = OperationStore(repo_root)
    store.create_or_load("fixture-repo", head)

    ledger = _ledger_dir(repo_root)
    before = {
        str(p.relative_to(ledger)): p.read_bytes()
        for p in sorted(ledger.rglob("*"))
        if p.is_file()
    }
    assert before, "fixture failed to seed the ledger"

    _run_checkpoint(repo_root, head)

    after = {
        str(p.relative_to(ledger)): p.read_bytes()
        for p in sorted(ledger.rglob("*"))
        if p.is_file()
    }
    assert after == before


def test_a_later_canonical_refresh_computes_its_own_results(
    repo: tuple[Path, str],
) -> None:
    repo_root, head = repo
    register(_ModeRecordingProducer())

    checkpoint_result = _run_checkpoint(repo_root, head)
    assert [
        v["summary"]
        for r in checkpoint_result.report["producer_results"]
        for v in r["validations"]
    ] == ["check"]

    refresh = orchestrator.generate(
        repo_root,
        revision=head,
        architecture=lambda repository, revision, mode: ProducerResult(
            producer_id="architecture",
            producer_version="1.0.0",
            status=ProducerStatus.FRESH,
        ),
    )

    # The refresh created its own operation and ran its own producers in
    # generate mode; nothing from the checkpoint was reused.
    assert refresh.operation_id
    summaries = [
        v.summary for r in refresh.producer_results for v in r.validations
    ]
    assert summaries == ["generate"]

    persisted = OperationStore(repo_root).load(refresh.operation_id)
    assert [
        v.summary for r in persisted.producer_results for v in r.validations
    ] == ["generate"]


# --------------------------------------------------------------------------- #
# D1 — structural: the module cannot reach the ledger at all
# --------------------------------------------------------------------------- #
def _referenced_names(module_path: Path) -> set[str]:
    """Every imported name, attribute, and identifier used in *module_path*."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            names.update(alias.asname for alias in node.names if alias.asname)
        elif isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
            names.update(alias.asname for alias in node.names if alias.asname)
    return names


def test_checkpoint_module_never_names_the_operation_store() -> None:
    module_path = Path(checkpoint.__file__)
    used = _referenced_names(module_path) & FORBIDDEN_NAMES
    assert used == set(), (
        f"{module_path.name} references ledger-writing names {sorted(used)}; "
        "D1 forbids a checkpoint from becoming a second writer of canonical state"
    )


def test_checkpoint_module_does_not_import_the_store_or_manifest_modules() -> None:
    tree = ast.parse(Path(checkpoint.__file__).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
    assert {"store", "manifest", "orchestrator"} & modules == set()
