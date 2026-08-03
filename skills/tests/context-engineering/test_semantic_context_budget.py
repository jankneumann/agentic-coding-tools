"""The budget is first-fit over a fixed order, and that is the whole point.

Design decision D6 admits a hit only when all four bounds hold, and when one
fails it records the **first** failing reason in a fixed order — so the reason a
hit was dropped is a function of the inputs alone rather than of which check the
implementation happened to run first.

The property this file guards hardest is the absence of an early break. A greedy
pass that stopped at the first oversized hit would produce a different section
depending on where that hit landed in the ranking, which is the same
input-order dependence the rank key exists to remove. ``test_a_small_hit_is_still
_admitted_after_a_large_one_is_skipped`` is the assertion that catches it, and it
is written so that a ``break`` in place of the ``continue`` fails it outright.

Coverage here plus ``test_semantic_context_determinism.py`` accounts for all
seven omission reasons in the section schema's closed enum: two dedup reasons
there, the four budget reasons and ``scope_filtered`` here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills/context-engineering/scripts"
PROMOTED = REPO_ROOT / "openspec/contracts/code-search/schemas"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import semantic_context as sc  # noqa: E402

REVISION = "1cf51386d0c0ffee1cf51386d0c0ffee1cf51386"
INDEX_ID = "9f1c0b3a-6d2e-4f81-9a44-0e1b2c3d4e5f"


def hit(
    file_path: str,
    start_line: int,
    end_line: int,
    score: float,
    index_id: str = INDEX_ID,
) -> sc.InjectedHit:
    return sc.InjectedHit(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        score=score,
        indexed_commit=REVISION,
        index_id=index_id,
        language="python",
        content="x",
    )


def budget(**overrides: int) -> sc.ContextBudget:
    """A permissive budget with only the bound under test tightened."""
    values: dict[str, int] = {
        "max_hits": 100,
        "max_files": 100,
        "max_total_lines": 100000,
        "max_hit_lines": 100000,
    }
    values.update(overrides)
    return sc.ContextBudget(**values)


def section_validator() -> Draft202012Validator:
    """Validator for the promoted section schema, with its sibling `$ref` resolved."""
    section = json.loads((PROMOTED / "semantic-context-section.schema.json").read_text())
    hit_schema = json.loads((PROMOTED / "semantic-context-hit.schema.json").read_text())
    registry = Registry().with_resources(
        [
            ("./semantic-context-hit.schema.json", Resource.from_contents(hit_schema)),
            (hit_schema["$id"], Resource.from_contents(hit_schema)),
        ]
    )
    return Draft202012Validator(section, registry=registry)


class TestDefaults:
    def test_the_four_bounds_carry_the_documented_defaults(self) -> None:
        default = sc.DEFAULT_BUDGET
        assert (
            default.max_hits,
            default.max_files,
            default.max_total_lines,
            default.max_hit_lines,
        ) == (8, 5, 240, 40)

    def test_the_query_limit_leaves_room_for_dedup_without_exceeding_the_server_cap(
        self,
    ) -> None:
        # Ask for three times the render budget so dedup and budgeting have
        # something to work with, but never more than ri-03's own cap of 50.
        assert sc.ContextBudget(max_hits=8).query_limit == 24
        assert sc.ContextBudget(max_hits=100).query_limit == 50
        assert sc.ContextBudget(max_hits=1).query_limit == 3

    def test_a_bound_below_one_is_rejected_rather_than_silently_clamped(self) -> None:
        with pytest.raises(ValueError, match="max_hits"):
            sc.ContextBudget(max_hits=0)


class TestEnvOverrides:
    def test_each_bound_has_its_own_environment_override(self) -> None:
        resolved = sc.ContextBudget.from_env(
            {
                "SEMANTIC_CONTEXT_MAX_HITS": "3",
                "SEMANTIC_CONTEXT_MAX_FILES": "2",
                "SEMANTIC_CONTEXT_MAX_TOTAL_LINES": "50",
                "SEMANTIC_CONTEXT_MAX_HIT_LINES": "10",
            }
        )
        assert resolved == sc.ContextBudget(
            max_hits=3, max_files=2, max_total_lines=50, max_hit_lines=10
        )

    def test_an_absent_override_keeps_the_default(self) -> None:
        assert sc.ContextBudget.from_env({}) == sc.DEFAULT_BUDGET

    @pytest.mark.parametrize("value", ["", "0", "-1", "eight", "3.5", " "])
    def test_an_unusable_override_falls_back_to_the_default_for_that_bound(
        self, value: str
    ) -> None:
        # A malformed override must not raise (collect_semantic_context never
        # raises) and must not disable the bound; it degrades to the default so
        # the budget stays a pure function of the environment.
        resolved = sc.ContextBudget.from_env({"SEMANTIC_CONTEXT_MAX_HITS": value})
        assert resolved.max_hits == sc.DEFAULT_BUDGET.max_hits


class TestTheFourBounds:
    def test_hit_count_cap(self) -> None:
        hits = [
            hit("skills/a.py", 1, 2, 0.9),
            hit("skills/a.py", 10, 11, 0.8),
            hit("skills/a.py", 20, 21, 0.7),
        ]
        kept, omissions = sc.apply_budget(hits, budget(max_hits=2))
        assert list(kept) == hits[:2]
        assert [(o.start_line, o.reason) for o in omissions] == [(20, "hit_count_cap")]

    def test_file_count_cap(self) -> None:
        hits = [
            hit("skills/a.py", 1, 2, 0.9),
            hit("skills/b.py", 1, 2, 0.8),
            hit("skills/a.py", 10, 11, 0.7),
        ]
        kept, omissions = sc.apply_budget(hits, budget(max_files=1))
        # The third hit re-uses an already-admitted file, so the cap does not
        # touch it: the bound is on distinct files, not on hits.
        assert [h.file_path for h in kept] == ["skills/a.py", "skills/a.py"]
        assert [(o.file_path, o.reason) for o in omissions] == [
            ("skills/b.py", "file_count_cap")
        ]

    def test_hit_line_cap(self) -> None:
        hits = [hit("skills/a.py", 1, 2, 0.9), hit("skills/a.py", 10, 40, 0.8)]
        kept, omissions = sc.apply_budget(hits, budget(max_hit_lines=10))
        assert list(kept) == hits[:1]
        assert [(o.start_line, o.reason) for o in omissions] == [(10, "hit_line_cap")]

    def test_an_over_long_hit_is_omitted_rather_than_truncated(self) -> None:
        long_hit = hit("skills/a.py", 1, 60, 0.9)
        kept, omissions = sc.apply_budget([long_hit], budget(max_hit_lines=40))
        # Truncating would make the rendered line range a lie; the section would
        # claim 1-60 while showing 40 lines.
        assert kept == ()
        assert omissions[0].end_line == 60

    def test_total_line_cap(self) -> None:
        hits = [hit("skills/a.py", 1, 10, 0.9), hit("skills/a.py", 20, 29, 0.8)]
        kept, omissions = sc.apply_budget(hits, budget(max_total_lines=15))
        assert list(kept) == hits[:1]
        assert [(o.start_line, o.reason) for o in omissions] == [(20, "total_line_cap")]

    def test_a_hit_that_exactly_fills_the_line_budget_is_admitted(self) -> None:
        hits = [hit("skills/a.py", 1, 10, 0.9), hit("skills/a.py", 20, 24, 0.8)]
        kept, omissions = sc.apply_budget(hits, budget(max_total_lines=15))
        assert list(kept) == hits
        assert omissions == ()


class TestNoEarlyBreak:
    def test_a_small_hit_is_still_admitted_after_a_large_one_is_skipped(self) -> None:
        big = hit("skills/a.py", 1, 10, 0.9)  # 10 lines, admitted
        huge = hit("skills/a.py", 20, 28, 0.8)  # 9 lines, would exceed the cap
        small = hit("skills/a.py", 40, 41, 0.7)  # 2 lines, fits exactly

        kept, omissions = sc.apply_budget([big, huge, small], budget(max_total_lines=12))

        # A pass that stopped at `huge` would drop `small` too, and the section's
        # contents would then depend on where the first oversized hit happened to
        # land in the ranking.
        assert list(kept) == [big, small]
        assert [(o.start_line, o.reason) for o in omissions] == [(20, "total_line_cap")]

    def test_the_scan_continues_past_an_over_long_hit(self) -> None:
        over = hit("skills/a.py", 1, 50, 0.9)
        fits = hit("skills/a.py", 60, 62, 0.8)
        kept, omissions = sc.apply_budget([over, fits], budget(max_hit_lines=10))
        assert list(kept) == [fits]
        assert [o.reason for o in omissions] == ["hit_line_cap"]

    def test_the_scan_continues_past_a_capped_file(self) -> None:
        first = hit("skills/a.py", 1, 2, 0.9)
        other_file = hit("skills/b.py", 1, 2, 0.8)
        same_file = hit("skills/a.py", 10, 11, 0.7)
        kept, _ = sc.apply_budget([first, other_file, same_file], budget(max_files=1))
        assert list(kept) == [first, same_file]


class TestReasonPrecedence:
    """When several bounds fail at once the reason is the first in the fixed order."""

    def test_the_precedence_order_is_pinned(self) -> None:
        assert sc.BUDGET_REASON_ORDER == (
            "hit_count_cap",
            "file_count_cap",
            "hit_line_cap",
            "total_line_cap",
        )

    def test_hit_count_outranks_file_count(self) -> None:
        hits = [hit("skills/a.py", 1, 2, 0.9), hit("skills/b.py", 1, 2, 0.8)]
        _, omissions = sc.apply_budget(hits, budget(max_hits=1, max_files=1))
        assert [o.reason for o in omissions] == ["hit_count_cap"]

    def test_file_count_outranks_hit_line(self) -> None:
        hits = [hit("skills/a.py", 1, 2, 0.9), hit("skills/b.py", 1, 20, 0.8)]
        _, omissions = sc.apply_budget(hits, budget(max_files=1, max_hit_lines=5))
        assert [o.reason for o in omissions] == ["file_count_cap"]

    def test_hit_line_outranks_total_line(self) -> None:
        hits = [hit("skills/a.py", 1, 3, 0.9), hit("skills/a.py", 10, 29, 0.8)]
        _, omissions = sc.apply_budget(hits, budget(max_hit_lines=5, max_total_lines=6))
        assert [o.reason for o in omissions] == ["hit_line_cap"]


class TestOmissionOrder:
    def test_omissions_are_reported_in_the_order_the_hits_were_scanned(self) -> None:
        hits = [
            hit("skills/a.py", 1, 2, 0.9),
            hit("skills/b.py", 1, 2, 0.8),
            hit("skills/c.py", 1, 2, 0.7),
        ]
        _, omissions = sc.apply_budget(hits, budget(max_files=1))
        assert [o.file_path for o in omissions] == ["skills/b.py", "skills/c.py"]

    def test_budgeting_the_same_hits_twice_gives_byte_identical_output(self) -> None:
        hits = [
            hit("skills/a.py", 1, 30, 0.9),
            hit("skills/b.py", 1, 30, 0.8),
            hit("skills/c.py", 1, 4, 0.7),
        ]
        limits = budget(max_files=2, max_total_lines=40)
        runs = []
        for _ in range(2):
            kept, omissions = sc.apply_budget(hits, limits)
            runs.append(
                json.dumps(
                    {
                        "hits": [h.to_dict() for h in kept],
                        "omissions": [o.to_dict() for o in omissions],
                    },
                    sort_keys=True,
                )
            )
        assert runs[0] == runs[1]


class TestOmissionRecordsValidateAgainstTheContract:
    def test_a_budgeted_section_payload_validates(self) -> None:
        hits = [
            hit("skills/a.py", 1, 10, 0.9),
            hit("skills/b.py", 1, 10, 0.8),
            hit("skills/c.py", 1, 10, 0.7),
        ]
        kept, omissions = sc.apply_budget(hits, budget(max_files=2))
        payload = {
            "schema_version": sc.SCHEMA_VERSION,
            "status": "injected",
            "consumer": "implement-feature",
            "requested_revision": REVISION,
            "hits": [h.to_dict() for h in kept],
            "omissions": [o.to_dict() for o in omissions],
            "provenance": {
                "repo_slug": "agentic_coding_tools",
                "namespace_kind": "main",
                "namespace_key": "main",
                "index_id": INDEX_ID,
                "scope_decision": "allowed",
                "scope_authority": "principal_grant",
                "read_allow_count": 2,
                "deny_count": 1,
            },
        }
        section_validator().validate(payload)

    def test_every_budget_reason_is_in_the_schema_enum(self) -> None:
        section = json.loads(
            (PROMOTED / "semantic-context-section.schema.json").read_text()
        )
        enum = section["properties"]["omissions"]["items"]["properties"]["reason"]["enum"]
        assert set(sc.BUDGET_REASON_ORDER) <= set(enum)
        assert set(sc.OMISSION_REASONS) == set(enum)


class DenySkillsOnly:
    """A stand-in for ri-08's ``IndexScopes``: only ``skills/`` is readable."""

    def allows(self, path: str) -> bool:
        return path.startswith("skills/")


class TestScopeFiltering:
    """The seventh omission reason, and the one that is a security claim.

    The service cannot return a path its own scope excluded, so this re-check is
    redundant by design. It exists because ri-12 supplies the scope from the
    client side: without a local check the skill's boundary claim would be a
    claim about someone else's code.
    """

    def test_a_hit_outside_the_read_scope_is_omitted_as_scope_filtered(self) -> None:
        inside = hit("skills/a.py", 1, 2, 0.9)
        outside = hit("agent-coordinator/src/x.py", 1, 2, 0.8)
        kept, omissions = sc.filter_scope([inside, outside], DenySkillsOnly())
        assert list(kept) == [inside]
        assert [(o.file_path, o.reason) for o in omissions] == [
            ("agent-coordinator/src/x.py", "scope_filtered")
        ]

    def test_a_filtered_hit_never_appears_among_the_rendered_hits(self) -> None:
        kept, _ = sc.select_hits(
            [hit("agent-coordinator/src/x.py", 1, 2, 0.9), hit("skills/a.py", 1, 2, 0.8)],
            sc.DEFAULT_BUDGET,
            DenySkillsOnly(),
        )
        assert [h.file_path for h in kept] == ["skills/a.py"]

    def test_a_filtered_hit_does_not_spend_the_budget_it_was_denied(self) -> None:
        # The out-of-scope hit outranks the in-scope one and would exhaust a
        # one-hit budget if it were filtered after budgeting instead of before.
        kept, omissions = sc.select_hits(
            [hit("agent-coordinator/src/x.py", 1, 2, 0.9), hit("skills/a.py", 1, 2, 0.8)],
            budget(max_hits=1),
            DenySkillsOnly(),
        )
        assert [h.file_path for h in kept] == ["skills/a.py"]
        assert [o.reason for o in omissions] == ["scope_filtered"]

    def test_a_filtered_hit_does_not_consume_a_file_slot(self) -> None:
        # The denied hit outranks the allowed one and is in a different file, so
        # filtering after budgeting would spend the single file slot on a file
        # the package is not allowed to read and then drop it, leaving nothing.
        denied = hit("agent-coordinator/src/x.py", 10, 20, 0.9)
        allowed = hit("skills/a.py", 10, 20, 0.8)
        kept, omissions = sc.select_hits([denied, allowed], budget(max_files=1), DenySkillsOnly())
        assert [h.file_path for h in kept] == ["skills/a.py"]
        assert [o.reason for o in omissions] == ["scope_filtered"]

    def test_omissions_are_grouped_scope_then_dedup_then_budget(self) -> None:
        hits = [
            hit("agent-coordinator/src/x.py", 1, 2, 0.95),  # scope_filtered
            hit("skills/a.py", 1, 20, 0.9),  # kept
            hit("skills/a.py", 5, 10, 0.8),  # duplicate_contained
            hit("skills/b.py", 1, 2, 0.7),  # file_count_cap
        ]
        _, omissions = sc.select_hits(hits, budget(max_files=1), DenySkillsOnly())
        assert [o.reason for o in omissions] == [
            "scope_filtered",
            "duplicate_contained",
            "file_count_cap",
        ]

    def test_all_seven_omission_reasons_are_reachable(self) -> None:
        # Six from the other cases in this file and its determinism sibling,
        # plus scope_filtered here. The enum being closed is only useful if no
        # member is dead.
        produced = {"scope_filtered"}
        produced.update(sc.BUDGET_REASON_ORDER)
        produced.update({"duplicate_exact", "duplicate_contained"})
        assert produced == set(sc.OMISSION_REASONS)


class TestFilteredHitsFailClosed:
    def test_a_response_whose_hits_are_all_out_of_scope_is_not_an_empty_success(
        self,
    ) -> None:
        # An empty "injected" section is unrepresentable by the contract, and a
        # silent absence reads to a worker as "no relevant code exists".
        def search(body: dict) -> dict:
            return {
                "status": "ok",
                "status_code": 200,
                "response": {
                    "state": "ready",
                    "current": True,
                    "index": {
                        "index_id": INDEX_ID,
                        "repo_slug": "agentic_coding_tools",
                        "source_revision": REVISION,
                    },
                    "scope": {
                        "decision": "allowed",
                        "source": "explicit",
                        "authority": "principal_grant",
                    },
                    "results": [
                        {
                            "file_path": "agent-coordinator/src/x.py",
                            "language": "python",
                            "content": "x",
                            "start_line": 1,
                            "end_line": 2,
                            "similarity": 0.9,
                            "repo_slug": "agentic_coding_tools",
                            "source_revision": REVISION,
                            "index_id": INDEX_ID,
                            "scope_decision": "allowed",
                        }
                    ],
                    "fallback": {
                        "required": False,
                        "strategy": "exact_search",
                        "reason": None,
                    },
                },
            }

        def git(repository, args):
            args = tuple(args)
            if args[:2] == ("rev-parse", "--show-toplevel"):
                return f"{repository}\n"
            if args == ("rev-parse", "HEAD"):
                return f"{REVISION}\n"
            if args == ("status", "--porcelain"):
                return ""
            return None

        runtime = sc.SemanticContextRuntime(
            search=search,
            detect=lambda: {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "http"},
            git=git,
            load_package=lambda root, change_id, package_id: {
                "package_id": "wp-retrieval",
                "scope": {"read_allow": ["skills/**"], "deny": []},
            },
            load_checkpoint=lambda root, change_id, package_id: None,
            env={"SEMANTIC_CONTEXT_INJECTION": "1"},
        )
        result = sc.collect_semantic_context(
            sc.SemanticContextRequest(
                repository=Path("."),
                query="q",
                consumer="implement-feature",
                change_id="inject-scoped-semantic-context-into-coding-jobs",
                package_id="wp-retrieval",
            ),
            runtime,
        )
        assert result.status == "fallback"
        assert (result.fallback.trigger, result.fallback.reason) == (
            "out_of_scope",
            "all_hits_scope_filtered",
        )
        assert result.hits == ()
        assert result.fallback.strategy == "exact_search"
