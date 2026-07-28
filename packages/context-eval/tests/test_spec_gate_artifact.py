"""The artifact the `code-search` Retrieval Quality Gate names is durable and machine-read.

The requirement this file guards used to be unsatisfiable in place. It demanded
`eval/spike-report.md` exist "in the change directory" with "an explicit pass
verdict"; archival moved that directory, and the report it pointed at records
`BLOCKED (environment) -> WAIVED (operator decision)`. Its automated form was
`sys.exit(0 if ('Verdict' in t and 'hit@5' in t) else 1)` — a substring test the
waived report passes, over a markdown file no schema can read. Design decision
D13 reconciles the requirement; this file is the executable half of that.

**Why this test does not simply require a passing report to exist.**
`docs/evaluation/semantic-context/report.json` is deliberately absent right now,
and absent is the fail-closed default state (design D11). The measurement phase
may legitimately produce a *failing* report. A test that demanded presence, or
demanded `pass`, would be a test that pressures the measurement — which is the
exact failure this whole change exists to correct. So the assertions here are
chosen to be total over the three states the durable path can be in, and to say
something true and load-bearing in each:

- **No report** (the state today). The path is resolvable, durable, outside every
  change directory, and named by every consumer that sends a reader to it.
  Absence is readable *as* absence: `check` refuses to exit `0`, so nothing can
  mistake "not measured" for "measured and fine" — which is exactly what the
  waiver did.
- **A FAIL report.** It is schema-valid, its verdict is drawn from the closed
  two-member enum, it carries at least one explicit reason, and `check` exits
  non-zero. A blocked or waived outcome has no representation other than this.
- **A PASS report.** It is schema-valid, its verdict is `pass`, it carries no
  fail reasons, and `check` exits `0`.

The state machine is total: exactly one branch runs, each branch asserts, and no
branch can be satisfied by a document that is unreadable, waived, or parked
inside a directory archival will move. That is the property the requirement
actually needs, and it is the property the substring check never had.

`test_the_durability_predicate_rejects_the_requirement_it_replaced` is the
positive control. The reconciliation landed before this file did, so the
predicate below is green on this tree; a predicate nobody has watched reject
anything is decoration, so it is run against a verbatim copy of the requirement
as it read before the reconciliation and asserted to reject it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "packages" / "context-eval" / "src"

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval import report as report_module  # noqa: E402
from context_eval.__main__ import EXIT_PASS, main  # noqa: E402

#: The durable home. Outside every change directory, by construction: this is
#: the whole of design decision D1 expressed as a path.
DURABLE_REPORT = REPO_ROOT / "docs" / "evaluation" / "semantic-context" / "report.json"
DURABLE_REPORT_PATH = "docs/evaluation/semantic-context/report.json"

LIVE_SPEC = REPO_ROOT / "openspec" / "specs" / "code-search" / "spec.md"
ACTIVE_CHANGES = REPO_ROOT / "openspec" / "changes"
REQUIREMENT_NAME = "Retrieval Quality Gate"

REPORT_SCHEMA = (
    REPO_ROOT
    / "openspec"
    / "contracts"
    / "semantic-context-evaluation"
    / "schemas"
    / "context-eval-report.schema.json"
)

#: The artifact the requirement used to name, kept for its history and asserted
#: below to be exactly what the replaced check could not read.
SUPERSEDED_REPORT = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "archive"
    / "2026-07-20-add-semantic-code-search"
    / "eval"
    / "spike-report.md"
)

#: Everything a consumer of this requirement may name as the gate's artifact
#: must be reachable forever. These three markers are the ways the previous
#: version was not.
NON_DURABLE_MARKERS = (
    "openspec/changes/",
    "spike-report.md",
    "in the change directory",
)

#: The documents that send a reader somewhere else to find the gate's evidence.
#: Each must send them to the durable path — the requirement's own scenario says
#: no consumer of it may reference a path inside a change directory. The
#: evaluation README is not in this list because it *is* the durable home and
#: names the report relative to itself; that it exists there is asserted
#: separately.
CONSUMERS = (
    REPO_ROOT / "docs" / "guides" / "code-search.md",
    REPO_ROOT / "docs" / "guides" / "semantic-context-injection.md",
)

#: The requirement as it read before design decision D13 reconciled it, copied
#: verbatim from `openspec/specs/code-search/spec.md` at `748af34c`. It exists
#: here only so the predicate that rejects it can be watched rejecting it.
PRE_RECONCILIATION_REQUIREMENT = """\
### Requirement: Retrieval Quality Gate

Adoption SHALL be gated on a recorded spike evaluation: at least 10 realistic retrieval tasks
with hand-labeled expected files, run against stock cocoindex-code on this repository, reporting
hit@5 and token cost against a ripgrep baseline. The gate passes only if hit@5 >= 7/10 including
at least 2 tasks the ripgrep baseline misses; a failing gate SHALL stop the change with a written
finding before any Postgres backend work proceeds.

#### Scenario: Gate report exists before backend implementation

- **WHEN** any task from the vendored-backend work packages starts
- **THEN** `eval/spike-report.md` SHALL exist in the change directory with per-task hit results
  and an explicit pass verdict
"""

#: The automated check this file replaces, from the archived work package.
ARCHIVED_SUBSTRING_CHECK = ("Verdict", "hit@5")


# --------------------------------------------------------------------------
# resolving the requirement, wherever it currently lives
# --------------------------------------------------------------------------


def _requirement_block(text: str, name: str) -> str | None:
    """The `### Requirement: <name>` section, up to the next heading of any rank."""
    lines = text.splitlines()
    heading = f"### Requirement: {name}"
    try:
        start = lines.index(heading)
    except ValueError:
        return None
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.startswith("### ") or line.startswith("## ") or line.startswith("# "):
            return "\n".join(lines[start:offset])
    return "\n".join(lines[start:])


def _effective_requirement() -> tuple[Path, str]:
    """Where the requirement is stated *now*, and what it says.

    An active change's delta supersedes the live spec: `openspec archive` rewrites
    the live document from the delta, so before archival the delta is the
    repository's decision and after archival the live spec is. Reading whichever
    one currently holds it keeps this test asserting the same property on both
    sides of the archive operation rather than passing on one side by accident.
    """
    for delta in sorted(ACTIVE_CHANGES.glob("*/specs/code-search/spec.md")):
        if "archive" in delta.parts:  # pragma: no cover - glob excludes it already
            continue
        block = _requirement_block(delta.read_text(encoding="utf-8"), REQUIREMENT_NAME)
        if block is not None:
            return delta, block
    block = _requirement_block(LIVE_SPEC.read_text(encoding="utf-8"), REQUIREMENT_NAME)
    assert block is not None, f"no `{REQUIREMENT_NAME}` requirement in {LIVE_SPEC}"
    return LIVE_SPEC, block


def _non_durable_references(text: str) -> list[str]:
    """Every way *text* points at an artifact a directory move would orphan."""
    return [marker for marker in NON_DURABLE_MARKERS if marker in text]


# --------------------------------------------------------------------------
# the requirement names a durable artifact
# --------------------------------------------------------------------------


def test_the_effective_requirement_names_no_artifact_inside_a_change_directory() -> None:
    source, block = _effective_requirement()
    found = _non_durable_references(block)
    assert not found, (
        f"{source.relative_to(REPO_ROOT)} still points the gate at {found}; "
        "archival moves change directories and every reference into one eventually 404s"
    )


def test_the_durability_predicate_rejects_the_requirement_it_replaced() -> None:
    """Positive control. A tripwire nobody proved can trip is decoration."""
    assert _non_durable_references(PRE_RECONCILIATION_REQUIREMENT)


def test_the_durable_artifact_path_is_outside_every_change_directory() -> None:
    relative = DURABLE_REPORT.relative_to(REPO_ROOT).as_posix()
    assert relative == DURABLE_REPORT_PATH
    assert not _non_durable_references(relative)
    assert DURABLE_REPORT.parent.is_dir(), (
        "the durable home is not committed; a path that does not exist cannot be "
        "the answer to 'where does the evidence live'"
    )
    assert (DURABLE_REPORT.parent / "README.md").is_file()


def test_every_consumer_of_the_requirement_names_the_durable_path() -> None:
    missing = [
        consumer.relative_to(REPO_ROOT).as_posix()
        for consumer in CONSUMERS
        if DURABLE_REPORT_PATH not in consumer.read_text(encoding="utf-8")
    ]
    assert not missing, f"these consumers do not name the durable report path: {missing}"


# --------------------------------------------------------------------------
# whatever is at the durable path carries a verdict from the closed enum
# --------------------------------------------------------------------------


def _verdict_enum() -> frozenset[str]:
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    return frozenset(schema["$defs"]["Verdict"]["enum"])


def test_the_durable_report_is_absent_or_carries_a_closed_enum_verdict() -> None:
    """Total over the three states the durable path can be in.

    Absent, failing and passing are each asserted, so this test says something
    true today and keeps saying something true on the day a report lands —
    without requiring that the report say anything in particular.
    """
    verdicts = _verdict_enum()
    assert verdicts == frozenset({"pass", "fail"}), (
        "the verdict vocabulary grew; a third value is a value automation "
        "eventually learns to accept"
    )

    if not DURABLE_REPORT.exists():
        # Absence is readable as absence. Nothing can mistake "not measured"
        # for "measured and fine", which is precisely what the waiver did.
        assert main(["check", "--report", str(DURABLE_REPORT)]) != EXIT_PASS
        return

    document = report_module.read_report(DURABLE_REPORT)
    report_module.validate_report(document)  # raises ReportError if it is not a report
    assert document["verdict"] in verdicts

    exit_code = main(["check", "--report", str(DURABLE_REPORT)])
    if document["verdict"] == "pass":
        assert not document.get("fail_reasons")
        assert exit_code == EXIT_PASS
    else:
        assert document.get("fail_reasons"), "a failing verdict must say why"
        assert exit_code != EXIT_PASS


# --------------------------------------------------------------------------
# the artifact this supersedes, and the check it would still pass
# --------------------------------------------------------------------------


def test_the_superseded_artifact_passes_the_check_it_replaced() -> None:
    """The waived report satisfies `'Verdict' in t and 'hit@5' in t`. That is the point."""
    if not SUPERSEDED_REPORT.is_file():  # pragma: no cover - history is committed
        pytest.skip("the archived spike report is not in this checkout")
    text = SUPERSEDED_REPORT.read_text(encoding="utf-8")
    assert all(token in text for token in ARCHIVED_SUBSTRING_CHECK), (
        "the replaced check no longer passes the report it was written for; "
        "this control no longer demonstrates anything"
    )
    assert re.search(r"WAIVED|BLOCKED|UNMEASURED", text), (
        "the superseded report no longer records the outcome this change exists to "
        "make unrepresentable"
    )


def test_no_closed_enum_verdict_can_be_read_from_the_superseded_artifact() -> None:
    """It is prose, not a document. No schema reads it, so no gate can.

    The words `PASS` and `FAIL` both appear in its verdict section, in a sentence
    saying neither could be produced. That is the difference between a substring
    and a verdict, and it is why the replacement reads a closed enum out of a
    schema-validated document instead of grepping markdown.
    """
    if not SUPERSEDED_REPORT.is_file():  # pragma: no cover - history is committed
        pytest.skip("the archived spike report is not in this checkout")
    with pytest.raises(report_module.ReportError):
        report_module.read_report(SUPERSEDED_REPORT)
