"""OpenSpec scenario seeding for gen-eval.

Parses ``openspec/changes/<id>/specs/**/*.md`` for ``### Requirement:`` and
nested ``#### Scenario:`` blocks (WHEN/THEN/AND structure) and produces
constraint sections injected into the cli-augmented prompt.

The flag ``--openspec-change <id>`` in ``__main__`` activates this path.
The change-id MUST match ``^[a-zA-Z0-9_-]+$`` — values failing this regex
are rejected at argparse time (status 64) BEFORE any filesystem walk, to
prevent path-traversal and shell-metacharacter injection.

Scenario body text is escaped before injection so a maliciously crafted
spec.md cannot inject prompt directives that change the structure of the
cli-augmented prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


CHANGE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Section delimiters used by render_constraints_section. These are part of
# the public prompt contract — see contracts/gen-eval-cli.md.
SECTION_HEADER = "# OpenSpec Scenarios (constraints)"
SECTION_FOOTER = "# End OpenSpec Scenarios"

# Regex matching a markdown header line (1-6 hashes followed by a space).
# Used by escape_scenario_body to neutralize header markers in body text.
_HEADER_LINE_RE = re.compile(r"^(#{1,6}) ")

_REQUIREMENT_HEADING_RE = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
_SCENARIO_HEADING_RE = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$")
# Any other heading (#, ##, ### non-Requirement, ##### or deeper, etc.)
# closes an in-progress scenario.
_HEADING_RE = re.compile(r"^#{1,6}\s+\S")


class InvalidChangeIdError(ValueError):
    """Raised when a change-id fails the validation regex.

    The argparse layer translates this to exit status 64 (usage error).
    """


@dataclass
class ParsedScenario:
    """A scenario parsed from an OpenSpec change spec.md.

    Attributes:
        requirement_name: The text after ``### Requirement:`` for the
            enclosing requirement block.
        scenario_name: The text after ``#### Scenario:`` for this scenario.
        body: The lines of the scenario body (WHEN/THEN/AND bullets and
            any blank lines), joined with ``\\n``.
        source_file: Repo-relative POSIX path to the originating spec file,
            e.g. ``openspec/changes/foo/specs/api/spec.md``.
        line_start: 1-based line number of the ``#### Scenario:`` heading.
        line_end: 1-based line number of the last non-blank body line.
    """

    requirement_name: str
    scenario_name: str
    body: str
    source_file: str
    line_start: int
    line_end: int

    @property
    def source_ref(self) -> str:
        """Return ``<file>:<line-start>-<line-end>`` for source.openspec_scenario."""
        return f"{self.source_file}:{self.line_start}-{self.line_end}"


def validate_change_id(value: str) -> str:
    """argparse ``type=`` validator for ``--openspec-change``.

    Raises:
        InvalidChangeIdError: If ``value`` does not match ``^[a-zA-Z0-9_-]+$``.
            The message names the regex constraint so operators can correct
            their input.
    """
    if not isinstance(value, str) or not CHANGE_ID_RE.match(value):
        raise InvalidChangeIdError(
            f"change-id MUST match {CHANGE_ID_RE.pattern}: got {value!r}"
        )
    return value


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    """Return ``path`` as a POSIX string relative to ``repo_root`` if possible.

    Falls back to the absolute POSIX path when ``path`` is outside the root,
    which only happens in tests that pass synthetic absolute paths.
    """
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_spec_file(spec_path: Path, repo_root: Path) -> list[ParsedScenario]:
    """Parse one spec.md file. Logs and returns ``[]`` on read errors."""
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("openspec_seed: cannot read %s: %s", spec_path, exc)
        return []

    rel = _relative_to_repo(spec_path, repo_root)
    lines = text.splitlines()
    out: list[ParsedScenario] = []

    current_requirement: str | None = None
    in_scenario = False
    scenario_name = ""
    scenario_start = 0
    body_lines: list[str] = []
    last_content_line = 0  # 1-based; tracks last non-blank body line

    def flush() -> None:
        nonlocal in_scenario, scenario_name, scenario_start, body_lines, last_content_line
        if in_scenario and current_requirement is not None:
            line_end = last_content_line if last_content_line >= scenario_start else scenario_start
            out.append(
                ParsedScenario(
                    requirement_name=current_requirement,
                    scenario_name=scenario_name,
                    body="\n".join(body_lines).rstrip(),
                    source_file=rel,
                    line_start=scenario_start,
                    line_end=line_end,
                )
            )
        in_scenario = False
        scenario_name = ""
        scenario_start = 0
        body_lines = []
        last_content_line = 0

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r")

        req_match = _REQUIREMENT_HEADING_RE.match(line)
        if req_match:
            flush()
            current_requirement = req_match.group(1).strip()
            continue

        scn_match = _SCENARIO_HEADING_RE.match(line)
        if scn_match:
            flush()
            if current_requirement is None:
                # Scenario without an enclosing requirement — skip with warning.
                logger.warning(
                    "openspec_seed: %s:%d scenario %r has no enclosing Requirement; skipping",
                    rel,
                    idx,
                    scn_match.group(1).strip(),
                )
                continue
            in_scenario = True
            scenario_name = scn_match.group(1).strip()
            scenario_start = idx
            body_lines = []
            last_content_line = idx
            continue

        # Any other heading closes the current scenario.
        if _HEADING_RE.match(line):
            flush()
            continue

        if in_scenario:
            body_lines.append(line)
            if line.strip():
                last_content_line = idx

    flush()
    return out


def parse_openspec_change(
    change_dir: Path,
    repo_root: Path | None = None,
) -> list[ParsedScenario]:
    """Walk ``change_dir/specs/**/*.md`` and parse Requirement+Scenario blocks.

    Args:
        change_dir: Path to ``openspec/changes/<id>/``.
        repo_root: Path against which to compute relative source_file values.
            Defaults to the current working directory; tests can override.

    Returns:
        A list of ParsedScenario objects in deterministic order (sorted by
        path then line). Returns ``[]`` if ``change_dir`` or ``specs/`` is
        missing — the caller is expected to log the warning naming the
        missing path so the message can include CLI context.
    """
    if repo_root is None:
        repo_root = Path.cwd()

    if not change_dir.exists():
        return []
    specs_dir = change_dir / "specs"
    if not specs_dir.exists() or not specs_dir.is_dir():
        return []

    # Resolve specs_dir once so we can reject any spec file whose resolved
    # path escapes the specs subtree (defense against symlink attacks where
    # a malicious checkout contains specs/foo.md → /etc/passwd).
    specs_dir_resolved = specs_dir.resolve()

    spec_files = sorted(specs_dir.rglob("*.md"))
    parsed: list[ParsedScenario] = []
    for spec_file in spec_files:
        if not spec_file.is_file():
            continue
        try:
            spec_resolved = spec_file.resolve()
        except OSError as exc:
            logger.warning(
                "skipping spec file with broken resolution: %s (%s)",
                spec_file,
                exc,
            )
            continue
        try:
            spec_resolved.relative_to(specs_dir_resolved)
        except ValueError:
            logger.warning(
                "skipping spec file that resolves outside specs/ subtree: %s "
                "(resolves to %s; possible symlink escape)",
                spec_file,
                spec_resolved,
            )
            continue
        parsed.extend(_parse_spec_file(spec_file, repo_root))
    return parsed


def escape_scenario_body(body: str) -> str:
    """Escape header lines and the section terminator in scenario body text.

    Rules (from contracts/gen-eval-cli.md):

    - Lines beginning with 1-6 ``#`` characters followed by a space are
      prefixed with a backslash so the prompt parser does not interpret
      them as headers.
    - The exact string ``# End OpenSpec Scenarios`` (the section terminator)
      is escaped if it appears anywhere in the body (it is also caught by
      the header-line rule, but we belt-and-suspenders the literal string).
    - Triple-backtick code fences are preserved as-is in the body; the
      caller (``render_constraints_section``) wraps the body in a
      quadruple-backtick fence so embedded triples cannot terminate it.

    Non-header content is returned unchanged.
    """
    out_lines: list[str] = []
    for line in body.splitlines():
        if _HEADER_LINE_RE.match(line):
            out_lines.append("\\" + line)
        else:
            out_lines.append(line)
    escaped = "\n".join(out_lines)
    # Belt-and-suspenders: escape any literal section terminator that
    # didn't have a trailing space (the header regex requires "# " + text,
    # which matches "# End OpenSpec Scenarios" already, but we guard
    # against bare-line variants too).
    if SECTION_FOOTER in escaped and ("\\" + SECTION_FOOTER) not in escaped:
        escaped = escaped.replace(SECTION_FOOTER, "\\" + SECTION_FOOTER)
    return escaped


def render_constraints_section(scenarios: list[ParsedScenario]) -> str:
    """Build the ``# OpenSpec Scenarios (constraints)`` prompt section.

    The output starts with the ``SECTION_HEADER`` line, contains one
    block per ParsedScenario preceded by a ``## Scenario: <name>
    [source: <file>:<start>-<end>]`` header, and ends with the
    ``SECTION_FOOTER`` line. Body text is escaped via
    :func:`escape_scenario_body` and wrapped in a quadruple-backtick
    fence so any triple-backtick fences in the body cannot terminate
    the wrapping fence.
    """
    parts: list[str] = [SECTION_HEADER, ""]
    for scn in scenarios:
        header = (
            f"## Scenario: {scn.scenario_name} "
            f"[source: {scn.source_ref}]"
        )
        parts.append(header)
        parts.append(f"Requirement: {scn.requirement_name}")
        parts.append("````")
        parts.append(escape_scenario_body(scn.body))
        parts.append("````")
        parts.append("")
    parts.append(SECTION_FOOTER)
    return "\n".join(parts)


__all__ = [
    "CHANGE_ID_RE",
    "InvalidChangeIdError",
    "ParsedScenario",
    "SECTION_FOOTER",
    "SECTION_HEADER",
    "escape_scenario_body",
    "parse_openspec_change",
    "render_constraints_section",
    "validate_change_id",
]
