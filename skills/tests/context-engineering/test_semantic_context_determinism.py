"""Ordering and deduplication are the deliverable, so they are proven, not assumed.

Design decision D12 rules out the cheap version of this test. Running the same
input through the same function twice and asserting the two outputs match passes
trivially for a function whose comparator reads a ``set``'s iteration order —
the order is arbitrary but *stable within a process*, so self-equality is
satisfied by exactly the bug it is supposed to catch.

Every ordering assertion here is therefore against a **hand-derived** expected
sequence: the fixture below has deliberate ties at every level of the D5 rank
key, and the expected order was worked out on paper from the key's definition,
not by running the code. The seeded-shuffle case then feeds the same fixture in
many different input orders and demands the identical output, which is what
proves the result does not depend on arrival order.

The rank key is total by construction — ``(file_path, start_line, end_line,
index_id)`` is unique within one response — so ``sorted()``'s stability is never
load-bearing and the shuffle can never be a coin flip.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills/context-engineering/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import semantic_context as sc  # noqa: E402

MODULE_SOURCE = (SCRIPTS / "semantic_context.py").read_text(encoding="utf-8")

REVISION = "1cf51386d0c0ffee1cf51386d0c0ffee1cf51386"

# Chosen so the lexicographic order of the UUID strings is I1 < I2 < I3, making
# the fifth rank-key component's effect visible rather than incidental.
I1 = "11111111-1111-4111-8111-111111111111"
I2 = "22222222-2222-4222-8222-222222222222"
I3 = "33333333-3333-4333-8333-333333333333"


def hit(
    file_path: str,
    start_line: int,
    end_line: int,
    score: float,
    index_id: str = I1,
    *,
    content: str = "x",
    language: str = "python",
) -> sc.InjectedHit:
    """One hit, with only the rank-relevant fields spelled out at call sites."""
    return sc.InjectedHit(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        score=score,
        indexed_commit=REVISION,
        index_id=index_id,
        language=language,
        content=content,
    )


# --------------------------------------------------------------------------
# The tie-heavy fixture, and the order derived from D5 by hand.
#
#   G  z.py  1-2    0.9        -- highest score, wins despite the latest path
#   D  a.py  5-9    0.8   I1   -- score tie broken by path, then start_line
#   E  a.py  5-30   0.8   I1   -- same start as D, broken by end_line
#   B  a.py  10-20  0.8   I1   -- later start than D/E
#   C  a.py  10-20  0.8   I2   -- identical but for index_id
#   F  a.py  10-20  0.8000004  I3 -- rounds to 0.8 at 6dp, so it ties and falls
#                                    through to index_id rather than sorting first
#   J  b.py  1-3    0.8   I1   -- the lowest start line in the whole 0.8 group,
#                                 yet it must sort behind every a.py hit: the
#                                 path outranks the line numbers, and this hit is
#                                 what makes that visible in the order itself
#   A  b.py  10-20  0.8   I2   -- same score, later path than every a.py hit
#   H  a.py  1-2    0.79999    -- does NOT round to 0.8, so score still separates
# --------------------------------------------------------------------------
G = hit("skills/z.py", 1, 2, 0.9)
D = hit("skills/a.py", 5, 9, 0.8, I1)
E = hit("skills/a.py", 5, 30, 0.8, I1)
B = hit("skills/a.py", 10, 20, 0.8, I1)
C = hit("skills/a.py", 10, 20, 0.8, I2)
F = hit("skills/a.py", 10, 20, 0.8000004, I3)
J = hit("skills/b.py", 1, 3, 0.8, I1)
A = hit("skills/b.py", 10, 20, 0.8, I2)
H = hit("skills/a.py", 1, 2, 0.79999)

FIXTURE = [A, B, C, D, E, F, G, H, J]
EXPECTED_ORDER = [G, D, E, B, C, F, J, A, H]


class TestRankKey:
    def test_key_is_the_five_tuple_of_design_decision_d5(self) -> None:
        assert sc.rank_key(B) == (-0.8, "skills/a.py", 10, 20, I1)

    def test_score_is_negated_so_higher_similarity_sorts_first(self) -> None:
        assert sc.rank_key(G)[0] < sc.rank_key(B)[0]
        assert G.score > B.score

    def test_score_is_rounded_to_six_places_so_float_noise_becomes_a_tie(self) -> None:
        # F scores fractionally higher than B. Without the rounding it would sort
        # ahead of every 0.8 hit; with it, the structural tie-breakers decide.
        assert F.score > B.score
        assert sc.rank_key(F)[0] == sc.rank_key(B)[0]

    def test_key_is_total_over_the_fixture(self) -> None:
        keys = [sc.rank_key(item) for item in FIXTURE]
        assert len(set(keys)) == len(keys)


class TestHandDerivedOrder:
    def test_ranked_order_matches_the_order_derived_from_the_key_by_hand(self) -> None:
        assert list(sc.rank_hits(FIXTURE)) == EXPECTED_ORDER

    def test_path_breaks_a_score_tie_before_line_numbers_do(self) -> None:
        # J (b.py, line 1) has a lower start line than D (a.py, line 5) at the
        # same score, so a key that consulted line numbers before the path would
        # put J first. The path is the second component; J sorts second.
        assert list(sc.rank_hits([J, D])) == [D, J]
        assert list(sc.rank_hits([D, J])) == [D, J]

    def test_start_line_breaks_a_tie_before_end_line_does(self) -> None:
        assert list(sc.rank_hits([B, D])) == [D, B]

    def test_end_line_breaks_a_tie_before_index_id_does(self) -> None:
        assert list(sc.rank_hits([E, D])) == [D, E]

    def test_index_id_is_the_final_tie_breaker(self) -> None:
        assert list(sc.rank_hits([F, C, B])) == [B, C, F]

    @pytest.mark.parametrize("seed", [0, 1, 7, 1234, 20260726])
    def test_seeded_shuffles_all_collapse_onto_the_same_order(self, seed: int) -> None:
        shuffled = list(FIXTURE)
        random.Random(seed).shuffle(shuffled)
        assert list(sc.rank_hits(shuffled)) == EXPECTED_ORDER

    def test_reversed_input_produces_the_same_order(self) -> None:
        assert list(sc.rank_hits(list(reversed(FIXTURE)))) == EXPECTED_ORDER


class TestDeduplication:
    """One forward pass in rank order; the survivor is always the higher-ranked hit."""

    # P kept; Q is the same interval from another index; R sits inside P;
    # S overlaps P partially and carries lines P does not; T is another file.
    P = hit("skills/a.py", 10, 20, 0.9, I1)
    Q = hit("skills/a.py", 10, 20, 0.9, I2)
    R = hit("skills/a.py", 12, 18, 0.8, I1)
    S = hit("skills/a.py", 15, 25, 0.7, I1)
    T = hit("skills/b.py", 10, 20, 0.6, I1)

    def _run(self) -> tuple[tuple, tuple]:
        return sc.deduplicate(sc.rank_hits([self.T, self.S, self.R, self.Q, self.P]))

    def test_keeps_the_first_of_each_distinct_interval(self) -> None:
        kept, _ = self._run()
        assert list(kept) == [self.P, self.S, self.T]

    def test_an_identical_interval_from_another_index_is_duplicate_exact(self) -> None:
        _, omissions = self._run()
        exact = [o for o in omissions if o.reason == "duplicate_exact"]
        assert [(o.file_path, o.start_line, o.end_line) for o in exact] == [
            ("skills/a.py", 10, 20)
        ]

    def test_a_contained_interval_is_duplicate_contained(self) -> None:
        _, omissions = self._run()
        contained = [o for o in omissions if o.reason == "duplicate_contained"]
        assert [(o.file_path, o.start_line, o.end_line) for o in contained] == [
            ("skills/a.py", 12, 18)
        ]

    def test_the_two_dedup_reasons_are_not_interchangeable(self) -> None:
        _, omissions = self._run()
        by_interval = {(o.start_line, o.end_line): o.reason for o in omissions}
        assert by_interval == {(10, 20): "duplicate_exact", (12, 18): "duplicate_contained"}

    def test_partial_overlap_is_retained_because_it_carries_new_lines(self) -> None:
        kept, omissions = self._run()
        assert self.S in kept
        assert all(o.start_line != 15 for o in omissions)

    def test_containment_is_scoped_to_one_file(self) -> None:
        # T's interval is identical to P's but in another file; it must survive.
        kept, _ = self._run()
        assert self.T in kept

    def test_omissions_come_out_in_rank_order(self) -> None:
        _, omissions = self._run()
        assert [o.start_line for o in omissions] == [10, 12]

    @pytest.mark.parametrize("seed", [0, 3, 99])
    def test_dedup_result_is_independent_of_input_order(self, seed: int) -> None:
        items = [self.P, self.Q, self.R, self.S, self.T]
        random.Random(seed).shuffle(items)
        kept, omissions = sc.deduplicate(sc.rank_hits(items))
        assert list(kept) == [self.P, self.S, self.T]
        assert [(o.start_line, o.reason) for o in omissions] == [
            (10, "duplicate_exact"),
            (12, "duplicate_contained"),
        ]


class TestProducerObligations:
    """``end_line >= start_line`` is the invariant JSON Schema cannot express.

    The contracts README hands it to this package explicitly: two sibling
    properties cannot be compared in JSON Schema, so the type itself has to be
    unable to hold an inverted range.
    """

    def test_an_inverted_range_cannot_be_constructed(self) -> None:
        with pytest.raises(ValueError, match="end_line"):
            hit("skills/a.py", 20, 10, 0.5)

    def test_a_single_line_range_is_legal(self) -> None:
        assert hit("skills/a.py", 7, 7, 0.5).line_count == 1

    def test_an_inverted_omission_range_cannot_be_constructed(self) -> None:
        with pytest.raises(ValueError, match="end_line"):
            sc.Omission(
                file_path="skills/a.py",
                start_line=9,
                end_line=4,
                reason="duplicate_exact",
            )

    def test_line_numbers_are_one_based(self) -> None:
        with pytest.raises(ValueError, match="start_line"):
            hit("skills/a.py", 0, 5, 0.5)

    def test_a_path_escaping_the_repository_cannot_be_constructed(self) -> None:
        with pytest.raises(ValueError, match="file_path"):
            hit("../secrets.py", 1, 2, 0.5)
        with pytest.raises(ValueError, match="file_path"):
            hit("/etc/passwd", 1, 2, 0.5)

    def test_a_dotted_filename_is_still_accepted(self) -> None:
        assert hit("docs/guides/a..b.md", 1, 2, 0.5).file_path == "docs/guides/a..b.md"

    def test_index_id_must_be_a_uuid(self) -> None:
        with pytest.raises(ValueError, match="index_id"):
            hit("skills/a.py", 1, 2, 0.5, "not-a-uuid")

    def test_indexed_commit_must_be_a_full_revision(self) -> None:
        with pytest.raises(ValueError, match="indexed_commit"):
            sc.InjectedHit(
                file_path="skills/a.py",
                start_line=1,
                end_line=2,
                score=0.5,
                indexed_commit="abc123",
                index_id=I1,
                language="python",
                content="x",
            )

    def test_hit_to_dict_uses_the_contract_field_names(self) -> None:
        # `score` and `indexed_commit` are the rendered names for the
        # coordinator's `similarity` and `source_revision` (contracts README).
        payload = B.to_dict()
        assert set(payload) == {
            "file_path",
            "start_line",
            "end_line",
            "score",
            "indexed_commit",
            "index_id",
            "scope_decision",
            "language",
            "content",
        }
        assert payload["score"] == pytest.approx(0.8)
        assert payload["indexed_commit"] == REVISION
        assert payload["scope_decision"] == "allowed"


class TestNoNondeterministicInputs:
    """A determinism claim is only as good as the module's inputs.

    These are cheap source-level assertions rather than behavioural ones on
    purpose: a wall clock or an RNG reintroduced into the ranking path would not
    necessarily change any single run's output, so no output comparison can rule
    it out.
    """

    @pytest.mark.parametrize(
        "forbidden",
        [
            r"^import random\b",
            r"^import time\b",
            r"\brandom\.",
            r"\btime\.time\(",
            r"\bdatetime\.now\(",
            r"\butcnow\(",
        ],
    )
    def test_module_does_not_reach_for_a_clock_or_an_rng(self, forbidden: str) -> None:
        assert not re.search(forbidden, MODULE_SOURCE, re.MULTILINE)

    def test_ranked_hits_round_trip_through_json_unchanged(self) -> None:
        first = json.dumps([h.to_dict() for h in sc.rank_hits(FIXTURE)], sort_keys=True)
        second = json.dumps([h.to_dict() for h in sc.rank_hits(FIXTURE)], sort_keys=True)
        assert first == second


# --------------------------------------------------------------------------
# End to end: the same determinism claim, but through the seams a real coding
# job goes through -- git, the package scope, the bridge -- all stubbed.
# --------------------------------------------------------------------------

PACKAGE = {
    "package_id": "wp-retrieval",
    "scope": {
        "read_allow": ["skills/**", "docs/**"],
        "deny": ["**/.venv/**"],
    },
}


def as_service_hit(item: sc.InjectedHit) -> dict:
    """One hit in the *coordinator's* vocabulary, which is what the wire carries."""
    return {
        "file_path": item.file_path,
        "language": item.language,
        "content": item.content,
        "start_line": item.start_line,
        "end_line": item.end_line,
        "similarity": item.score,
        "repo_slug": "agentic_coding_tools",
        "source_revision": item.indexed_commit,
        "index_id": item.index_id,
        "scope_decision": "allowed",
    }


def service_response(results: list[dict], state: str = "ready") -> dict:
    return {
        "state": state,
        "current": state == "ready",
        "request": {
            "repo_slug": "agentic_coding_tools",
            "source_revision": REVISION,
            "namespace": {"kind": "main", "key": "main"},
            "index_id": None,
        },
        "index": {
            "index_id": I1,
            "repo_slug": "agentic_coding_tools",
            "source_revision": REVISION,
            "namespace": {"kind": "main", "key": "main"},
            "embedder_model": "text-embedding-3-small",
            "embedding_dim": 1536,
        },
        "scope": {
            "decision": "allowed",
            "source": "explicit",
            "authority": "principal_grant",
        },
        "results": results,
        "fallback": {"required": False, "strategy": "exact_search", "reason": None},
    }


def git_stub(*, dirty: bool = False, revision: str = REVISION):
    def run(repository, args):
        args = tuple(args)
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return f"{repository}\n"
        if args == ("rev-parse", "HEAD"):
            return f"{revision}\n"
        if args == ("status", "--porcelain"):
            return "M skills/a.py\n" if dirty else ""
        return None
    return run


def stub_runtime(results: list[dict], **overrides):
    """A runtime whose every boundary is a stub, and whose flag is on."""
    captured: dict = {}

    def search(body):
        captured["body"] = body
        return {"status": "ok", "status_code": 200, "response": service_response(results)}

    defaults = dict(
        search=search,
        detect=lambda: {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "http"},
        git=git_stub(),
        load_package=lambda root, change_id, package_id: PACKAGE,
        load_checkpoint=lambda root, change_id, package_id: None,
        env={"SEMANTIC_CONTEXT_INJECTION": "1"},
    )
    defaults.update(overrides)
    runtime = sc.SemanticContextRuntime(**defaults)
    return runtime, captured


def collect(results: list[dict], **overrides) -> sc.SemanticContextResult:
    runtime, _ = stub_runtime(results, **overrides)
    return sc.collect_semantic_context(
        sc.SemanticContextRequest(
            repository=Path("."),
            query="deterministic ranking",
            consumer="implement-feature",
            change_id="inject-scoped-semantic-context-into-coding-jobs",
            package_id="wp-retrieval",
        ),
        runtime,
    )


class TestEndToEndDeterminism:
    """The whole pipeline, hand-derived from the same fixture.

    Ranked order is [G, D, E, B, C, F, J, A, H]; B, C and F all sit inside E's
    5-30 span and are dropped as ``duplicate_contained``; nothing exceeds the
    default budget. So six hits survive, in exactly this order.
    """

    EXPECTED_INJECTED = [G, D, E, J, A, H]

    def test_the_injected_hits_are_the_hand_derived_survivors_in_order(self) -> None:
        result = collect([as_service_hit(h) for h in FIXTURE])
        assert result.status == "injected"
        assert [
            (h.file_path, h.start_line, h.end_line, h.index_id) for h in result.hits
        ] == [(h.file_path, h.start_line, h.end_line, h.index_id) for h in self.EXPECTED_INJECTED]

    def test_the_contained_duplicates_are_recorded_with_their_reason(self) -> None:
        result = collect([as_service_hit(h) for h in FIXTURE])
        assert [(o.start_line, o.reason) for o in result.omissions] == [
            (10, "duplicate_contained"),
            (10, "duplicate_contained"),
            (10, "duplicate_contained"),
        ]

    @pytest.mark.parametrize("seed", [0, 5, 42, 2026])
    def test_the_service_result_order_does_not_change_the_section(self, seed: int) -> None:
        shuffled = [as_service_hit(h) for h in FIXTURE]
        random.Random(seed).shuffle(shuffled)
        baseline = collect([as_service_hit(h) for h in FIXTURE]).to_dict()
        assert collect(shuffled).to_dict() == baseline

    def test_the_result_carries_the_revision_it_asked_for(self) -> None:
        result = collect([as_service_hit(h) for h in FIXTURE])
        assert result.requested_revision == REVISION
        assert all(h.indexed_commit == REVISION for h in result.hits)

    def test_the_request_sends_an_explicit_scope_not_a_work_package_scope(self) -> None:
        # D2: `work_package` scope is rejected by the coordinator on every call
        # because no resolver is wired, so sending one would guarantee a fallback.
        runtime, captured = stub_runtime([as_service_hit(h) for h in FIXTURE])
        sc.collect_semantic_context(
            sc.SemanticContextRequest(
                repository=Path("."),
                query="q",
                consumer="implement-feature",
                change_id="inject-scoped-semantic-context-into-coding-jobs",
                package_id="wp-retrieval",
            ),
            runtime,
        )
        assert captured["body"]["scope"]["kind"] == "explicit"
        assert captured["body"]["scope"]["read_allow"] == ["skills/**", "docs/**"]
        assert captured["body"]["scope"]["deny"] == ["**/.venv/**"]

    def test_the_request_asks_for_more_hits_than_it_will_render(self) -> None:
        runtime, captured = stub_runtime([as_service_hit(h) for h in FIXTURE])
        sc.collect_semantic_context(
            sc.SemanticContextRequest(
                repository=Path("."),
                query="q",
                consumer="implement-feature",
                change_id="inject-scoped-semantic-context-into-coding-jobs",
                package_id="wp-retrieval",
            ),
            runtime,
        )
        assert captured["body"]["limit"] == sc.DEFAULT_BUDGET.query_limit
        assert captured["body"]["limit"] <= sc.MAX_QUERY_LIMIT

    def test_a_flag_off_run_never_touches_git_or_the_bridge(self) -> None:
        touched: list[str] = []

        def loud_git(repository, args):
            touched.append("git")
            return ""

        def loud_search(body):
            touched.append("search")
            return {"status": "ok"}

        result = collect(
            [], env={}, git=loud_git, search=loud_search, detect=lambda: touched.append("detect")
        )
        assert result.status == "fallback"
        assert (result.fallback.trigger, result.fallback.reason) == (
            "unavailable",
            "injection_disabled",
        )
        assert touched == []
