"""Command-line entry point for the playwright-validator skill.

Usage::

    python -m playwright_validator <change-id> \
        [--descriptor PATH] [--output-dir PATH] [--specs-dir PATH]

Or, when invoked from the skill's installed location::

    python skills/playwright-validator/scripts/cli.py <change-id> ...

Behavior:

1. Validates ``<change-id>`` against ``^[a-zA-Z0-9_-]+$`` (mirrors
   gen-eval's openspec_seed regex; fail fast on shell-metacharacter
   injection attempts).
2. Loads the frontend descriptor (``--descriptor`` or auto-detected at
   ``evaluation/gen_eval/descriptors/<change-id>.yaml``).
3. Parses OpenSpec scenarios from
   ``openspec/changes/<change-id>/specs/**/*.md`` (or ``--specs-dir``).
4. Translates scenarios -> Playwright actions/assertions.
5. Emits a generated ``.spec.ts`` test file + minimal ``playwright.config.ts``.
6. Validates env-vars (fails fast with non-zero exit BEFORE any browser
   launch on missing var).
7. If ``--dry-run`` or Playwright CLI is missing, exits 127 and writes
   no findings file.
8. Runs ``npx playwright test --reporter=json`` per browser in matrix.
9. Emits ``findings-playwright.json`` to ``--output-dir`` (default:
   ``openspec/changes/<change-id>/``).

Exit codes:

* ``0``  — All scenarios passed (or ``--dry-run`` succeeded with no failures).
* ``1``  — One or more Playwright tests failed (findings file emitted).
* ``2``  — Pipeline error (missing descriptor, malformed YAML, missing env var).
* ``64`` — Invalid change-id (usage error).
* ``127`` — Playwright CLI not installed (no findings file emitted).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from auth_flow import MissingEnvVar
from descriptor import (
    DescriptorError,
    load_descriptor,
    normalize_descriptor,
)
from findings import emit_playwright_findings
from generator import emit_playwright_config, emit_test_script
from parser import translate_openspec_scenario
from runner import EXIT_CLI_MISSING, run_playwright


CHANGE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "openspec").is_dir():
            return parent
    return Path.cwd()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playwright-validator",
        description=(
            "Drive a deployed frontend via Playwright using OpenSpec scenarios."
        ),
    )
    parser.add_argument(
        "change_id",
        help="OpenSpec change-id (e.g. 'sample-frontend-demo'). Must match ^[a-zA-Z0-9_-]+$.",
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=None,
        help="Path to frontend-descriptor YAML. "
        "Defaults to evaluation/gen_eval/descriptors/<change-id>.yaml.",
    )
    parser.add_argument(
        "--specs-dir",
        type=Path,
        default=None,
        help="Override OpenSpec specs directory. "
        "Defaults to openspec/changes/<change-id>/specs/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write findings-playwright.json. "
        "Defaults to openspec/changes/<change-id>/.",
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=None,
        help="Where to emit the generated .spec.ts files. "
        "Defaults to skills/playwright-validator/test-results/generated/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the test script but do not invoke npx playwright.",
    )
    parser.add_argument(
        "--browsers",
        nargs="+",
        default=None,
        help="Override the descriptor's browsers list.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser


def _load_scenarios(specs_dir: Path) -> list:
    """Parse OpenSpec scenarios from ``specs_dir``.

    Imports lazily from agent-coordinator so the rest of the validator (the
    pure-Python pieces) can be unit-tested even when agent-coordinator is
    not on the path.
    """
    repo_root = _repo_root()
    coord_path = repo_root / "agent-coordinator"
    if str(coord_path) not in sys.path:
        sys.path.insert(0, str(coord_path))
    try:
        from evaluation.gen_eval.openspec_seed import (  # type: ignore[import-not-found]
            parse_openspec_change,
        )
    except ImportError:
        # Fall back to a minimal in-tree parser that only recognizes the
        # subset we need. This keeps the skill usable even if agent-
        # coordinator imports fail.
        return _minimal_parse(specs_dir, repo_root)

    change_dir = specs_dir.parent
    return parse_openspec_change(change_dir, repo_root=repo_root)


def _minimal_parse(specs_dir: Path, repo_root: Path) -> list:
    """Tiny standalone fallback parser for OpenSpec WHEN/THEN scenarios.

    Used only when ``agent-coordinator/evaluation/gen_eval/openspec_seed.py``
    cannot be imported. Produces objects with the same duck-typed attributes
    that :func:`parser.translate_openspec_scenario` needs.
    """
    from dataclasses import dataclass

    @dataclass
    class _Scenario:
        scenario_name: str
        requirement_name: str
        body: str
        source_file: str
        line_start: int
        line_end: int

        @property
        def source_ref(self) -> str:
            return f"{self.source_file}:{self.line_start}-{self.line_end}"

    out: list[_Scenario] = []
    if not specs_dir.exists():
        return out
    for path in sorted(specs_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        current_req = ""
        in_scn = False
        scn_name = ""
        scn_start = 0
        body: list[str] = []
        last = 0

        def flush() -> None:
            nonlocal in_scn, scn_name, scn_start, body, last
            if in_scn and current_req:
                rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
                out.append(
                    _Scenario(
                        scenario_name=scn_name,
                        requirement_name=current_req,
                        body="\n".join(body).rstrip(),
                        source_file=rel,
                        line_start=scn_start,
                        line_end=last if last >= scn_start else scn_start,
                    )
                )
            in_scn = False
            scn_name = ""
            scn_start = 0
            body = []
            last = 0

        for i, line in enumerate(lines, start=1):
            if line.startswith("### Requirement:"):
                flush()
                current_req = line[len("### Requirement:") :].strip()
                continue
            if line.startswith("#### Scenario:"):
                flush()
                in_scn = True
                scn_name = line[len("#### Scenario:") :].strip()
                scn_start = i
                last = i
                body = []
                continue
            if line.startswith("#"):
                flush()
                continue
            if in_scn:
                body.append(line)
                if line.strip():
                    last = i
        flush()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("playwright-validator")

    if not CHANGE_ID_RE.match(args.change_id):
        logger.error(
            "change-id MUST match %s: got %r",
            CHANGE_ID_RE.pattern,
            args.change_id,
        )
        return 64

    repo_root = _repo_root()

    descriptor_path = args.descriptor or (
        repo_root
        / "evaluation"
        / "gen_eval"
        / "descriptors"
        / f"{args.change_id}.yaml"
    )
    specs_dir = args.specs_dir or (
        repo_root / "openspec" / "changes" / args.change_id / "specs"
    )
    output_dir = args.output_dir or (
        repo_root / "openspec" / "changes" / args.change_id
    )
    test_dir = args.test_dir or (
        repo_root
        / "skills"
        / "playwright-validator"
        / "test-results"
        / "generated"
        / args.change_id
    )

    if not descriptor_path.exists():
        logger.error("frontend descriptor not found: %s", descriptor_path)
        return 2

    try:
        descriptor = normalize_descriptor(load_descriptor(descriptor_path))
    except DescriptorError as exc:
        logger.error("descriptor error: %s", exc)
        return 2

    selectors = descriptor.get("selectors") or {}
    parsed = _load_scenarios(specs_dir) if specs_dir.exists() else []
    if not parsed:
        logger.warning(
            "no OpenSpec scenarios found at %s; emitting placeholder test only",
            specs_dir,
        )
    translated = [translate_openspec_scenario(s, selectors) for s in parsed]

    test_dir.mkdir(parents=True, exist_ok=True)
    emit_playwright_config(descriptor, test_dir)
    spec_path = test_dir / f"{args.change_id}.spec.ts"
    emit_test_script(translated, descriptor, spec_path)
    logger.info("emitted test script: %s", spec_path)

    if args.dry_run:
        logger.info("--dry-run: skipping npx playwright test")
        return 0

    try:
        result = run_playwright(
            test_dir, descriptor, browsers=args.browsers
        )
    except MissingEnvVar as exc:
        logger.error("%s", exc)
        return 2

    if result.exit_code == EXIT_CLI_MISSING:
        # Per spec: do NOT emit a findings file when the CLI is missing.
        return EXIT_CLI_MISSING

    findings_path = output_dir / "findings-playwright.json"
    emit_playwright_findings(
        failures=result.failures,
        scenarios=translated,
        output_path=findings_path,
        target=args.change_id,
    )
    logger.info(
        "emitted %d finding(s) to %s",
        len(result.failures),
        findings_path,
    )
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
