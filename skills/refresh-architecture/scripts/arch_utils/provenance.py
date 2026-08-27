"""Architecture producer provenance and content-based freshness (ri-04).

This module owns the architecture-specific deterministic evidence that lives
beside the generated artifacts:

* which source inputs and producer identity generated the architecture graph,
  summary, diagnostics, zones, views, and report (the *input fingerprint* and
  *producer identity*); and
* a read-only, mtime-independent freshness check that reports exact drift
  reasons and stale artifact paths.

It deliberately does **not** own operation identity, locking, atomic operation
persistence, or the canonical ``ProducerResult`` — ``project-context-runtime``
(ri-06) owns those, and :mod:`context_runtime_adapter` bridges to it. See the
change's ``design.md`` decisions D1-D4.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arch_utils.determinism import source_date_epoch

# --------------------------------------------------------------------------- #
# Canonical serialization / hashing — reuse ri-06 atomic primitives when the
# stacked runtime is importable, else fall back to an identical local impl so
# provenance stays byte-stable even outside the runtime worktree.
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - import wiring
    _RUNTIME_SCRIPTS = (
        Path(__file__).resolve().parents[3] / "project-context-runtime" / "scripts"
    )
    if _RUNTIME_SCRIPTS.is_dir() and str(_RUNTIME_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_RUNTIME_SCRIPTS))
    from atomic import atomic_write_bytes as _atomic_write_bytes  # type: ignore
    from atomic import canonical_json_bytes as _canonical_bytes  # type: ignore
    from atomic import sha256_hex as _sha256_hex  # type: ignore
except Exception:  # pragma: no cover - fallback path

    def _canonical_bytes(data: Any) -> bytes:
        text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
        return (text + "\n").encode("utf-8")

    def _sha256_hex(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _atomic_write_bytes(target: Path, payload: bytes) -> bool:
        target = Path(target)
        if target.exists() and target.read_bytes() == payload:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return True


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
PRODUCER_ID = "architecture"
#: Bump when the producer's output-affecting logic changes. A recorded value
#: that differs from this triggers a PRODUCER_IDENTITY_MISMATCH on check.
#:
#: 1.1.0 — input enumeration asks git which files are version-controlled instead
#: of walking the working tree with a name-only exclusion list. Provenance built
#: by 1.0.0 fingerprinted whatever ignored files happened to sit under an input
#: root on the generating machine, so it can never match a clean checkout.
#:
#: 1.2.0 — the tree-sitter enrichment pass orders its occurrence lists. Before
#: this, `QueryCursor.captures()` returned them in an order that varied between
#: runs of one revision, so treesitter_enrichment.json (and every digest over
#: it) changed on every refresh. Artifacts built by 1.1.0 carry that arbitrary
#: order and so cannot match a current rebuild; the identity mismatch says that
#: plainly rather than surfacing as an unexplained fingerprint difference.
#:
#: 1.3.0 — the *set of artifacts this producer commits* changed: the tree-sitter
#: enrichment, Python analysis and parallel-zone caches are still generated but
#: no longer tracked. This is a different fact from the record-shape change
#: below, and both are compared: a reader seeing only the schema bump could not
#: tell whether the artifact set had changed, and vice versa.
PRODUCER_VERSION = "1.3.0"
#: Bump when the *shape* of the provenance record changes.
#:
#: 2 — every artifact entry carries a required ``tier``. Not optional-with-a-
#: default: defaulting would read every entry of a pre-tier record as
#: ``committed``, which is exactly the silent misclassification the field exists
#: to prevent. An earlier version is rejected loudly instead.
PROVENANCE_SCHEMA_VERSION = 2

ARCH_DIR_DEFAULT = "docs/architecture-analysis"
PROVENANCE_FILENAME = "architecture.provenance.json"

#: Fallback deterministic epoch (2023-11-14T22:13:20Z) for repos without a
#: resolvable commit timestamp — keeps ad-hoc generation reproducible.
_FIXED_EPOCH = 1_700_000_000

#: Where an artifact's bytes are expected to live, and therefore what its
#: absence means. ``committed`` bytes are tracked in version control, so a clean
#: checkout is expected to contain them and absence is drift. ``local-cache``
#: bytes are generated by the pipeline but deliberately not tracked, so a clean
#: checkout is expected *not* to contain them and absence is the normal state.
#: The digest is verified for both tiers whenever the file is present, so a
#: stale local cache is reported rather than trusted.
TIER_COMMITTED = "committed"
TIER_LOCAL_CACHE = "local-cache"

#: Canonical owned artifacts under the architecture output directory. Only
#: those present are recorded; ``required`` ones missing make a refresh stale.
#:
#: ``required`` and ``tier`` answer different questions and neither substitutes
#: for the other: ``required`` governs generation and promotion ("must this run
#: produce it?"), ``tier`` governs the freshness check ("should a clean checkout
#: have it?"). The three caches below have no reader outside this pipeline, so
#: they are generated locally and never committed.
_OWNED_TOP_LEVEL: tuple[tuple[str, bool, str], ...] = (
    ("architecture.graph.json", True, TIER_COMMITTED),
    ("architecture.summary.json", True, TIER_COMMITTED),
    ("architecture.diagnostics.json", False, TIER_COMMITTED),
    ("parallel_zones.json", False, TIER_LOCAL_CACHE),
    ("architecture.report.md", False, TIER_COMMITTED),
    ("python_analysis.json", False, TIER_LOCAL_CACHE),
    ("ts_analysis.json", False, TIER_COMMITTED),
    ("postgres_analysis.json", False, TIER_COMMITTED),
    ("treesitter_enrichment.json", False, TIER_LOCAL_CACHE),
    ("comment_insights.json", False, TIER_COMMITTED),
    ("pattern_insights.json", False, TIER_COMMITTED),
)

#: How the relevant-input set was enumerated. Recorded in provenance and compared
#: as producer identity, because the two strategies see different file sets: only
#: ``git`` honours ``.gitignore``, so a ``walk`` fingerprint carries whatever
#: ignored files existed on the generating machine and a ``git`` fingerprint does
#: not. Comparing them as raw fingerprints would report
#: INPUT_FINGERPRINT_MISMATCH — "the inputs changed" — for what is really "these
#: two numbers are not the same kind of number".
INPUT_ENUMERATION_GIT = "git"
INPUT_ENUMERATION_WALK = "walk"

#: Directory names never walked when fingerprinting relevant inputs. Only
#: consulted by the ``walk`` fallback; under ``git`` enumeration ``.gitignore``
#: is the authority and this list is not applied.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".git-worktrees",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }
)

# Freshness drift reason codes (stable, machine-readable).
PROVENANCE_MISSING = "PROVENANCE_MISSING"
PROVENANCE_INVALID = "PROVENANCE_INVALID"
PROVENANCE_SCHEMA_VERSION_MISMATCH = "PROVENANCE_SCHEMA_VERSION_MISMATCH"
INPUT_FINGERPRINT_MISMATCH = "INPUT_FINGERPRINT_MISMATCH"
PRODUCER_IDENTITY_MISMATCH = "PRODUCER_IDENTITY_MISMATCH"
ARTIFACT_DIGEST_MISMATCH = "ARTIFACT_DIGEST_MISMATCH"
ARTIFACT_MISSING = "ARTIFACT_MISSING"


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DriftReason:
    code: str
    detail: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if self.path is not None:
            out["path"] = self.path
        return out


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a read-only architecture freshness check.

    ``status`` is one of ``fresh`` | ``stale`` | ``invalid``. ``fresh`` means the
    committed artifacts describe the current relevant inputs and producer; the
    check writes no repository or runtime state.
    """

    status: str
    reasons: tuple[DriftReason, ...] = ()
    provenance: dict[str, Any] | None = None

    @property
    def is_fresh(self) -> bool:
        return self.status == "fresh"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": [r.to_dict() for r in self.reasons],
            "artifacts": [r.path for r in self.reasons if r.path],
            # Recorded artifacts the generating run did not produce. Not drift —
            # the optional stages skip soft by design — but a reader deciding
            # how much to trust a `fresh` verdict needs to see which artifacts
            # it does not cover. Empty for provenance predating the flag.
            "carried_over": [
                art["path"]
                for art in (self.provenance or {}).get("artifacts", [])
                if art.get("carried_over")
            ],
        }


# --------------------------------------------------------------------------- #
# Git / repository identity
# --------------------------------------------------------------------------- #
def _git_raw(repo_root: Path, *args: str) -> str | None:
    """Run git and return stdout verbatim, or ``None`` if it could not run.

    Unstripped, because ``-z`` output is NUL-delimited and trailing whitespace
    is significant to a filename.
    """
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def _git(repo_root: Path, *args: str) -> str | None:
    out = _git_raw(repo_root, *args)
    return None if out is None else out.strip()


def repository_id(repo_root: Path | str) -> str:
    """Return the stable repository id used for the shared operation identity.

    Overridable via ``PROJECT_CONTEXT_REPO_ID`` so the architecture adapter and
    every other producer agree on one id for the same clone.
    """
    override = os.environ.get("PROJECT_CONTEXT_REPO_ID")
    if override:
        return override
    repo_root = Path(repo_root)
    toplevel = _git(repo_root, "rev-parse", "--show-toplevel")
    if toplevel:
        return Path(toplevel).name
    return repo_root.resolve().name


def analyzed_revision(repo_root: Path | str) -> str | None:
    """Return the full 40-char ``HEAD`` SHA, or ``None`` outside a committed repo."""
    rev = _git(Path(repo_root), "rev-parse", "HEAD")
    if rev and len(rev) == 40 and all(c in "0123456789abcdef" for c in rev):
        return rev
    return None


def worktree_dirty(repo_root: Path | str, roots: list[str]) -> bool:
    """Return whether any relevant tracked or untracked input differs from HEAD."""
    repo_root = Path(repo_root)
    existing = [r for r in roots if (repo_root / r).exists()]
    if not existing:
        return False
    out = _git(repo_root, "status", "--porcelain", "--", *existing)
    return bool(out)


# --------------------------------------------------------------------------- #
# Deterministic clock
# --------------------------------------------------------------------------- #
def deterministic_epoch(repo_root: Path | str, source_revision: str | None) -> int:
    """Resolve the deterministic epoch: ``SOURCE_DATE_EPOCH`` → commit ts → fixed."""
    override = source_date_epoch()
    if override is not None:
        return override
    if source_revision:
        ts = _git(Path(repo_root), "show", "-s", "--format=%ct", source_revision)
        if ts and ts.isdigit():
            return int(ts)
    return _FIXED_EPOCH


def deterministic_timestamp(repo_root: Path | str, source_revision: str | None) -> str:
    """ISO-8601 UTC timestamp derived from :func:`deterministic_epoch`."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(
        deterministic_epoch(repo_root, source_revision), tz=timezone.utc
    ).isoformat()


# --------------------------------------------------------------------------- #
# Relevant-input discovery and fingerprint
# --------------------------------------------------------------------------- #
def default_input_roots(env: Mapping[str, str] | None = None) -> list[str]:
    """Relevant input roots, mirroring ``refresh_architecture.sh`` env overrides.

    ``env`` defaults to ``os.environ``, but callers that hand the analyzers a
    *child* environment must pass that same mapping. ``run_architecture.py``
    builds the overrides into a child dict without touching ``os.environ``, so
    reading the ambient environment here silently recorded the fallback roots
    (``src``/``web``/``database/migrations``) instead of the ones actually
    analyzed — and a fingerprint over roots that do not exist can never change,
    which makes the freshness check fail open.
    """
    source = os.environ if env is None else env
    roots = [
        source.get("PYTHON_SRC_DIR", "src"),
        source.get("TS_SRC_DIR", "web"),
        source.get("MIGRATIONS_DIR", "database/migrations"),
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered


def input_enumeration_strategy(repo_root: Path | str) -> str:
    """Which enumeration strategy is available here: ``git``, else ``walk``.

    ``git`` is used whenever *repo_root* is inside a work tree and the binary
    answers, which is the case for every developer checkout and every CI job.
    ``walk`` exists for a source export with no ``.git`` — it is a degraded
    strategy, and recording which one produced a fingerprint is what stops the
    degradation from being silent.
    """
    inside = _git(Path(repo_root), "rev-parse", "--is-inside-work-tree")
    return INPUT_ENUMERATION_GIT if inside == "true" else INPUT_ENUMERATION_WALK


def _iter_root_files_git(repo_root: Path, root: str) -> list[Path] | None:
    """Version-controlled files under *root*, or ``None`` if git cannot answer.

    ``--cached --others --exclude-standard`` is the set "tracked, plus untracked
    files that are not ignored" — precisely the files a clean clone of this
    revision would also have. A new source file that has not been ``git add``-ed
    still counts as an input; an ignored file never does.
    """
    out = _git_raw(repo_root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", root)
    if out is None:
        return None
    # ``--cached`` can list a path once per merge stage; de-duplicate so a
    # conflicted index cannot double-count an input.
    rels = sorted({rel for rel in out.split("\0") if rel})
    return [repo_root / rel for rel in rels]


def _iter_root_files(repo_root: Path, root: str) -> list[Path]:
    base = repo_root / root
    if base.is_file():
        return [base]
    if not base.is_dir():
        return []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_DIR_NAMES)
        for name in filenames:
            files.append(Path(dirpath) / name)
    return files


def _discover(
    repo_root: Path, roots: list[str], enumeration: str
) -> tuple[list[dict[str, Any]], list[str], str]:
    """``(entries, missing_roots, enumeration_used)`` for *roots*.

    The returned strategy is the one that actually produced the entries, not the
    one requested. If ``git`` is requested and any root cannot be enumerated
    through it, the whole call degrades to ``walk`` and says so — enumerating
    some roots one way and some the other would yield a fingerprint that belongs
    to neither strategy, and labelling that ``git`` would reproduce the exact
    silent divergence this enumeration exists to remove.
    """
    per_root: dict[str, list[Path]] = {}
    if enumeration == INPUT_ENUMERATION_GIT:
        for root in sorted(set(roots)):
            found = _iter_root_files_git(repo_root, root)
            if found is None:
                enumeration = INPUT_ENUMERATION_WALK
                per_root.clear()
                break
            per_root[root] = found
    if enumeration != INPUT_ENUMERATION_GIT:
        per_root = {root: _iter_root_files(repo_root, root) for root in sorted(set(roots))}

    arch_dir = (repo_root / ARCH_DIR_DEFAULT).resolve()
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for root in sorted(set(roots)):
        found = per_root[root]
        if not found and not (repo_root / root).exists():
            missing.append(root)
            continue
        for f in found:
            rf = f.resolve()
            # Never fingerprint our own outputs.
            if arch_dir == rf or arch_dir in rf.parents:
                continue
            try:
                data = rf.read_bytes()
            except OSError:
                continue
            rel = rf.relative_to(repo_root).as_posix()
            entries.append({"path": rel, "mode": _portable_mode(rf), "sha256": _sha256_hex(data)})
    entries.sort(key=lambda e: e["path"])
    return entries, sorted(missing), enumeration


def _portable_mode(path: Path) -> str:
    """The git-visible mode of *path*: ``100755`` if executable, else ``100644``.

    Full permission bits are a property of the checking-out machine's umask, not
    of the repository — git records only the executable bit. Fingerprinting
    ``st_mode & 0o777`` therefore makes the same commit hash differently under a
    umask of 022 and 002, which is drift no refresh can resolve.
    """
    return "100755" if path.stat().st_mode & 0o111 else "100644"


def discover_relevant_inputs(
    repo_root: Path | str, roots: list[str], *, enumeration: str | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return ``(entries, missing_roots)`` describing relevant input bytes.

    Each entry is ``{"path", "mode", "sha256"}`` for one version-controlled file
    under a declared root, sorted by repo-relative POSIX path. Reading
    working-tree bytes (not the HEAD blob) is what makes a dirty relevant input
    change the fingerprint (spec scenario architecture-refresh.2) — git decides
    *which* files are inputs, the working tree decides what they contain.
    """
    repo_root = Path(repo_root).resolve()
    if enumeration is None:
        enumeration = input_enumeration_strategy(repo_root)
    entries, missing, _used = _discover(repo_root, roots, enumeration)
    return entries, missing


def compute_input_fingerprint(
    repo_root: Path | str, roots: list[str], *, enumeration: str | None = None
) -> tuple[str, str]:
    """Return ``(fingerprint, enumeration_used)`` for the relevant inputs.

    The strategy is returned rather than assumed so callers record the one that
    actually ran. The strategy is deliberately *not* mixed into the hashed
    payload: it is compared as producer identity, which reports "these were
    enumerated differently" instead of the misleading "the inputs changed".
    """
    repo_root = Path(repo_root).resolve()
    if enumeration is None:
        enumeration = input_enumeration_strategy(repo_root)
    entries, missing, used = _discover(repo_root, roots, enumeration)
    payload = {
        "roots": sorted(set(roots)),
        "inputs": entries,
        "missing_roots": missing,
    }
    return _sha256_hex(_canonical_bytes(payload)), used


# --------------------------------------------------------------------------- #
# Optional-tool identity (output-affecting)
# --------------------------------------------------------------------------- #
def detect_optional_tools() -> list[dict[str, Any]]:
    """Identify output-affecting optional tools, one entry per grammar.

    Reports the interpreter the *pipeline* would use, not the one running this
    function. Importing ``tree_sitter`` in-process answered a different question:
    a refresh driven by an interpreter without the package skipped the
    enrichment, comment-linker and pattern-reporter stages while provenance —
    running under a Python that did have it — still recorded
    ``available: true``. The record then vouched for artifacts that were never
    regenerated (issue #378).

    A single ``tree-sitter`` entry could not say *which* stages ran, because the
    grammars install independently: an interpreter with the Python and
    TypeScript grammars but not the SQL one produces enrichment but no
    tree-sitter SQL analysis. Recording each grammar keeps the record and the
    pipeline's stage verdicts derived from one resolver answer, so they cannot
    disagree about which stage had what it needed.

    A version is recorded only for an importable grammar; distribution metadata
    can outlive a package that no longer imports, and reporting that version
    would overstate what the run had.
    """
    from arch_utils.interpreters import (
        GRAMMAR_MODULES,
        resolve_grammars,
        tool_name,
    )

    resolution = resolve_grammars()
    tools: list[dict[str, Any]] = []
    for module in sorted(GRAMMAR_MODULES):
        available = bool(resolution.available.get(module, False))
        tools.append(
            {
                "name": tool_name(module),
                "available": available,
                "version": resolution.versions.get(module) if available else None,
            }
        )
    return tools


# --------------------------------------------------------------------------- #
# Owned-artifact digests
# --------------------------------------------------------------------------- #
def hash_file(path: Path) -> tuple[str, int]:
    data = Path(path).read_bytes()
    return _sha256_hex(data), len(data)


def owned_artifacts(
    repo_root: Path | str,
    arch_dir: str = ARCH_DIR_DEFAULT,
    *,
    generated: Collection[str] | None = None,
) -> list[dict[str, Any]]:
    """Return sorted digests for the owned architecture artifacts that exist.

    *generated* is the set of paths, relative to *arch_dir* and POSIX-separated,
    that the current run actually produced — what promotion wrote, not what the
    output directory happens to contain. Promotion is a one-way merge (it copies
    and never deletes, deliberately: the optional stages fail soft, and
    ``views/.gitkeep`` is committed but never staged), so scanning the directory
    cannot tell an artifact this revision generated from one an earlier revision
    left behind. Every entry then gets an explicit ``carried_over`` flag.

    Passing ``None`` means the caller does not know what the run produced, and
    the flag is omitted rather than guessed — which is also the shape of every
    document written before this field existed. Absent is "unknown"; present is
    a claim. Nothing is dropped from the record either way, so a carried-over
    artifact keeps its digest pinned and hand-edits to it still surface as
    ARTIFACT_DIGEST_MISMATCH.
    """
    repo_root = Path(repo_root)
    base = repo_root / arch_dir
    known = None if generated is None else {Path(g).as_posix() for g in generated}

    def _entry(path: Path, rel_to_arch: str, required: bool, tier: str) -> dict[str, Any]:
        digest, size = hash_file(path)
        record: dict[str, Any] = {
            "path": f"{arch_dir}/{rel_to_arch}",
            "sha256": digest,
            "size_bytes": size,
            "required": required,
            "tier": tier,
        }
        if known is not None:
            record["carried_over"] = rel_to_arch not in known
        return record

    out: list[dict[str, Any]] = []
    for name, required, tier in _OWNED_TOP_LEVEL:
        p = base / name
        if p.is_file():
            out.append(_entry(p, name, required, tier))
    views = base / "views"
    if views.is_dir():
        # Rendered views are tracked in git, so their absence is real drift.
        for p in sorted(views.rglob("*")):
            if p.is_file():
                out.append(_entry(p, p.relative_to(base).as_posix(), False, TIER_COMMITTED))
    out.sort(key=lambda a: a["path"])
    return out


# --------------------------------------------------------------------------- #
# Build / read / validate / write provenance
# --------------------------------------------------------------------------- #
def _published_schema_path() -> Path | None:
    candidate = (
        Path(__file__).resolve().parents[4]
        / "openspec"
        / "schemas"
        / "architecture-provenance.schema.json"
    )
    return candidate if candidate.is_file() else None


def validate_provenance(doc: dict[str, Any]) -> None:
    """Validate *doc* against the published architecture provenance schema.

    Raises ``ValueError`` on any violation so callers fail closed. If the
    published schema cannot be located (e.g. a trimmed runtime copy), structural
    validation is skipped but the document is still required to be a dict.
    """
    if not isinstance(doc, dict):
        raise ValueError("provenance document must be an object")
    schema_path = _published_schema_path()
    if schema_path is None:  # pragma: no cover - depends on install layout
        return
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(doc),
        key=lambda e: list(e.absolute_path),
    )
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise ValueError(f"architecture provenance schema validation failed: {rendered}")


def build_provenance(
    repo_root: Path | str,
    *,
    mode: str,
    arch_dir: str = ARCH_DIR_DEFAULT,
    roots: list[str] | None = None,
    optional_tools: list[dict[str, Any]] | None = None,
    source_revision: str | None = None,
    dirty: bool | None = None,
    warning_count: int = 0,
    generated_at: str | None = None,
    generated: Collection[str] | None = None,
) -> dict[str, Any]:
    """Assemble a schema-valid architecture provenance document from disk state.

    *generated* is forwarded to :func:`owned_artifacts` — see there for why a
    caller that knows what the run produced must say so.
    """
    repo_root = Path(repo_root)
    roots = roots if roots is not None else default_input_roots()
    tools = optional_tools if optional_tools is not None else detect_optional_tools()
    rev = source_revision if source_revision is not None else analyzed_revision(repo_root)
    if rev is None:
        raise ValueError("cannot build provenance without a resolvable HEAD revision")
    is_dirty = dirty if dirty is not None else worktree_dirty(repo_root, roots)
    ts = generated_at if generated_at is not None else deterministic_timestamp(repo_root, rev)
    fingerprint, enumeration = compute_input_fingerprint(repo_root, roots)
    doc: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "producer": {"producer_id": PRODUCER_ID, "producer_version": PRODUCER_VERSION},
        "repository_id": repository_id(repo_root),
        "source_revision": rev,
        "worktree_dirty": bool(is_dirty),
        "mode": mode,
        "input_roots": sorted(set(roots)),
        "input_enumeration": enumeration,
        "input_fingerprint": fingerprint,
        "generated_at": ts,
        "optional_tools": tools,
        "validation": {
            "status": "passed" if warning_count == 0 else "passed-with-warnings",
            "error_count": 0,
            "warning_count": warning_count,
        },
        "artifacts": owned_artifacts(repo_root, arch_dir, generated=generated),
    }
    return doc


def provenance_path(repo_root: Path | str, arch_dir: str = ARCH_DIR_DEFAULT) -> Path:
    return Path(repo_root) / arch_dir / PROVENANCE_FILENAME


def load_provenance(
    repo_root: Path | str, arch_dir: str = ARCH_DIR_DEFAULT
) -> dict[str, Any] | None:
    """Load the committed provenance document, or ``None`` if absent/unreadable."""
    p = provenance_path(repo_root, arch_dir)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_provenance(
    repo_root: Path | str, doc: dict[str, Any], arch_dir: str = ARCH_DIR_DEFAULT
) -> tuple[bool, str]:
    """Atomically persist canonical provenance bytes; return ``(changed, sha256)``.

    A byte-identical rewrite returns ``changed=False`` and never touches the
    file, so a repeat refresh of the same identity produces no repository diff.
    """
    validate_provenance(doc)
    payload = _canonical_bytes(doc)
    changed = _atomic_write_bytes(provenance_path(repo_root, arch_dir), payload)
    return changed, _sha256_hex(payload)


# --------------------------------------------------------------------------- #
# Content-based freshness check (read-only)
# --------------------------------------------------------------------------- #
def check_freshness(
    repo_root: Path | str,
    arch_dir: str = ARCH_DIR_DEFAULT,
    *,
    mode: str = "full",
    optional_tools: list[dict[str, Any]] | None = None,
) -> CheckResult:
    """Recompute architecture identity and compare it with committed provenance.

    Writes no repository or runtime state. Returns ``fresh`` only when the
    committed provenance is at the current schema version and schema-valid, the
    relevant input fingerprint and producer identity match, every recorded
    ``committed`` artifact is present, and every recorded artifact that is
    present matches its digest. Never uses mtime or elapsed wall-clock age.
    """
    repo_root = Path(repo_root)
    prov = load_provenance(repo_root, arch_dir)
    if prov is None:
        return CheckResult(
            "invalid",
            (DriftReason(PROVENANCE_MISSING, "no committed architecture provenance"),),
        )
    # A record written at an earlier schema version cannot be re-read through the
    # current rules — its artifact entries carry no tier, so every judgement
    # below would be made on a shape this producer no longer emits. Checked
    # before (and independently of) structural validation so the verdict names
    # the version even where the published schema file is not installed, and so
    # the remediation reads "regenerate the record" rather than being mistaken
    # for drift in some individual file.
    if isinstance(prov, dict) and prov.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        version_reasons = [
            DriftReason(
                PROVENANCE_SCHEMA_VERSION_MISMATCH,
                f"provenance schema_version {prov.get('schema_version')!r} != current "
                f"{PROVENANCE_SCHEMA_VERSION!r}; regenerate the provenance record",
            )
        ]
        try:
            validate_provenance(prov)
        except ValueError as exc:
            version_reasons.append(DriftReason(PROVENANCE_INVALID, str(exc)))
        return CheckResult("stale", tuple(version_reasons), provenance=prov)

    try:
        validate_provenance(prov)
    except ValueError as exc:
        return CheckResult(
            "invalid", (DriftReason(PROVENANCE_INVALID, str(exc)),), provenance=prov
        )

    reasons: list[DriftReason] = []

    # Producer identity (version + output-affecting tools + mode).
    recorded_producer = prov.get("producer", {})
    if recorded_producer.get("producer_version") != PRODUCER_VERSION:
        reasons.append(
            DriftReason(
                PRODUCER_IDENTITY_MISMATCH,
                f"producer_version {recorded_producer.get('producer_version')!r} "
                f"!= current {PRODUCER_VERSION!r}",
            )
        )
    current_tools = optional_tools if optional_tools is not None else detect_optional_tools()
    if prov.get("optional_tools") != current_tools:
        reasons.append(
            DriftReason(PRODUCER_IDENTITY_MISMATCH, "optional-tool identity changed")
        )
    if prov.get("mode") != mode:
        reasons.append(
            DriftReason(
                PRODUCER_IDENTITY_MISMATCH,
                f"recorded mode {prov.get('mode')!r} != requested {mode!r}",
            )
        )

    # Relevant input fingerprint (uses the recorded roots so added/removed/renamed
    # files within them change the fingerprint).
    recorded_roots = list(prov.get("input_roots", []))
    current_fp, current_enumeration = compute_input_fingerprint(repo_root, recorded_roots)
    recorded_enumeration = prov.get("input_enumeration")
    if recorded_enumeration != current_enumeration:
        # Reported as identity, not as a fingerprint mismatch: two strategies see
        # different file sets, so their fingerprints are not comparable and
        # "the inputs changed" would be the wrong thing to tell a reader.
        reasons.append(
            DriftReason(
                PRODUCER_IDENTITY_MISMATCH,
                f"input enumeration {recorded_enumeration!r} != current "
                f"{current_enumeration!r}",
            )
        )
    elif current_fp != prov.get("input_fingerprint"):
        reasons.append(
            DriftReason(
                INPUT_FINGERPRINT_MISMATCH,
                "relevant input bytes/paths changed since the recorded refresh",
            )
        )

    # Owned artifacts. The tier decides what absence means; presence is judged
    # identically for both tiers, so a local cache that IS on disk with the wrong
    # bytes is reported rather than trusted.
    for art in prov.get("artifacts", []):
        rel = art.get("path")
        target = repo_root / rel
        if not target.is_file():
            if art.get("tier") == TIER_COMMITTED:
                reasons.append(
                    DriftReason(
                        ARTIFACT_MISSING, "recorded artifact is missing", path=rel
                    )
                )
            # A local-cache artifact is expected to be absent in a clean
            # checkout: the pipeline generates it, the repository does not track
            # it. Reporting that as drift is what made untracking impossible.
            continue
        digest, _size = hash_file(target)
        if digest != art.get("sha256"):
            reasons.append(
                DriftReason(
                    ARTIFACT_DIGEST_MISMATCH,
                    "committed artifact bytes differ from recorded digest",
                    path=rel,
                )
            )

    status = "fresh" if not reasons else "stale"
    return CheckResult(status, tuple(reasons), provenance=prov)
