"""Tests for the deterministic behavior seeder (R6, design D4).

The seeder is a pure function of the graph and insight artifacts — no LLM. It
produces the fixed skeleton the synthesis step is allowed to name and narrate
but never extend, which is what keeps synthesized narratives grounded.
"""

from __future__ import annotations

from typing import Any

from behavior_seeder import (
    UNCOVERED_NO_TRACED_FLOW,
    seed_behaviors,
)


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "py:api.claim_task", "kind": "function", "file": "src/api.py",
             "span": {"start": 10, "end": 40}, "name": "claim_task"},
            {"id": "py:svc.lock", "kind": "function", "file": "src/svc.py",
             "span": {"start": 1, "end": 20}, "name": "lock"},
            {"id": "py:db.write", "kind": "function", "file": "src/db.py",
             "span": {"start": 5, "end": 15}, "name": "write"},
            {"id": "py:api.health", "kind": "function", "file": "src/api.py",
             "span": {"start": 50, "end": 55}, "name": "health"},
            {"id": "py:api.report", "kind": "function", "file": "src/api.py",
             "span": {"start": 60, "end": 80}, "name": "report"},
            {"id": "py:svc.render", "kind": "function", "file": "src/svc.py",
             "span": {"start": 30, "end": 45}, "name": "render"},
        ],
        "edges": [
            {"from": "py:api.claim_task", "to": "py:svc.lock", "type": "call",
             "confidence": "high", "evidence": "ast"},
            {"from": "py:svc.lock", "to": "py:db.write", "type": "db_access",
             "confidence": "high", "evidence": "ast"},
            {"from": "py:api.report", "to": "py:svc.render", "type": "call",
             "confidence": "high", "evidence": "ast"},
        ],
        "entrypoints": [
            {"node_id": "py:api.claim_task", "kind": "route", "method": "POST",
             "path": "/tasks/claim"},
            {"node_id": "py:api.health", "kind": "route", "method": "GET",
             "path": "/health"},
            {"node_id": "py:api.report", "kind": "route", "method": "GET",
             "path": "/report"},
        ],
    }


# --------------------------------------------------------------------------- #
# Clustering (D4 steps 1-2)
# --------------------------------------------------------------------------- #
def test_clusters_root_at_entrypoints_and_expand_downstream() -> None:
    seeds = seed_behaviors(_graph())

    roots = {c["root"] for c in seeds["clusters"]}
    assert "py:api.claim_task" in roots

    claim = next(c for c in seeds["clusters"] if c["root"] == "py:api.claim_task")
    assert set(claim["member_nodes"]) == {
        "py:api.claim_task", "py:svc.lock", "py:db.write"
    }


def test_expansion_follows_call_api_call_and_db_access_edges() -> None:
    graph = _graph()
    graph["edges"].append(
        {"from": "py:db.write", "to": "py:svc.render", "type": "api_call",
         "confidence": "medium", "evidence": "fetch"}
    )

    seeds = seed_behaviors(graph)
    claim = next(c for c in seeds["clusters"] if c["root"] == "py:api.claim_task")

    assert "py:svc.render" in claim["member_nodes"]


def test_import_edges_do_not_drive_expansion() -> None:
    graph = _graph()
    graph["edges"].append(
        {"from": "py:api.health", "to": "py:svc.render", "type": "import",
         "confidence": "high", "evidence": "ast"}
    )

    seeds = seed_behaviors(graph)

    uncovered_ids = {u["node_id"] for u in seeds["uncovered"]}
    assert "py:api.health" in uncovered_ids


def test_output_is_deterministic() -> None:
    first = seed_behaviors(_graph())
    second = seed_behaviors(_graph())
    assert first == second


def test_member_nodes_are_sorted() -> None:
    seeds = seed_behaviors(_graph())
    for cluster in seeds["clusters"]:
        assert cluster["member_nodes"] == sorted(cluster["member_nodes"])


# --------------------------------------------------------------------------- #
# Merging (D4 step 3)
# --------------------------------------------------------------------------- #
def test_clusters_with_majority_overlap_merge() -> None:
    graph = _graph()
    # A second entrypoint into the same downstream chain.
    graph["nodes"].append(
        {"id": "py:api.claim_batch", "kind": "function", "file": "src/api.py",
         "span": {"start": 90, "end": 110}, "name": "claim_batch"}
    )
    graph["entrypoints"].append({"node_id": "py:api.claim_batch", "kind": "route"})
    graph["edges"].append(
        {"from": "py:api.claim_batch", "to": "py:svc.lock", "type": "call",
         "confidence": "high", "evidence": "ast"}
    )

    seeds = seed_behaviors(graph)
    merged = [
        c for c in seeds["clusters"]
        if "py:api.claim_task" in c["member_nodes"]
        and "py:api.claim_batch" in c["member_nodes"]
    ]

    assert len(merged) == 1, "overlapping entrypoint chains should merge into one cluster"
    assert sorted(merged[0]["roots"]) == ["py:api.claim_batch", "py:api.claim_task"]


def test_disjoint_clusters_do_not_merge() -> None:
    seeds = seed_behaviors(_graph())

    claim = next(c for c in seeds["clusters"] if "py:api.claim_task" in c["member_nodes"])
    report = next(c for c in seeds["clusters"] if "py:api.report" in c["member_nodes"])

    assert claim["id"] != report["id"]


# --------------------------------------------------------------------------- #
# R6 — uncovered accounting
# --------------------------------------------------------------------------- #
def test_entrypoint_with_no_downstream_is_uncovered() -> None:
    seeds = seed_behaviors(_graph())

    uncovered = {u["node_id"]: u for u in seeds["uncovered"]}
    assert "py:api.health" in uncovered
    assert uncovered["py:api.health"]["reason"] == UNCOVERED_NO_TRACED_FLOW


def test_every_entrypoint_is_covered_or_accounted_for() -> None:
    graph = _graph()
    seeds = seed_behaviors(graph)

    clustered = {n for c in seeds["clusters"] for n in c["member_nodes"]}
    uncovered = {u["node_id"] for u in seeds["uncovered"]}

    for entry in graph["entrypoints"]:
        node_id = entry["node_id"]
        assert node_id in clustered or node_id in uncovered


def test_summary_reports_uncovered_count() -> None:
    seeds = seed_behaviors(_graph())
    assert seeds["summary"]["uncovered_entrypoints"] == len(seeds["uncovered"])
    assert seeds["summary"]["clusters"] == len(seeds["clusters"])


# --------------------------------------------------------------------------- #
# Hub annotation (D4 step 3) and exception attachment (D4 step 4)
# --------------------------------------------------------------------------- #
def test_high_impact_nodes_annotate_owning_cluster() -> None:
    high_impact = {"high_impact_nodes": [
        {"node_id": "py:svc.lock", "score": 9.5},
        {"node_id": "py:nowhere", "score": 1.0},
    ]}

    seeds = seed_behaviors(_graph(), high_impact=high_impact)
    claim = next(c for c in seeds["clusters"] if "py:svc.lock" in c["member_nodes"])

    assert "py:svc.lock" in claim["hubs"]
    assert all("py:nowhere" not in c["hubs"] for c in seeds["clusters"])


def test_exception_patterns_attach_to_owning_cluster() -> None:
    enrichment = {
        "exception_patterns": [
            {"node_id": "py:svc.lock", "file": "src/svc.py", "line": 12,
             "exception_type": "LockTimeout", "handler": "retry"},
            {"node_id": "py:orphan", "file": "src/x.py", "line": 1,
             "exception_type": "ValueError"},
        ]
    }

    seeds = seed_behaviors(_graph(), enrichment=enrichment)
    claim = next(c for c in seeds["clusters"] if "py:svc.lock" in c["member_nodes"])

    assert len(claim["exception_patterns"]) == 1
    assert claim["exception_patterns"][0]["exception_type"] == "LockTimeout"


def test_real_enrichment_schema_is_understood() -> None:
    """The committed enrichment artifact groups findings, it does not flatten them.

    Shape: ``{python_patterns: {broad_except: {count, items: [{file, line,
    enclosing_node}]}}}`` — an ``exception_patterns[]`` list never appears.
    """
    enrichment = {
        "python_patterns": {
            "bare_except": {"count": 0, "items": []},
            "broad_except": {"count": 1, "items": [
                {"file": "svc.py", "line": 12, "enclosing_node": "py:svc.lock"}
            ]},
        },
        "typescript_patterns": {"empty_catch": {"count": 0, "items": []}},
    }

    seeds = seed_behaviors(_graph(), enrichment=enrichment,
                           source_roots={"python": "src"})
    claim = next(c for c in seeds["clusters"] if "py:svc.lock" in c["member_nodes"])

    assert len(claim["exception_patterns"]) == 1
    assert claim["exception_patterns"][0]["exception_type"] == "broad_except"
    assert claim["exception_patterns"][0]["file"] == "src/svc.py"


def test_enrichment_without_exception_groups_is_harmless() -> None:
    seeds = seed_behaviors(_graph(), enrichment={"comments": {"total": 3}})
    assert all(c["exception_patterns"] == [] for c in seeds["clusters"])


def test_exception_patterns_keyed_by_file_also_attach() -> None:
    enrichment = {
        "exception_patterns": [
            {"file": "src/db.py", "line": 9, "exception_type": "IntegrityError"},
        ]
    }

    seeds = seed_behaviors(_graph(), enrichment=enrichment)
    claim = next(c for c in seeds["clusters"] if "py:db.write" in c["member_nodes"])

    assert any(p["exception_type"] == "IntegrityError"
               for p in claim["exception_patterns"])


# --------------------------------------------------------------------------- #
# Scoping
# --------------------------------------------------------------------------- #
def test_scope_prefix_limits_clusters_to_matching_files() -> None:
    graph = _graph()
    graph["nodes"].append(
        {"id": "py:other.thing", "kind": "function", "file": "other/thing.py",
         "span": {"start": 1, "end": 5}, "name": "thing"}
    )
    graph["entrypoints"].append({"node_id": "py:other.thing", "kind": "route"})

    seeds = seed_behaviors(graph, scope=["src/"])

    all_members = {n for c in seeds["clusters"] for n in c["member_nodes"]}
    assert "py:other.thing" not in all_members
    assert "py:other.thing" not in {u["node_id"] for u in seeds["uncovered"]}
