"""``report.render_report`` (design D13; spec requirement "Pilot Report With Open Decisions").

Spec scenarios: test-oracle-audit.53 (Report states its advisory status), .54 (Degraded stages are
visible), .55 (Open decisions are recorded).

API assumed:

``render_report(analysis: dict, *, boundaries: Mapping[str, str] | None = None) -> str``

* ``analysis`` is a document valid against ``analysis-report.schema.json`` (as produced by
  ``analysis.analyze``); the optional ``boundaries`` maps node id to the test's judged top
  ``boundary`` label, printed beside each listed disagreement;
* the result is Markdown whose FIRST LINE says the report is advisory and not a gate;
* tables are Markdown rows (one line per approach / metric), so line-oriented assertions apply;
* the "Open decisions" section is a Markdown heading containing "Open decisions"; the section runs to
  the next heading of the same or a higher level.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "analysis"))

import analysis_builders as b
from test_oracle_audit.analysis import analyze
from test_oracle_audit.report import render_report


def section(text: str, title: str) -> str:
    """Body of the Markdown section whose heading contains ``title`` (case-insensitive)."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(r"#{1,6}\s", line) and title.lower() in line.lower()),
        None,
    )
    assert start is not None, f"no heading containing {title!r}"
    level = len(re.match(r"(#+)", lines[start]).group(1))
    body = []
    for line in lines[start + 1 :]:
        m = re.match(r"(#+)\s", line)
        if m and len(m.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def lines_with(text: str, *needles: str) -> list[str]:
    return [ln for ln in text.splitlines() if all(n.lower() in ln.lower() for n in needles)]


def real_analysis():
    joined, labels = b.mixed_suite(40)
    return analyze(joined, labels, seed=0, suites=[b.SUITE])


@pytest.fixture(params=["hand_built", "from_analyze"])
def doc(request):
    return b.make_analysis_doc() if request.param == "hand_built" else real_analysis()


def test_hand_built_fixture_document_is_schema_valid(schema_validator):
    """Contract analysis-report.schema.json: the fixture the report tests render is itself a valid document."""
    schema_validator(b.make_analysis_doc(), "analysis-report")


# --- advisory first line (.53) --------------------------------------------


def test_first_line_declares_the_report_advisory_and_not_a_gate(doc):
    """Scenario test-oracle-audit.53: the first line declares the report advisory and not a gate."""
    first = render_report(doc).splitlines()[0].lower()
    assert "advisory" in first
    assert "not a gate" in first


def test_rendering_is_deterministic_and_does_not_mutate_the_analysis():
    """Scenario test-oracle-audit.53 / requirement text ("rendering SHALL NOT change" inputs)."""
    import copy

    analysis = b.make_analysis_doc()
    snapshot = copy.deepcopy(analysis)
    assert render_report(analysis) == render_report(analysis)
    assert analysis == snapshot


# --- degraded stages (.54) ------------------------------------------------


def test_judged_dry_run_is_shown_as_not_run_with_its_degraded_count():
    """Scenario test-oracle-audit.54: judged ran in dry-run (7 degraded, 0 ok) -> shown as ``not run``, not omitted."""
    text = render_report(b.make_analysis_doc())
    rows = lines_with(text, "judged", "not run")
    assert rows, "the judged approach is missing or not marked 'not run'"
    assert any("7" in row for row in rows)


def test_history_degraded_everywhere_is_also_not_run():
    """Scenario test-oracle-audit.54: a second degraded approach (history, 50 degraded) is visible the same way."""
    rows = lines_with(render_report(b.make_analysis_doc()), "history", "not run")
    assert rows and any("50" in row for row in rows)


def test_approaches_that_ran_are_not_marked_not_run_and_show_their_counts():
    """Scenario test-oracle-audit.54 (converse): static (52 ok) and mutation (31 ok, 13 insufficient) show counts."""
    text = render_report(b.make_analysis_doc())
    static_rows = lines_with(text, "static", "52")
    assert static_rows and not any("not run" in row.lower() for row in static_rows)
    mutation_rows = lines_with(text, "mutation", "31", "13")
    assert mutation_rows and not any("not run" in row.lower() for row in mutation_rows)


def test_every_measured_approach_appears_in_the_coverage_table(doc):
    """Scenario test-oracle-audit.54: no measured approach is omitted from the report."""
    text = render_report(doc).lower()
    for approach in ("static", "judged", "mutation", "rename", "history"):
        assert approach in text


# --- open decisions (.55) --------------------------------------------------


def test_open_decisions_section_lists_the_coverage_ratchet_options(doc):
    """Scenario test-oracle-audit.55: keep, deletion manifest and mutation-score ratchet are all listed."""
    body = section(render_report(doc), "Open decisions").lower()
    assert "keep" in body
    assert "deletion manifest" in body
    assert "mutation-score ratchet" in body
    assert "coverage" in body


def test_open_decisions_section_records_the_in_file_marker_question(doc):
    """Scenario test-oracle-audit.55: whether oracle-source labels become in-file pytest markers, plus --strict-markers."""
    body = section(render_report(doc), "Open decisions").lower()
    assert "marker" in body
    assert "in-file" in body
    assert "--strict-markers" in body


def test_open_decisions_come_after_the_analysis_not_instead_of_it():
    """Scenario test-oracle-audit.55 / requirement: the section is one part of a report that also has analysis content."""
    text = render_report(b.make_analysis_doc())
    assert "kappa_binary" in text
    assert text.lower().index("open decisions") > text.index("kappa_binary")


# --- required content -----------------------------------------------------


def test_metric_rows_show_n_value_and_interval_and_insufficient_cells_show_no_number():
    """Requirement "analysis tables"; scenario test-oracle-audit.43 as rendered.

    kappa_binary: n=40, value 0.55, CI [0.31, 0.79]. kappa_7: n=12, insufficient, no value.
    """
    text = render_report(b.make_analysis_doc())
    ok_rows = lines_with(text, "kappa_binary")
    assert any("40" in r and "0.55" in r and "0.31" in r and "0.79" in r for r in ok_rows)
    insufficient_rows = lines_with(text, "kappa_7")
    assert insufficient_rows
    assert all("insufficient" in r.lower() and "12" in r for r in insufficient_rows)


def test_linter_candidates_and_excluded_lists_are_rendered_with_reasons():
    """Requirement "linter-candidate and excluded lists"; scenario test-oracle-audit.44 as rendered."""
    text = render_report(b.make_analysis_doc())
    candidates = lines_with(text, "private_import", "cliffs_delta")
    assert candidates, "linter candidate and its reason are missing"
    excluded = lines_with(text, "oracle_source", "0.7")
    assert excluded, "excluded question and its reason are missing"


def test_disagreement_classes_and_their_tests_are_listed():
    """Scenarios test-oracle-audit.47/.48 as rendered: every class name and every listed node id appears."""
    analysis = b.make_analysis_doc()
    text = render_report(analysis)
    for cls in analysis["disagreements"]:
        assert cls in text
    for ids in analysis["disagreements"].values():
        for node_id in ids:
            assert node_id in text


def test_each_listed_test_carries_its_judged_top_boundary_label_when_one_exists():
    """Requirement "each listed test carrying its judged top boundary label when one exists"."""
    analysis = b.make_analysis_doc()
    text = render_report(analysis, boundaries={b.nid(1): "service_api", b.nid(4): "module_api"})
    assert any("service_api" in ln and b.nid(1) in ln for ln in text.splitlines())
    assert any("module_api" in ln and b.nid(4) in ln for ln in text.splitlines())
    unlabelled = [ln for ln in lines_with(text, b.nid(2))]
    assert unlabelled and not any(
        label in ln for ln in unlabelled for label in ("pure_function", "module_api", "service_api", "ui", "mixed")
    )


def test_tercile_cutpoints_are_cited():
    """Design D1/D10: the report cites the same per-suite kill-rate cut-points that analysis.json stores."""
    text = render_report(b.make_analysis_doc())
    assert "0.25" in text and "0.75" in text


def test_provisional_thresholds_are_labelled_provisional():
    """Requirement "Derived thresholds SHALL be marked provisional" as rendered."""
    metric = {
        "subject": "co_change_ratio", "comparison": "human_label", "metric": "auc", "n": 24, "status": "ok",
        "value": 0.81, "ci95": [0.62, 0.95], "threshold": 0.43, "provisional": True,
    }
    text = render_report(b.make_analysis_doc(metrics=[metric]))
    rows = lines_with(text, "co_change_ratio", "auc")
    assert rows and any("0.43" in r and "provisional" in r.lower() for r in rows)
