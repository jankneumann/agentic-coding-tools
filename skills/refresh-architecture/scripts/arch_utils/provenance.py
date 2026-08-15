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
from collections.abc import Mapping
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
PRODUCER_VERSION = "1.1.0"
PROVENANCE_SCHEMA_VERSION = 1

ARCH_DIR_DEFAULT = "docs/architecture-analysis"
PROVENANCE_FILENAME = "architecture.provenance.json"

#: Fallback deterministic epoch (2023-11-14T22:13:20Z) for repos without a
#: resolvable commit timestamp — keeps ad-hoc generation reproducible.
_FIXED_EPOCH = 1_700_000_000

#: Canonical owned artifacts under the architecture output directory. Only
#: those present are recorded; ``required`` ones missing make a refresh stale.
_OWNED_TOP_LEVEL: tuple[tuple[str, bool], ...] = (
    ("architecture.graph.json", True),
    ("architecture.summary.json", True),
    ("architecture.diagnostics.json", False),
    ("parallel_zones.json", False),
    ("architecture.report.md", False),
    ("python_analysis.json", False),
    ("ts_analysis.json", False),
    ("postgres_analysis.json", False),
    ("treesitter_enrichment.json", False),
    ("comment_insights.json", False),
    ("pattern_insights.json", False),
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
    """Identify output-affecting optional tools (tree-sitter SQL/enrichment)."""
    available = False
    version: str | None = None
    try:
        import tree_sitter  # type: ignore  # noqa: F401
        from importlib.metadata import PackageNotFoundError, version as _v

        available = True
        try:
            version = _v("tree-sitter")
        except PackageNotFoundError:  # pragma: no cover - installed-without-metadata
            version = None
    except Exception:
        available = False
        version = None
    return [{"name": "tree-sitter", "available": available, "version": version}]


# --------------------------------------------------------------------------- #
# Owned-artifact digests
# --------------------------------------------------------------------------- #
def hash_file(path: Path) -> tuple[str, int]:
    data = Path(path).read_bytes()
    return _sha256_hex(data), len(data)


def owned_artifacts(
    repo_root: Path | str, arch_dir: str = ARCH_DIR_DEFAULT
) -> list[dict[str, Any]]:
    """Return sorted digests for the owned architecture artifacts that exist."""
    repo_root = Path(repo_root)
    base = repo_root / arch_dir
    out: list[dict[str, Any]] = []
    for name, required in _OWNED_TOP_LEVEL:
        p = base / name
        if p.is_file():
            digest, size = hash_file(p)
            out.append(
                {
                    "path": f"{arch_dir}/{name}",
                    "sha256": digest,
                    "size_bytes": size,
                    "required": required,
                }
            )
    views = base / "views"
    if views.is_dir():
        for p in sorted(views.rglob("*")):
            if p.is_file():
                digest, size = hash_file(p)
                rel = p.relative_to(repo_root).as_posix()
                out.append(
                    {"path": rel, "sha256": digest, "size_bytes": size, "required": False}
                )
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
) -> dict[str, Any]:
    """Assemble a schema-valid architecture provenance document from disk state."""
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
        "artifacts": owned_artifacts(repo_root, arch_dir),
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
    committed provenance is schema-valid, the relevant input fingerprint and
    producer identity match, and every recorded artifact is present with a
    matching digest. Never uses mtime or elapsed wall-clock age.
    """
    repo_root = Path(repo_root)
    prov = load_provenance(repo_root, arch_dir)
    if prov is None:
        return CheckResult(
            "invalid",
            (DriftReason(PROVENANCE_MISSING, "no committed architecture provenance"),),
        )
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

    # Owned artifacts present with matching digests.
    for art in prov.get("artifacts", []):
        rel = art.get("path")
        target = repo_root / rel
        if not target.is_file():
            reasons.append(
                DriftReason(ARTIFACT_MISSING, "recorded artifact is missing", path=rel)
            )
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
