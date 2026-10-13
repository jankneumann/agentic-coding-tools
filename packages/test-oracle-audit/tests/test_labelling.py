"""``labelling``: stratified seeded sampling, blind cards and the non-interactive label flow (design D9).

Spec scenarios: test-oracle-audit.39 (Sample covers every non-empty stratum), .40 (Card hides other
approaches' outputs), .41 (Dry-run labelling writes no ledger entry); ledger scenarios .2 (stale on
change), .3 (whitespace-only edits keep a label), .4 (unknown label rejected) for ``record_label``.

API assumed (the tests define it):

* ``stratified_sample(entries, static_records, mutation_records, *, n=40, seed=0) -> list[TestEntry]``
  strata: any-static-flag (an ok static record with a non-empty ``rules`` list) x kill-rate tercile
  (``thresholds.tercile_cutpoints`` over every numeric kill rate in ``mutation_records``), plus one
  ``insufficient`` stratum (kill rate ``insufficient``, not split by flag): seven strata. Exactly ``n``
  distinct entries come back (when at least ``n`` exist), every non-empty stratum contributing at
  least one; same inputs and seed give the same list.
* ``render_card(entry, *, repo_root) -> str``: the test source, signatures and docstrings of the
  functions in ``entry.covered_modules`` (dotted module names resolved under ``repo_root``, bodies cut
  at 40 lines) and the text of a cited spec requirement (docstring names
  ``openspec/specs/<cap>/spec.md`` and ``Requirement: <title>``). It receives no stage records.
* ``label_next(entries, static_records, mutation_records, *, repo_root, out_dir, ledger_path,
  n=40, seed=0, dry_run=False) -> str | None``: the ``label next`` command. Draws the sample, or
  reloads the one stored in the ledger's ``sample`` field; writes every card to
  ``<out_dir>/cards/<index>-<slug>.md``; returns the card text of the first sampled test with no label
  in the ledger, or ``None`` when all are labelled. Non-dry-run persists the sample in the ledger.
  ``dry_run=True`` renders cards and never creates or modifies the ledger.
* ``record_label(node_id, label, *, repo_root, ledger_path, labeller, note=None) -> LabelEntry``: the
  ``label record`` command. Hashes the CURRENT test source under ``repo_root`` and appends one
  ledger entry (keeping any stored sample); an unknown label raises ``ValueError`` and writes nothing.

Nothing here prompts: ``builtins.input`` is replaced by a function that fails the test.
"""

from __future__ import annotations

import builtins
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "analysis"))

import analysis_builders as b
from test_oracle_audit.labelling import label_next, record_label, render_card, stratified_sample

from test_oracle_audit.ledger import LabelLedger
from test_oracle_audit.records import StageRecord, TestEntry, TestId, content_hash
from test_oracle_audit.thresholds import tercile_cutpoints, tercile_of

BAND_BASE = {"bottom": 0.0, "middle": 0.4, "top": 0.8}


# --- population for sampling tests -----------------------------------------


def population(counts, insufficient=0):
    """counts: {(flagged, band): size}. Returns entries, static records, mutation records."""
    entries, statics, muts = [], [], []
    i = 0
    for (flagged, band), size in counts.items():
        for j in range(size):
            rate = round(BAND_BASE[band] + 0.19 * j / max(size, 1), 4)
            entries.append(b.entry(i))
            statics.append(b.static_rec(i, ["private_import"] if flagged else []))
            muts.append(b.mutation_rec(i, rate))
            i += 1
    for _ in range(insufficient):
        entries.append(b.entry(i))
        statics.append(b.static_rec(i, []))
        muts.append(b.mutation_rec(i, "insufficient"))
        i += 1
    return entries, statics, muts


def stratum_of(entry, statics, muts):
    """The stratum a test belongs to, derived independently from the shared tercile helper."""
    rates = {m.test_id.node_id: m.payload["kill_rate"] for m in muts}
    numeric = [float(r) for r in rates.values() if r != "insufficient"]
    cuts = tercile_cutpoints(numeric)
    rate = rates[entry.test_id.node_id]
    if rate == "insufficient":
        return "insufficient"
    flagged = any(
        s.payload["rules"] for s in statics if s.test_id.node_id == entry.test_id.node_id and s.status == "ok"
    )
    return (flagged, tercile_of(float(rate), cuts))


EVEN = {(f, band): 30 for f in (True, False) for band in BAND_BASE}


def test_sample_of_forty_covers_every_non_empty_stratum():
    """Scenario test-oracle-audit.39: all seven strata are non-empty, so all seven contribute."""
    entries, statics, muts = population({k: 10 for k in EVEN}, insufficient=5)
    sample = stratified_sample(entries, statics, muts, n=40, seed=0)
    assert len(sample) == 40
    assert len({e.test_id.node_id for e in sample}) == 40
    all_strata = {stratum_of(e, statics, muts) for e in entries}
    assert len(all_strata) == 7
    assert {stratum_of(e, statics, muts) for e in sample} == all_strata


def test_a_tiny_stratum_is_still_represented():
    """Scenario test-oracle-audit.39: one flagged top-tercile test among 210 is drawn (n=40).

    Bands hold 70 tests each (35+35, 35+35, 1+69); the flagged-top stratum has a single member, far
    below its proportional share, but must still contribute it.
    """
    counts = {
        (True, "bottom"): 35, (False, "bottom"): 35,
        (True, "middle"): 35, (False, "middle"): 35,
        (True, "top"): 1, (False, "top"): 69,
    }
    entries, statics, muts = population(counts)
    singles = [e for e in entries if stratum_of(e, statics, muts) == (True, "top")]
    assert len(singles) == 1  # fixture guard
    sample = stratified_sample(entries, statics, muts, n=40, seed=0)
    assert len(sample) == 40
    assert singles[0].test_id.node_id in {e.test_id.node_id for e in sample}


def test_empty_strata_are_tolerated():
    """Scenario test-oracle-audit.39 ("non-empty" strata): no insufficient tests and no flagged-top tests."""
    counts = {
        (True, "bottom"): 10, (False, "bottom"): 10,
        (True, "middle"): 10, (False, "middle"): 10,
        (False, "top"): 20,
    }
    entries, statics, muts = population(counts)
    sample = stratified_sample(entries, statics, muts, n=20, seed=1)
    assert len(sample) == 20
    present = {stratum_of(e, statics, muts) for e in entries}
    assert len(present) == 5
    assert {stratum_of(e, statics, muts) for e in sample} == present


def test_sample_members_come_from_the_given_entries():
    """Scenario test-oracle-audit.39: the sample is a subset of the supplied entries."""
    entries, statics, muts = population(EVEN, insufficient=10)
    sample = stratified_sample(entries, statics, muts, n=40, seed=0)
    assert {e.test_id.node_id for e in sample} <= {e.test_id.node_id for e in entries}


def test_same_seed_gives_the_same_sample_and_another_seed_a_different_one():
    """Design D9 / task 6.1 (seeded, reproducible sample); supports scenario test-oracle-audit.39."""
    entries, statics, muts = population(EVEN, insufficient=10)
    first = stratified_sample(entries, statics, muts, n=40, seed=7)
    again = stratified_sample(entries, statics, muts, n=40, seed=7)
    other = stratified_sample(entries, statics, muts, n=40, seed=8)
    assert first == again
    assert {e.test_id.node_id for e in first} != {e.test_id.node_id for e in other}


def test_sample_ignores_input_order_of_records():
    """Design D9 (the join is by test id): shuffling the record lists does not change the sample."""
    entries, statics, muts = population(EVEN, insufficient=10)
    a = stratified_sample(entries, statics, muts, n=40, seed=3)
    c = stratified_sample(entries, list(reversed(statics)), list(reversed(muts)), n=40, seed=3)
    assert {e.test_id.node_id for e in a} == {e.test_id.node_id for e in c}


# --- cards -----------------------------------------------------------------

BIG_BODY = "\n".join(f"    step_{k} = {k}" for k in range(60)).replace("step_55 = 55", "SENTINEL_LATE_BODY_LINE = 55")

MOD_SRC = '''\
def clamp(value, lo, hi):
    """Limit ``value`` to the closed range [lo, hi]."""
    return max(lo, min(value, hi))


def _private_detail(x):
    """A private helper docstring."""
    return x
'''

BIG_SRC = f'''\
def long_function(x):
    """Docstring of the long function."""
{BIG_BODY}
    return x
'''

SPEC_SRC = """\
# widgets Specification

## Requirements

### Requirement: Clamp Output

The system SHALL keep outputs inside the configured range. UNIQUE_SPEC_SENTENCE_ALPHA

#### Scenario: Value above the range

- **WHEN** the value exceeds the upper bound
- **THEN** the upper bound is returned

### Requirement: Unrelated Thing

UNRELATED_SPEC_SENTENCE_BETA
"""


def make_repo(root: Path, n_tests: int = 12):
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "mod.py").write_text(MOD_SRC)
    (root / "pkg" / "big.py").write_text(BIG_SRC)
    spec_dir = root / "openspec" / "specs" / "widgets"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC_SRC)
    (root / "tests").mkdir()
    lines = ["from pkg.mod import clamp", ""]
    for k in range(n_tests):
        lines += ["", f"def test_gen_{k:02d}():"]
        if k == 0:
            lines.append('    """Verifies openspec/specs/widgets/spec.md, Requirement: Clamp Output."""')
        lines.append(f"    assert clamp({15 + k}, 0, 10) == 10")
    src = "\n".join(lines) + "\n"
    (root / "tests" / "test_gen.py").write_text(src)
    return src


def entries_for(root: Path, n_tests: int = 12) -> list[TestEntry]:
    import ast

    src = (root / "tests" / "test_gen.py").read_text()
    tree = ast.parse(src)
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.append(
                TestEntry(
                    test_id=TestId(f"tests/test_gen.py::{node.name}", content_hash(src, node.name)),
                    path="tests/test_gen.py",
                    line_start=node.lineno,
                    line_end=node.end_lineno,
                    function_name=node.name,
                    covered_modules=("pkg.mod", "pkg.big"),
                )
            )
    assert len(out) == n_tests
    return out


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    make_repo(root)
    return root


@pytest.fixture(autouse=True)
def _no_prompting(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("labelling must be non-interactive: input() was called")

    monkeypatch.setattr(builtins, "input", boom)


def records_for(entries):
    """Static and mutation records for the 12 repo entries; the other approaches' outputs to hide.

    Flags alternate and kill rates rise with the index, so the tests fall into six strata of two
    (flag x tercile), which is why the flow tests draw n=6 (one per stratum).
    """
    statics, muts = [], []
    for k, e in enumerate(entries):
        rec_static = StageRecord(e.test_id, "static", "ok", {"rules": ["assertion_free"] if k % 2 else []})
        rate = round(0.1 + 0.07 * k, 4)
        rec_mut = StageRecord(
            e.test_id, "mutation", "ok",
            {"backend": "ast", "covering_mutants": 10, "killed_mutants": int(rate * 10), "kill_rate": rate},
        )
        statics.append(rec_static)
        muts.append(rec_mut)
    return statics, muts


def test_card_shows_the_test_source_and_covered_signatures_with_docstrings(repo):
    """Scenario test-oracle-audit.40 (what a card shows): test, covered signatures and docstrings."""
    entry = entries_for(repo)[3]
    card = render_card(entry, repo_root=repo)
    assert "assert clamp(18, 0, 10) == 10" in card
    assert "def clamp(value, lo, hi)" in card
    assert "Limit ``value`` to the closed range [lo, hi]." in card
    assert "def long_function(x)" in card
    assert "Docstring of the long function." in card


def test_card_cuts_function_bodies_at_forty_lines(repo):
    """Scenario test-oracle-audit.40 / design D9: a body line past line 40 of a covered function is not shown."""
    card = render_card(entries_for(repo)[3], repo_root=repo)
    assert "SENTINEL_LATE_BODY_LINE" not in card


def test_card_includes_the_cited_spec_requirement_only(repo):
    """Scenario test-oracle-audit.40 / design D9: a docstring citing a requirement brings that spec text onto the card."""
    cited = render_card(entries_for(repo)[0], repo_root=repo)
    assert "UNIQUE_SPEC_SENTENCE_ALPHA" in cited
    assert "UNRELATED_SPEC_SENTENCE_BETA" not in cited
    uncited = render_card(entries_for(repo)[1], repo_root=repo)
    assert "UNIQUE_SPEC_SENTENCE_ALPHA" not in uncited


def test_card_contains_no_other_approachs_output(repo):
    """Scenario test-oracle-audit.40: a test with static, mutation, judged and history records gets a card with none of them."""
    entries = entries_for(repo)
    forbidden = (
        "assertion_free", "mock_assertion_dominant", "private_attribute_assert", "private_import",
        "mirrored_test_file", "unscoped_patch", "kill_rate", "kill rate", "killed", "co_change",
        "added_with_fix", "survives_refactor", "low_confidence", "unrenamable",
    )
    for entry in entries:
        card = render_card(entry, repo_root=repo)
        for token in forbidden:
            assert token not in card.lower(), f"{token!r} leaked onto the card for {entry.test_id.node_id}"


def test_render_card_cannot_receive_other_approachs_records():
    """Scenario test-oracle-audit.40 (blind by construction): its parameters accept no stage records."""
    names = set(inspect.signature(render_card).parameters)
    assert {"entry", "repo_root"} <= names
    assert not any(token in name for name in names for token in ("static", "mutation", "judged", "history", "record"))


# --- non-interactive label flow -------------------------------------------


def run_next(repo, tmp_path, entries, *, seed=0, n=6, dry_run=False, name="out"):
    statics, muts = records_for(entries)
    return label_next(
        entries, statics, muts,
        repo_root=repo, out_dir=tmp_path / name, ledger_path=tmp_path / "labels.json",
        n=n, seed=seed, dry_run=dry_run,
    )


def sampled(entries, *, n=6, seed=0):
    statics, muts = records_for(entries)
    return stratified_sample(entries, statics, muts, n=n, seed=seed)


def test_label_next_emits_the_first_unlabelled_card_and_writes_every_card(repo, tmp_path):
    """Scenario test-oracle-audit.41 / design D9: ``label next`` emits one card and writes all to <out>/cards/."""
    entries = entries_for(repo)
    card = run_next(repo, tmp_path, entries)
    first = sampled(entries)[0]
    assert render_card(first, repo_root=repo) in card
    files = sorted((tmp_path / "out" / "cards").glob("*.md"))
    assert len(files) == 6
    assert all(re.fullmatch(r"\d+-[^/]+\.md", f.name) for f in files)


def test_label_next_and_record_label_walk_the_sample_one_card_per_invocation(repo, tmp_path):
    """Scenario test-oracle-audit.41 / task 6.1: separate invocations emit a card and record a label; input() is never called."""
    entries = entries_for(repo)
    order = sampled(entries)
    ledger_path = tmp_path / "labels.json"
    for position, test in enumerate(order):
        card = run_next(repo, tmp_path, entries)
        assert render_card(test, repo_root=repo) in card, f"card {position} is not the next unlabelled test"
        record_label(test.test_id.node_id, "spec", repo_root=repo, ledger_path=ledger_path, labeller="operator")
    assert run_next(repo, tmp_path, entries) is None
    assert len(LabelLedger.load(ledger_path).entries) == len(order)


def test_label_next_persists_the_sample_in_the_ledger(repo, tmp_path, schema_validator):
    """Design D9 (draws or reloads the sample); contract label-ledger.schema.json ``sample``."""
    entries = entries_for(repo)
    run_next(repo, tmp_path, entries, seed=5, n=6)
    data = json.loads((tmp_path / "labels.json").read_text())
    schema_validator(data, "label-ledger")
    assert data["sample"]["seed"] == 5 and data["sample"]["n"] == 6
    in_strata = {nid for ids in data["sample"]["strata"].values() for nid in ids}
    assert in_strata == {e.test_id.node_id for e in sampled(entries, n=6, seed=5)}


def test_label_next_reloads_the_stored_sample(repo, tmp_path):
    """Design D9 ("draws (or reloads)"): a second invocation with another seed still serves the stored sample."""
    entries = entries_for(repo)
    first = run_next(repo, tmp_path, entries, seed=0, n=6)
    second = run_next(repo, tmp_path, entries, seed=999, n=8)
    assert second == first
    assert LabelLedger.load(tmp_path / "labels.json").sample["seed"] == 0


# --- record_label ---------------------------------------------------------


def test_record_label_hashes_the_current_test_source(repo, tmp_path, schema_validator):
    """Scenario test-oracle-audit.41 / design D9 (``label record`` hashes the current test source)."""
    entries = entries_for(repo)
    target = entries[4]
    ledger_path = tmp_path / "labels.json"
    entry = record_label(
        target.test_id.node_id, "property", repo_root=repo, ledger_path=ledger_path,
        labeller="operator", note="invariant over the range",
    )
    assert entry.label == "property" and entry.labeller == "operator"
    loaded = LabelLedger.load(ledger_path)
    assert [e.node_id for e in loaded.entries] == [target.test_id.node_id]
    assert loaded.entries[0].content_hash == content_hash((repo / "tests" / "test_gen.py").read_text(), "test_gen_04")
    assert loaded.entries[0].note == "invariant over the range"
    schema_validator(json.loads(ledger_path.read_text()), "label-ledger")


def test_record_label_keeps_the_stored_sample(repo, tmp_path):
    """Design D9: appending a label does not drop the sample written by ``label next``."""
    entries = entries_for(repo)
    run_next(repo, tmp_path, entries)
    record_label(entries[0].test_id.node_id, "none", repo_root=repo, ledger_path=tmp_path / "labels.json", labeller="op")
    assert LabelLedger.load(tmp_path / "labels.json").sample is not None


def test_record_label_rejects_an_unknown_label_and_writes_nothing(repo, tmp_path):
    """Scenario test-oracle-audit.4: a label outside the vocabulary is rejected and no ledger is written."""
    entries = entries_for(repo)
    ledger_path = tmp_path / "labels.json"
    with pytest.raises(ValueError, match="allowed values"):
        record_label(entries[0].test_id.node_id, "vibes", repo_root=repo, ledger_path=ledger_path, labeller="op")
    assert not ledger_path.exists()


def test_recorded_label_survives_whitespace_edits_and_goes_stale_on_logic_edits(repo, tmp_path):
    """Scenarios test-oracle-audit.2 and .3 through ``record_label``: the hash it stored tracks the test's logic."""
    entries = entries_for(repo)
    node = entries[2].test_id.node_id
    ledger_path = tmp_path / "labels.json"
    record_label(node, "spec", repo_root=repo, ledger_path=ledger_path, labeller="op")
    ledger = LabelLedger.load(ledger_path)
    path = repo / "tests" / "test_gen.py"

    path.write_text(path.read_text().replace("    assert clamp(17, 0, 10) == 10", "    # a comment\n\n    assert clamp(17,0,10)==10"))
    same = content_hash(path.read_text(), "test_gen_02")
    assert node in ledger.current_labels({node: same})

    path.write_text(path.read_text().replace("clamp(17,0,10)==10", "clamp(17, 0, 10) == 9"))
    changed = content_hash(path.read_text(), "test_gen_02")
    assert ledger.current_labels({node: changed}) == {}


# --- dry run --------------------------------------------------------------


def test_dry_run_renders_every_card_and_does_not_create_the_ledger(repo, tmp_path):
    """Scenario test-oracle-audit.41: ``--dry-run`` renders cards to the output directory; no ledger file appears.

    Also scenario .40: the rendered files carry none of the static or mutation outputs that were supplied.
    """
    entries = entries_for(repo)
    card = run_next(repo, tmp_path, entries, dry_run=True)
    assert isinstance(card, str) and card
    files = sorted((tmp_path / "out" / "cards").glob("*.md"))
    assert len(files) == 6
    assert not (tmp_path / "labels.json").exists()
    for f in files:
        text = f.read_text().lower()
        assert "assertion_free" not in text and "kill_rate" not in text and "killed" not in text


def test_dry_run_leaves_an_existing_ledger_byte_identical(repo, tmp_path):
    """Scenario test-oracle-audit.41: an existing ledger is not modified by a dry run."""
    entries = entries_for(repo)
    ledger_path = tmp_path / "labels.json"
    record_label(entries[0].test_id.node_id, "spec", repo_root=repo, ledger_path=ledger_path, labeller="op")
    before = ledger_path.read_bytes()
    run_next(repo, tmp_path, entries, dry_run=True)
    assert ledger_path.read_bytes() == before
