"""Candidate digest storage, ranking, and publication behavior."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "supervise" / "scripts"
SCHEMAS = REPO_ROOT / "openspec" / "schemas"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cycle_state import compute_fingerprint  # noqa: E402
from digest import (  # noqa: E402
    CandidateCapacityError,
    MAX_JOURNAL_BYTES,
    MAX_JOURNAL_OPERATIONS,
    decide,
    decode_stub_key,
    encode_stub_key,
    prepare_batch,
    publish_transaction,
    rank_candidates,
    recover_transaction,
    store_candidates,
)

NOW = "2026-09-16T00:00:00Z"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _stub(number: int) -> dict:
    return {
        "schema_version": 1,
        "title": f"Candidate {number}",
        "description": "A bounded unit of candidate work.",
        "rationale": "Evidence supports doing it.",
        "provenance": {
            "source_artifact": "reports/findings.md",
            "finding_ids": [f"F-{number}"],
            "generator": "bug-scrub",
        },
        "effort": "S",
        "priority": number + 1,
        "suggested_change_id": f"add-candidate-{number}",
    }


def _record(entries: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "written_at": "2026-09-11T01:00:00Z",
        "pending_gates": [],
        "standing_decisions": [],
        "back_edge": {
            "last_digest_at": "2026-09-11T01:00:00Z",
            "last_fingerprint": "a" * 64,
            "digested_stubs": entries,
        },
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    schema_dir = root / "openspec" / "schemas"
    schema_dir.mkdir(parents=True)
    for name in (
        "candidate-work.schema.json",
        "supervise-digest.schema.json",
        "supervise-rubric-score.schema.json",
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
    ):
        shutil.copy2(SCHEMAS / name, schema_dir / name)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")
    return root


@pytest.mark.parametrize(
    "key",
    ["change:add-candidate-digest", "prov:0123456789abcdef0123456789abcdef"],
)
def test_stub_key_filename_encoding_is_strict_and_reversible(key: str) -> None:
    encoded = encode_stub_key(key)
    assert decode_stub_key(encoded) == key
    assert ":" not in encoded


@pytest.mark.parametrize(
    "key",
    [
        "change:feature",
        "change:Add-feature",
        "change:add-feature/escape",
        "prov:0123",
        "prov:0123456789ABCDEF0123456789ABCDEF",
        "../../outside",
    ],
)
def test_stub_key_filename_encoding_rejects_noncanonical_keys(key: str) -> None:
    with pytest.raises(ValueError, match="canonical stub key"):
        encode_stub_key(key)


def test_store_merges_retained_and_fresh_with_byte_stable_files(repo: Path) -> None:
    retained, fresh = _stub(1), _stub(2)
    first = store_candidates(repo, [retained], record=_record([]), as_of=NOW)
    retained_path = repo / first["stored"][0]["path"]
    first_bytes = retained_path.read_bytes()

    second = store_candidates(repo, [fresh], record=_record([]), as_of=NOW)

    assert second["retained_keys"] == ["change:add-candidate-1"]
    assert second["fresh_keys"] == ["change:add-candidate-2"]
    assert retained_path.read_bytes() == first_bytes
    assert retained_path.read_bytes().endswith(b"\n")
    assert json.loads(retained_path.read_text(encoding="utf-8")) == retained


def test_store_capacity_failure_is_atomic_and_names_every_overflow(repo: Path) -> None:
    store_candidates(repo, [_stub(i) for i in range(20)], record=_record([]), as_of=NOW)
    before = {
        path.name: path.read_bytes()
        for path in (repo / "openspec/supervise/candidates").glob("*.json")
    }

    with pytest.raises(CandidateCapacityError) as caught:
        store_candidates(repo, [_stub(20), _stub(21)], record=_record([]), as_of=NOW)

    assert caught.value.unpersisted_keys == [
        "change:add-candidate-20",
        "change:add-candidate-21",
    ]
    assert {
        path.name: path.read_bytes()
        for path in (repo / "openspec/supervise/candidates").glob("*.json")
    } == before


def test_terminal_prune_and_due_deferral_run_before_capacity_check(repo: Path) -> None:
    store_candidates(repo, [_stub(i) for i in range(20)], record=_record([]), as_of=NOW)
    entries = [
        {
            "stub_key": "change:add-candidate-0",
            "rank": 1,
            "decision": "approved",
            "decided_at": "2026-09-12T00:00:00Z",
            "route": "plan-roadmap",
            "roadmap_ref": None,
        },
        {
            "stub_key": "change:add-candidate-1",
            "rank": 2,
            "decision": "deferred",
            "decided_at": "2026-09-12T00:00:00Z",
            "until": "2026-09-15",
        },
    ]

    result = store_candidates(repo, [_stub(20)], record=_record(entries), as_of=NOW)

    assert result["lifecycle_changed"] is True
    assert result["pruned_keys"] == ["change:add-candidate-0"]
    assert result["woken_keys"] == ["change:add-candidate-1"]
    assert "change:add-candidate-20" in result["fresh_keys"]
    assert not (repo / "openspec/supervise/candidates/change--add-candidate-0.json").exists()


def test_maintained_baseline_survives_later_capacity_failure(repo: Path) -> None:
    store_candidates(repo, [_stub(i) for i in range(20)], record=_record([]), as_of=NOW)
    terminal = {
        "stub_key": "change:add-candidate-0",
        "rank": 1,
        "decision": "rejected",
        "decided_at": "2026-09-12T00:00:00Z",
        "reason": "Superseded",
    }

    with pytest.raises(CandidateCapacityError):
        store_candidates(
            repo,
            [_stub(20), _stub(21)],
            record=_record([terminal]),
            as_of=NOW,
        )

    names = sorted(path.name for path in (repo / "openspec/supervise/candidates").glob("*.json"))
    assert "change--add-candidate-0.json" not in names
    assert len(names) == 19


def test_lifecycle_prunes_terminal_even_when_surviving_store_entry_is_unscored(
    repo: Path,
) -> None:
    scored, unscored = _stub(0), _stub(1)
    store_candidates(repo, [scored], record=_record([]), as_of=NOW)
    manifest = _manifest([scored])
    rank_candidates(repo, manifest, _scores(manifest), record=_record([]), fresh_keys=[])
    store_candidates(repo, [unscored], record=_record([]), as_of=NOW)
    mirror = json.loads((repo / "openspec/supervise/supervisor-record.json").read_text())
    terminal = decide(
        repo,
        "change:add-candidate-0",
        decision="rejected",
        record=mirror,
        as_of=NOW,
        reason="Already covered",
    )

    result = store_candidates(repo, [], record=terminal, as_of=NOW, prune_only=True)

    assert result["pruned_keys"] == ["change:add-candidate-0"]
    assert (repo / "openspec/supervise/candidates/change--add-candidate-1.json").exists()
    assert not (repo / "openspec/supervise/candidates/change--add-candidate-0.json").exists()
    manifest = prepare_batch(repo, fingerprint="b" * 64, as_of=NOW, record=terminal)
    assert manifest["requested_keys"] == ["change:add-candidate-1"]


def test_dry_run_refuses_pending_recovery_without_writes(repo: Path) -> None:
    store_candidates(repo, [_stub(0)], record=_record([]), as_of=NOW)
    candidate = repo / "openspec/supervise/candidates/change--add-candidate-0.json"
    journal = repo / "openspec/supervise/.digest-transaction.json"
    journal.write_text('{"operations": []}\n', encoding="utf-8")
    before = candidate.read_bytes()
    terminal = {
        "stub_key": "change:add-candidate-0",
        "rank": 1,
        "decision": "rejected",
        "decided_at": "2026-09-12T00:00:00Z",
        "reason": "No longer relevant",
    }

    with pytest.raises(ValueError, match="pending digest transaction recovery"):
        store_candidates(
            repo, [], record=_record([terminal]), as_of=NOW, dry_run=True, prune_only=True
        )

    assert candidate.read_bytes() == before
    assert journal.exists()


def test_mutating_command_recovers_pending_transaction_then_requires_rehydrate(
    repo: Path,
) -> None:
    stale = _record(
        [
            {
                "stub_key": "change:add-candidate-0",
                "rank": 1,
                "decision": "pending",
                "decided_at": "2026-09-11T01:00:00Z",
                "suggested_change_id": "add-candidate-0",
            }
        ]
    )
    recovered = _record(
        [
            {
                "stub_key": "change:add-candidate-9",
                "rank": 1,
                "decision": "pending",
                "decided_at": "2026-09-12T01:00:00Z",
                "suggested_change_id": "add-candidate-9",
            }
        ]
    )
    publish_transaction(
        repo,
        [
            {
                "op": "replace",
                "target": "openspec/supervise/supervisor-record.json",
                "bytes": json.dumps(recovered, indent=2, sort_keys=True) + "\n",
            }
        ],
        apply=False,
    )

    with pytest.raises(ValueError, match="rehydrate and retry"):
        store_candidates(repo, [_stub(0)], record=stale, as_of=NOW)

    persisted = json.loads((repo / "openspec/supervise/supervisor-record.json").read_text())
    assert persisted["back_edge"]["digested_stubs"][0]["stub_key"] == "change:add-candidate-9"
    assert not (repo / "openspec/supervise/.digest-transaction.json").exists()


def test_supervisor_outputs_do_not_change_cycle_fingerprint(repo: Path) -> None:
    before = compute_fingerprint(repo)
    store_candidates(repo, [_stub(0)], record=_record([]), as_of=NOW)
    supervise = repo / "openspec/supervise"
    (supervise / "rubric-cache").mkdir()
    (supervise / "rubric-cache/change--add-candidate-0.rubric.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (supervise / "digest.json").write_text("{}\n", encoding="utf-8")
    (supervise / ".digest-transaction.json").write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "supervisor outputs")

    assert compute_fingerprint(repo) == before


FACTORS = ("relevance", "value", "readiness", "scope_fit", "risk")


def _manifest(stubs: list[dict], *, fingerprint: str = "a" * 64) -> dict:
    return {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "as_of": "2026-09-11T01:00:00Z",
        "requested_keys": [f"change:{stub['suggested_change_id']}" for stub in stubs],
        "candidates": [
            {
                "stub_key": f"change:{stub['suggested_change_id']}",
                "stub": stub,
                "signals": {
                    "dependency_ready": True,
                    "staleness_days": 0,
                    "prior_decision": None,
                    "deferred_until": None,
                },
                "degraded": [],
            }
            for stub in stubs
        ],
    }


def _scores(manifest: dict, *, values: dict[str, int] | None = None) -> dict:
    values = values or {}
    return {
        "schema_version": 1,
        "fingerprint": manifest["fingerprint"],
        "scored_at": manifest["as_of"],
        "scorer": {"vendor": "test", "model": "test", "archetype": "analyst"},
        "scores": [
            {
                "stub_key": key,
                **{
                    factor: {
                        "score": values.get(factor, 3),
                        "justification": f"{factor} evidence",
                    }
                    for factor in FACTORS
                },
                "evidence_read": [],
            }
            for key in manifest["requested_keys"]
        ],
    }


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("fingerprint", "fingerprint"),
        ("missing", "missing"),
        ("unknown", "unknown"),
        ("duplicate", "duplicate"),
        ("timestamp", "scored_at"),
    ],
)
def test_rank_rejects_manifest_score_mismatches_without_writes(
    repo: Path, mutation: str, match: str
) -> None:
    stub = _stub(0)
    store_candidates(repo, [stub], record=_record([]), as_of=NOW)
    manifest = _manifest([stub])
    scores = _scores(manifest)
    if mutation == "fingerprint":
        scores["fingerprint"] = "b" * 64
    elif mutation == "missing":
        scores["scores"] = []
    elif mutation == "unknown":
        scores["scores"][0]["stub_key"] = "change:add-unknown"
    elif mutation == "duplicate":
        scores["scores"].append(dict(scores["scores"][0]))
    else:
        scores["scored_at"] = "2026-09-11T01:00:01Z"

    with pytest.raises((ValueError, Exception), match=match):
        rank_candidates(repo, manifest, scores, record=_record([]), fresh_keys=[])

    assert not (repo / "openspec/supervise/digest.json").exists()
    assert not (repo / "openspec/supervise/.digest-transaction.json").exists()


@pytest.mark.parametrize(
    "scored_at",
    [None, "2026-09-11T00:59:59Z", "2026-09-11T01:00:01Z", "2026-09-11T01:00:00"],
)
def test_rank_rejects_any_nonexact_or_naive_scoring_time(repo: Path, scored_at: str | None) -> None:
    stub = _stub(0)
    store_candidates(repo, [stub], record=_record([]), as_of=NOW)
    manifest = _manifest([stub])
    scores = _scores(manifest)
    if scored_at is None:
        del scores["scored_at"]
    else:
        scores["scored_at"] = scored_at
    with pytest.raises(Exception, match="scored_at"):
        rank_candidates(repo, manifest, scores, record=_record([]), fresh_keys=[])


def test_rank_uses_formula_policy_buckets_and_stable_key_tie_break(repo: Path) -> None:
    stubs = [_stub(2), _stub(1), _stub(0)]
    store_candidates(repo, stubs, record=_record([]), as_of=NOW)
    manifest = _manifest(stubs)
    manifest["candidates"][0]["signals"].update(
        {"prior_decision": "deferred", "deferred_until": "2026-12-01"}
    )
    manifest["candidates"][1]["signals"]["dependency_ready"] = False
    scores = _scores(
        manifest, values={"relevance": 5, "value": 4, "readiness": 3, "scope_fit": 2, "risk": 5}
    )
    scores["scores"] = list(reversed(scores["scores"]))
    record = _record(
        [
            {
                "stub_key": "change:add-candidate-2",
                "rank": 1,
                "decision": "deferred",
                "decided_at": "2026-09-10T00:00:00Z",
                "until": "2026-12-01",
            }
        ]
    )

    digest = rank_candidates(repo, manifest, scores, record=record, fresh_keys=[])

    assert [item["stub_key"] for item in digest["ranked"]] == [
        "change:add-candidate-0",
        "change:add-candidate-1",
        "change:add-candidate-2",
    ]
    assert digest["ranked"][0]["score"] == 40
    assert digest["weights"] == {
        "relevance": 3,
        "value": 3,
        "readiness": 2,
        "scope_fit": 1,
        "risk": 1,
        "staleness_penalty_per_30d": 1,
        "staleness_penalty_cap": 5,
        "risk_higher_is_safer": True,
        "decision_bucket_order": ["pending", "future_deferred"],
        "dependency_bucket_order": ["ready", "blocked"],
        "tie_breaker": "stub_key:asc",
    }
    assert digest["generated_at"] == manifest["as_of"]
    assert digest["state_updated_at"] == manifest["as_of"]


def test_rank_assigns_candidate_sections_writes_singleton_caches_and_syncs_mirror(
    repo: Path,
) -> None:
    stubs = [_stub(0), _stub(1)]
    store_candidates(repo, stubs, record=_record([]), as_of=NOW)
    manifest = _manifest(stubs)

    digest = rank_candidates(
        repo,
        manifest,
        _scores(manifest),
        record=_record([]),
        fresh_keys=["change:add-candidate-1"],
    )

    assert digest["sections"]["new_this_cycle"] == ["change:add-candidate-1"]
    assert digest["sections"]["needs_decision"] == ["change:add-candidate-0"]
    for key in manifest["requested_keys"]:
        cache = repo / f"openspec/supervise/rubric-cache/{encode_stub_key(key)}.rubric.json"
        cached = json.loads(cache.read_text(encoding="utf-8"))
        assert cached["fingerprint"] == manifest["fingerprint"]
        assert cached["scored_at"] == manifest["as_of"]
        assert [score["stub_key"] for score in cached["scores"]] == [key]
    mirror = json.loads(
        (repo / "openspec/supervise/supervisor-record.json").read_text(encoding="utf-8")
    )
    entries = mirror["back_edge"]["digested_stubs"]
    assert [entry["stub_key"] for entry in entries] == [
        item["stub_key"] for item in digest["ranked"]
    ]
    assert all(entry["decision"] == "pending" for entry in entries)


def test_force_same_fingerprint_reuses_prior_digest_and_cache_without_new_scoring(
    repo: Path,
) -> None:
    stubs = [_stub(0), _stub(1)]
    store_candidates(repo, stubs, record=_record([]), as_of=NOW)
    first_manifest = _manifest(stubs)
    first_digest = rank_candidates(
        repo, first_manifest, _scores(first_manifest), record=_record([]), fresh_keys=[]
    )
    first_bytes = (repo / "openspec/supervise/digest.json").read_bytes()
    later_manifest = prepare_batch(
        repo,
        fingerprint=first_manifest["fingerprint"],
        as_of="2026-09-12T03:04:05Z",
        record=json.loads((repo / "openspec/supervise/supervisor-record.json").read_text()),
    )

    reused = rank_candidates(repo, later_manifest, None, record=_record([]), fresh_keys=[])

    assert reused == first_digest
    assert reused["generated_at"] == first_manifest["as_of"]
    assert (repo / "openspec/supervise/digest.json").read_bytes() == first_bytes


def test_rank_rejects_stale_manifest_when_store_candidate_bytes_changed(repo: Path) -> None:
    original = _stub(0)
    store_candidates(repo, [original], record=_record([]), as_of=NOW)
    stale_manifest = prepare_batch(repo, fingerprint="a" * 64, as_of=NOW, record=_record([]))
    refreshed = {**original, "description": "Different candidate bytes"}
    store_candidates(repo, [refreshed], record=_record([]), as_of=NOW)

    with pytest.raises(ValueError, match="manifest candidate does not match current store"):
        rank_candidates(
            repo, stale_manifest, _scores(stale_manifest), record=_record([]), fresh_keys=[]
        )

    assert not (repo / "openspec/supervise/digest.json").exists()


def test_rank_rejects_stale_nonempty_manifest_when_store_is_emptied(repo: Path) -> None:
    stub = _stub(0)
    store_candidates(repo, [stub], record=_record([]), as_of=NOW)
    stale_manifest = prepare_batch(repo, fingerprint="a" * 64, as_of=NOW, record=_record([]))
    (repo / "openspec/supervise/candidates/change--add-candidate-0.json").unlink()

    with pytest.raises(ValueError, match="manifest candidate keys do not match current store"):
        rank_candidates(
            repo, stale_manifest, _scores(stale_manifest), record=_record([]), fresh_keys=[]
        )

    assert not (repo / "openspec/supervise/digest.json").exists()
    assert not (repo / "openspec/supervise/.digest-transaction.json").exists()


def test_rank_normalizes_due_deferral_from_stale_record(repo: Path) -> None:
    stub = _stub(0)
    store_candidates(repo, [stub], record=_record([]), as_of=NOW)
    stale_record = _record(
        [
            {
                "stub_key": "change:add-candidate-0",
                "rank": 1,
                "decision": "deferred",
                "decided_at": "2026-09-10T00:00:00Z",
                "until": "2026-09-15",
            }
        ]
    )
    manifest = prepare_batch(repo, fingerprint="a" * 64, as_of=NOW, record=stale_record)

    digest = rank_candidates(repo, manifest, _scores(manifest), record=stale_record, fresh_keys=[])

    assert digest["ranked"][0]["decision"] == "pending"
    assert digest["ranked"][0]["signals"]["deferred_until"] is None
    mirror = json.loads((repo / "openspec/supervise/supervisor-record.json").read_text())
    assert mirror["back_edge"]["digested_stubs"][0]["decision"] == "pending"
    assert "until" not in mirror["back_edge"]["digested_stubs"][0]


def test_zero_candidate_batch_publishes_valid_empty_digest_without_scores(repo: Path) -> None:
    manifest = prepare_batch(repo, fingerprint="a" * 64, as_of=NOW, record=_record([]))

    digest = rank_candidates(repo, manifest, None, record=_record([]), fresh_keys=[])

    assert manifest["requested_keys"] == []
    assert digest["ranked"] == []
    assert digest["sections"] == {
        "needs_decision": [],
        "new_this_cycle": [],
        "degraded": [],
    }
    persisted = json.loads((repo / "openspec/supervise/digest.json").read_text())
    assert persisted == digest


def test_ranking_is_byte_identical_for_shuffled_input(repo: Path) -> None:
    stubs = [_stub(0), _stub(1)]
    store_candidates(repo, stubs, record=_record([]), as_of=NOW)
    first_manifest = _manifest(stubs)
    first = rank_candidates(
        repo, first_manifest, _scores(first_manifest), record=_record([]), fresh_keys=[]
    )
    first_bytes = (repo / "openspec/supervise/digest.json").read_bytes()

    second_manifest = _manifest(list(reversed(stubs)))
    second_manifest["requested_keys"].sort()
    second_manifest["candidates"].sort(key=lambda item: item["stub_key"])
    second_scores = _scores(second_manifest)
    second_scores["scores"].reverse()
    second = rank_candidates(
        repo, second_manifest, second_scores, record=_record([]), fresh_keys=[]
    )

    assert second == first
    assert (repo / "openspec/supervise/digest.json").read_bytes() == first_bytes


def test_recovery_rolls_forward_deletes_and_replacements_with_digest_last(
    repo: Path,
) -> None:
    doomed = repo / "openspec/supervise/candidates/change--add-old.json"
    doomed.parent.mkdir(parents=True)
    doomed.write_text("old\n", encoding="utf-8")
    operations = [
        {"op": "delete", "target": doomed.relative_to(repo).as_posix()},
        {
            "op": "replace",
            "target": "openspec/supervise/rubric-cache/change--add-old.rubric.json",
            "bytes": "cache\n",
        },
        {
            "op": "replace",
            "target": "openspec/supervise/digest.json",
            "bytes": "digest\n",
        },
    ]
    publish_transaction(repo, operations, apply=False)

    assert recover_transaction(repo) is True
    assert not doomed.exists()
    assert (
        repo / "openspec/supervise/rubric-cache/change--add-old.rubric.json"
    ).read_text() == "cache\n"
    assert (repo / "openspec/supervise/digest.json").read_text() == "digest\n"
    assert not (repo / "openspec/supervise/.digest-transaction.json").exists()


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "replace", "target": "README.md", "bytes": "owned\n"},
        {"op": "delete", "target": "README.md"},
        {
            "op": "replace",
            "target": "openspec/supervise/candidates/not-canonical.json",
            "bytes": "{}\n",
        },
        {"op": "delete", "target": "openspec/supervise/digest.json"},
    ],
)
def test_transaction_refuses_targets_outside_owned_artifacts_and_wrong_operations(
    repo: Path, operation: dict
) -> None:
    readme = repo / "README.md"
    before = readme.read_bytes()

    with pytest.raises(ValueError, match="unauthorized digest transaction target"):
        publish_transaction(repo, [operation])

    assert readme.read_bytes() == before
    assert not (repo / "openspec/supervise/.digest-transaction.json").exists()


def test_recovery_refuses_a_tampered_journal_target_before_mutating_any_file(
    repo: Path,
) -> None:
    journal = repo / "openspec/supervise/.digest-transaction.json"
    cache = repo / "openspec/supervise/rubric-cache/change--add-safe.rubric.json"
    journal.parent.mkdir(parents=True)
    cache_content = "safe cache\n"
    tampered_content = "tampered\n"
    journal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "replace",
                        "target": cache.relative_to(repo).as_posix(),
                        "bytes": cache_content,
                        "sha256": hashlib.sha256(cache_content.encode()).hexdigest(),
                    },
                    {
                        "op": "replace",
                        "target": "skills/tampered.py",
                        "bytes": tampered_content,
                        "sha256": hashlib.sha256(tampered_content.encode()).hexdigest(),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = (repo / "README.md").read_bytes()

    with pytest.raises(ValueError, match="unauthorized digest transaction target"):
        recover_transaction(repo)

    assert (repo / "README.md").read_bytes() == before
    assert not cache.exists()
    assert journal.exists()


def test_dry_run_fresh_overlay_is_available_to_batch_without_persistence(
    repo: Path,
) -> None:
    fresh = _stub(0)
    result = store_candidates(repo, [fresh], record=_record([]), as_of=NOW, dry_run=True)

    manifest = prepare_batch(
        repo,
        fingerprint="a" * 64,
        as_of=NOW,
        record=_record([]),
        fresh_stubs=[fresh],
    )

    assert result["fresh_keys"] == ["change:add-candidate-0"]
    assert manifest["requested_keys"] == ["change:add-candidate-0"]
    assert not (repo / "openspec/supervise/candidates").exists()


def test_store_refreshes_changed_same_key_and_invalidates_its_cache(repo: Path) -> None:
    original = _stub(0)
    store_candidates(repo, [original], record=_record([]), as_of=NOW)
    key = "change:add-candidate-0"
    cache = repo / f"openspec/supervise/rubric-cache/{encode_stub_key(key)}.rubric.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{}\n", encoding="utf-8")
    refreshed = {**original, "title": "Refreshed candidate"}

    result = store_candidates(repo, [refreshed], record=_record([]), as_of=NOW)

    stored = json.loads(
        (repo / "openspec/supervise/candidates/change--add-candidate-0.json").read_text()
    )
    assert stored["title"] == "Refreshed candidate"
    assert result["fresh_keys"] == [key]
    assert not cache.exists()


@pytest.mark.parametrize("mutation", ["fingerprint", "stub_key"])
def test_lifecycle_rebuild_rejects_cache_with_wrong_identity(repo: Path, mutation: str) -> None:
    stubs = [_stub(0), _stub(1)]
    store_candidates(repo, stubs, record=_record([]), as_of=NOW)
    manifest = _manifest(stubs)
    rank_candidates(repo, manifest, _scores(manifest), record=_record([]), fresh_keys=[])
    mirror = json.loads((repo / "openspec/supervise/supervisor-record.json").read_text())
    approved = decide(
        repo,
        "change:add-candidate-0",
        decision="approved",
        record=mirror,
        as_of=NOW,
        route="plan-roadmap",
    )
    cache = repo / "openspec/supervise/rubric-cache/change--add-candidate-1.rubric.json"
    payload = json.loads(cache.read_text())
    if mutation == "fingerprint":
        payload["fingerprint"] = "b" * 64
    else:
        payload["scores"][0]["stub_key"] = "change:add-candidate-9"
    cache.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="lifecycle cache"):
        store_candidates(repo, [], record=approved, as_of=NOW, prune_only=True)


def test_terminal_decisions_remain_in_durable_history_after_pruning(repo: Path) -> None:
    stubs = [_stub(0), _stub(1)]
    store_candidates(repo, stubs, record=_record([]), as_of=NOW)
    manifest = _manifest(stubs)
    rank_candidates(repo, manifest, _scores(manifest), record=_record([]), fresh_keys=[])
    mirror = json.loads((repo / "openspec/supervise/supervisor-record.json").read_text())
    approved = decide(
        repo,
        "change:add-candidate-0",
        decision="approved",
        record=mirror,
        as_of=NOW,
        route="plan-roadmap",
    )

    store_candidates(repo, [], record=approved, as_of=NOW, prune_only=True)

    persisted = json.loads((repo / "openspec/supervise/supervisor-record.json").read_text())
    by_key = {entry["stub_key"]: entry for entry in persisted["back_edge"]["digested_stubs"]}
    assert by_key["change:add-candidate-0"]["decision"] == "approved"
    assert by_key["change:add-candidate-1"]["decision"] == "pending"


def test_transaction_journal_operation_count_is_bounded(repo: Path) -> None:
    operations = [
        {
            "op": "delete",
            "target": (
                f"openspec/supervise/rubric-cache/change--add-candidate-{index}.rubric.json"
            ),
        }
        for index in range(MAX_JOURNAL_OPERATIONS + 1)
    ]

    with pytest.raises(ValueError, match="too many digest transaction operations"):
        publish_transaction(repo, operations)

    assert not (repo / "openspec/supervise/.digest-transaction.json").exists()


def test_recovery_refuses_an_oversized_journal_before_parsing(repo: Path) -> None:
    journal = repo / "openspec/supervise/.digest-transaction.json"
    journal.parent.mkdir(parents=True)
    journal.write_bytes(b" " * (MAX_JOURNAL_BYTES + 1))

    with pytest.raises(ValueError, match="journal exceeds size limit"):
        recover_transaction(repo)

    assert journal.exists()
