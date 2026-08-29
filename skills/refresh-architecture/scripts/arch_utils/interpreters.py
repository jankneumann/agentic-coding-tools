"""Resolve the interpreter that runs the optional tree-sitter stages (issue #378).

This module is the single source of truth for "which tree-sitter grammars are
available, and which Python has them". Before it existed there were two answers:

* ``refresh_architecture.sh`` probed ``${SCRIPTS_DIR}/.venv/bin/python`` — a
  per-skill venv that does not exist in this repository and that nothing
  creates — and required both ``tree_sitter`` and ``tree_sitter_sql``; while
* :func:`provenance.detect_optional_tools` imported ``tree_sitter`` in whatever
  process happened to be running provenance, and never checked
  ``tree_sitter_sql``.

The generated artifacts follow the first answer and the recorded provenance
follows the second, so a refresh could skip the enrichment, comment-linker and
pattern-reporter stages while stamping ``tree-sitter available: true``. Both
callers now ask this module, so they cannot disagree.

Resolution is *per grammar*. Requiring ``tree_sitter_sql`` for every stage made
one absent grammar disable ``treesitter_enrichment``, ``comment_linker`` and
``pattern_reporter`` as well — three stages that never parse SQL. Each stage now
declares what it imports (:data:`STAGE_REQUIREMENTS`) and runs when its own
grammars resolve, while provenance records availability per grammar. The
invariant that one resolver serves both callers is unchanged; it now holds at
grammar granularity instead of as a single boolean.

Resolution deliberately ends at a *project root* venv. Per repository
convention a virtualenv belongs to a project (``skills/``, the repo root), never
nested inside an individual skill directory.

Run as a script it prints the resolved interpreter and exits 0, or exits 1 when
tree-sitter is unavailable. ``--json`` and ``--shell`` emit the full resolution
map; ``--shell`` is the form the pipeline evals.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Every grammar whose presence changes what the pipeline produces. Reported
#: individually because they are installed individually: a consumer that vendors
#: the Python and TypeScript grammars but not the SQL one is a normal state, not
#: a broken install.
GRAMMAR_MODULES: tuple[str, ...] = (
    "tree_sitter",
    "tree_sitter_python",
    "tree_sitter_sql",
    "tree_sitter_typescript",
)

#: What each tree-sitter stage imports, and therefore what it requires.
#:
#: This replaces ``REQUIRED_MODULES``, which asked one question for the whole
#: pipeline and answered it with the union of every stage's needs. The entries
#: mirror the import blocks of the scripts themselves:
#:
#: * ``analyze_sql_treesitter.py`` imports ``tree_sitter`` and ``tree_sitter_sql``.
#: * ``enrich_with_treesitter.py`` imports ``tree_sitter``, ``tree_sitter_python``
#:   and ``tree_sitter_typescript`` in one block and exits 1 if any is missing,
#:   so both language grammars are genuinely required — under-declaring them
#:   here would let the pipeline start a stage that cannot run.
#: * ``comment_linker.py`` and ``pattern_reporter.py`` import no grammar at all;
#:   they read ``treesitter_enrichment.json``. They carry the enrichment stage's
#:   requirements because that artifact is only trustworthy when this run could
#:   have produced it — a stale file from an earlier refresh is not evidence.
STAGE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "treesitter_sql": ("tree_sitter", "tree_sitter_sql"),
    "treesitter_enrichment": (
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_typescript",
    ),
    "comment_linker": (
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_typescript",
    ),
    "pattern_reporter": (
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_typescript",
    ),
}

#: The core runtime. Without it no stage can run and no interpreter is resolved.
CORE_MODULE = "tree_sitter"

#: Explicit override, checked first, for callers that must pin the interpreter.
OVERRIDE_ENV = "ARCH_TREESITTER_PYTHON"

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def tool_name(module: str) -> str:
    """Return the distribution name provenance records for *module*."""
    return module.replace("_", "-")


def candidate_pythons(scripts_dir: Path | None = None) -> list[Path]:
    """Return interpreters to try, most specific first.

    The current interpreter comes early because the Makefile already resolves
    ``PYTHON`` to ``skills/.venv`` when it exists; honoring it keeps `make` and
    the shell pipeline on one interpreter instead of two.
    """
    scripts = Path(scripts_dir) if scripts_dir is not None else _SCRIPTS_DIR
    candidates: list[Path] = []

    override = os.environ.get(OVERRIDE_ENV)
    if override:
        candidates.append(Path(override))

    candidates.append(Path(sys.executable))

    # scripts/ -> <skill>/ -> skills/ -> <repo root>. Project-root venvs only.
    for ancestor in (scripts.parents[1], scripts.parents[2]):
        candidates.append(ancestor / ".venv" / "bin" / "python")

    which = shutil.which("python3")
    if which:
        candidates.append(Path(which))

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


@dataclass(frozen=True)
class GrammarResolution:
    """Which grammars a chosen interpreter can import, and what that enables.

    ``python is None`` means no candidate can import :data:`CORE_MODULE`; every
    grammar is then unavailable and every stage is skipped.
    """

    python: Path | None
    available: dict[str, bool]
    versions: dict[str, str | None]

    def stage_available(self, stage: str) -> bool:
        """Return whether every grammar *stage* imports is available."""
        required = STAGE_REQUIREMENTS.get(stage)
        if required is None:
            raise KeyError(f"unknown tree-sitter stage: {stage!r}")
        if self.python is None:
            return False
        return all(self.available.get(module, False) for module in required)

    def stages(self) -> dict[str, bool]:
        """Return the verdict for every declared stage, in declaration order."""
        return {stage: self.stage_available(stage) for stage in STAGE_REQUIREMENTS}

    def to_map(self) -> dict[str, object]:
        """Return the JSON map shared by the shell pipeline and provenance."""
        return {
            "python": str(self.python) if self.python is not None else None,
            "grammars": dict(self.available),
            "versions": dict(self.versions),
            "stages": self.stages(),
        }


def _unavailable(python: Path | None = None) -> GrammarResolution:
    return GrammarResolution(
        python=python,
        available={module: False for module in GRAMMAR_MODULES},
        versions={module: None for module in GRAMMAR_MODULES},
    )


#: Probes one interpreter for every grammar at once. Each import is attempted
#: separately so a partial install reports as partial rather than as nothing,
#: and a version is read only for a module that actually imported — distribution
#: metadata can outlive a broken or shadowed package.
_PROBE_SOURCE = """
import json
from importlib.metadata import PackageNotFoundError, version

available = {}
versions = {}
for name in %(modules)r:
    try:
        __import__(name)
    except Exception:
        available[name] = False
        versions[name] = None
        continue
    available[name] = True
    try:
        versions[name] = version(name.replace("_", "-"))
    except PackageNotFoundError:
        versions[name] = None
print(json.dumps({"available": available, "versions": versions}))
"""


def _probe(python: Path) -> tuple[dict[str, bool], dict[str, str | None]] | None:
    """Return per-grammar availability for *python*, or ``None`` if unusable."""
    if not (python.is_file() or shutil.which(str(python))):
        return None
    code = _PROBE_SOURCE % {"modules": list(GRAMMAR_MODULES)}
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return None
    available = {m: bool(payload["available"].get(m)) for m in GRAMMAR_MODULES}
    versions = {m: payload["versions"].get(m) for m in GRAMMAR_MODULES}
    return available, versions


def resolve_grammars(scripts_dir: Path | None = None) -> GrammarResolution:
    """Resolve one interpreter and report what each of its grammars enables.

    One interpreter runs every tree-sitter stage, so the resolver has to name
    one. Preference, in order:

    1. An explicit :data:`OVERRIDE_ENV` interpreter that can import the core
       module wins outright — pinning is the point of the override, and an
       override that cannot import the core still falls through rather than
       masking a working interpreter.
    2. Otherwise the first candidate that satisfies *every* stage, so a
       core-only interpreter early in the list does not starve stages a later
       one could run.
    3. Otherwise the first candidate that imports the core module, which runs
       whichever stages its grammars allow.
    """
    if os.environ.get("TREESITTER_ENABLED", "true") != "true":
        return _unavailable()

    override = os.environ.get(OVERRIDE_ENV)
    first_usable: GrammarResolution | None = None

    for candidate in candidate_pythons(scripts_dir):
        probed = _probe(candidate)
        if probed is None:
            continue
        available, versions = probed
        if not available[CORE_MODULE]:
            continue
        resolution = GrammarResolution(
            python=candidate, available=available, versions=versions
        )
        if override and str(candidate) == override:
            return resolution
        if all(resolution.stage_available(stage) for stage in STAGE_REQUIREMENTS):
            return resolution
        if first_usable is None:
            first_usable = resolution

    return first_usable if first_usable is not None else _unavailable()


def resolve_treesitter_python(scripts_dir: Path | None = None) -> Path | None:
    """Return the interpreter that runs the tree-sitter stages, or ``None``.

    ``None`` means no candidate can import :data:`CORE_MODULE`, and every caller
    must then agree that tree-sitter is unavailable. A returned interpreter does
    *not* imply every stage can run — ask :meth:`GrammarResolution.stage_available`
    for that.
    """
    return resolve_grammars(scripts_dir).python


def treesitter_version(python: Path) -> str | None:
    """Return the ``tree-sitter`` version *python* reports, or ``None``."""
    probed = _probe(Path(python))
    if probed is None:
        return None
    return probed[1].get(CORE_MODULE)


def _render_shell(resolution: GrammarResolution) -> str:
    """Render the resolution as assignments the pipeline can ``eval``.

    Bash 3 has no associative arrays (the pipeline still targets it), so stage
    verdicts are flat variables named after the stage.
    """
    python = str(resolution.python) if resolution.python is not None else ""
    lines = [f'TREESITTER_PYTHON="{python}"']
    for stage, ok in resolution.stages().items():
        lines.append(f'TREESITTER_STAGE_{stage}="{"true" if ok else "false"}"')
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Emit the resolution; exit 1 when tree-sitter is unavailable.

    The default output is the interpreter path, which is what the pipeline read
    before per-stage resolution existed and what a human running this by hand
    wants. ``--json`` and ``--shell`` carry the full map, and ``--stage NAME``
    answers for one stage through the exit code.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    resolution = resolve_grammars()

    if args and args[0] == "--stage":
        if len(args) < 2:
            print("--stage requires a stage name", file=sys.stderr)
            return 2
        try:
            ok = resolution.stage_available(args[1])
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if not ok:
            return 1
        print(str(resolution.python))
        return 0

    if args and args[0] == "--json":
        print(json.dumps(resolution.to_map(), indent=2, sort_keys=True))
        return 0 if resolution.python is not None else 1

    if args and args[0] == "--shell":
        sys.stdout.write(_render_shell(resolution))
        return 0 if resolution.python is not None else 1

    if args and args[0] not in ("--python",):
        print(f"unknown argument: {args[0]}", file=sys.stderr)
        return 2

    if resolution.python is None:
        return 1
    print(str(resolution.python))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
