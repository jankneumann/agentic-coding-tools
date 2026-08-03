"""The artifact the `code-search` Retrieval Quality Gate names is durable and machine-read.

The requirement this file guards used to be unsatisfiable in place. It demanded
`eval/spike-report.md` exist "in the change directory" with "an explicit pass
verdict"; archival moved that directory, and the report it pointed at records
`BLOCKED (environment) -> WAIVED (operator decision)`. Its automated form was
`sys.exit(0 if ('Verdict' in t and 'hit@5' in t) else 1)` — a substring test the
waived report passes, over a markdown file no schema can read. Design decision
D13 reconciles the requirement; this file is the executable half of that.

**Why this test does not simply require a passing report to exist.**
`docs/evaluation/semantic-context/report.json` records `verdict: "fail"`, and a
failing report is a correct and complete outcome (design D11). The measurement
phase may legitimately produce one, and a test that demanded `pass` — or that
demanded presence, on a tree where nothing had been measured — would be a test
that pressures the measurement, which is the exact failure this whole change
exists to correct. So the assertions here are chosen to be total over the three
states the durable path can be in, and to say something true and load-bearing in
each:

- **No report.** The path is resolvable, durable, outside every change directory,
  and named by every consumer that sends a reader to it. Absence is readable *as*
  absence: `check` refuses to exit `0`, so nothing can mistake "not measured" for
  "measured and fine" — which is exactly what the waiver did.
- **A FAIL report** (the state today). It is schema-valid, its verdict is drawn
  from the closed two-member enum, it carries at least one explicit reason, and
  `check` exits non-zero. A blocked or waived outcome has no representation other
  than this. The default is off for THIS reason — the evidence says no — and not
  because no evidence exists; the two are different facts, and the whole of this
  change is about not collapsing them.
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


DURABLE_README = REPO_ROOT / "docs" / "evaluation" / "semantic-context" / "README.md"

#: Values the published prose restates from `report.json`. Each is (json path,
#: how the README abbreviates it). A restated fact is a second copy of a derived
#: value, and a second copy is the thing that goes stale.
_RESTATED = (
    (("harness", "fingerprint"), 8),
    (("harness", "corpus_digest"), 64),
    (("repository", "evaluated_revision"), 40),
)


def test_the_published_evidence_prose_matches_the_report() -> None:
    """The README's quoted provenance is the report's, or this fails.

    `2864bbfc` moved `harness.fingerprint`, updated `report.json`, edited this
    README, and left one sentence restating the OLD digest. Four multi-vendor
    review rounds, a validation pass, and the author all missed it, because every
    one of them checked that the report's fingerprint equalled the source digest
    and nobody checked that the README's restatement equalled the report.

    That is this capability's own subject — a derived value copied into prose,
    where the copy is maintained by hand and agrees with the original only until
    it doesn't. `harness.version` was the same defect one layer down (#337) and
    was fixed by deriving it; prose cannot be derived, so it is pinned instead.

    Abbreviations are honoured: the README writes a fingerprint as its first
    eight hex characters followed by an ellipsis, so a prefix match is what the
    document actually claims.
    """
    if not DURABLE_README.is_file():  # pragma: no cover - the artifact is committed
        pytest.skip("no durable README in this checkout")
    if not DURABLE_REPORT.is_file():  # pragma: no cover - the artifact is committed
        pytest.skip("no durable report in this checkout")

    prose = DURABLE_README.read_text(encoding="utf-8")
    document = json.loads(DURABLE_REPORT.read_text(encoding="utf-8"))

    for path, width in _RESTATED:
        value = document
        for key in path:
            value = value[key]
        assert isinstance(value, str)
        abbreviated = value[:width]
        assert abbreviated in prose, (
            f"{'.'.join(path)} is {value!r} in report.json, and the README quotes "
            f"no value beginning {abbreviated!r}. The published evidence and the "
            "artifact it describes disagree about what produced the measurement."
        )


def test_the_readme_quotes_no_provenance_the_report_disowns() -> None:
    """The other direction: no stale digest may survive anywhere in the prose.

    The test above would pass if someone ADDED the current fingerprint while
    leaving the old one further down — the exact shape of the defect, since
    `2864bbfc` did update part of this file and miss one sentence.

    Scoped to hex runs introduced as `digest` or `fingerprint`, not to every hex
    run. The README legitimately cites commit SHAs (`ddc30be2`, `2864bbfc`)
    which the report does not record and must not be flagged. A first draft of
    this test matched any 16+ character run instead, and PASSED against the
    broken README — the stale value was abbreviated to eight characters and slid
    underneath the threshold. A backstop that misses the defect it was written
    for is worse than no backstop, because it reads as coverage.
    """
    if not DURABLE_README.is_file():  # pragma: no cover - the artifact is committed
        pytest.skip("no durable README in this checkout")
    if not DURABLE_REPORT.is_file():  # pragma: no cover - the artifact is committed
        pytest.skip("no durable report in this checkout")

    document = json.loads(DURABLE_REPORT.read_text(encoding="utf-8"))
    recorded = {
        str(document["harness"]["fingerprint"]),
        str(document["harness"]["corpus_digest"]),
        str(document["repository"]["evaluated_revision"]),
    }
    quoted = set(
        re.findall(
            r"(?:digest|fingerprint)[^`\n]*`([0-9a-f]{8,})…?`",
            DURABLE_README.read_text(encoding="utf-8"),
        )
    )

    orphans = {q for q in quoted if not any(known.startswith(q) for known in recorded)}
    assert not orphans, (
        f"the README quotes provenance the report does not record: {sorted(orphans)!r}. "
        "A stale digest left in the prose is indistinguishable, to a reader, from "
        "the value that actually produced the measurement."
    )
