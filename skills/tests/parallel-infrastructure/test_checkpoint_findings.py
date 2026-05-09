"""Tests for checkpoint_findings.py — the durable vendor-findings cache helper.

Encodes the spec scenarios from skill-workflow.R1.* (vendor-findings checkpoint
layout) and skill-workflow.R5.* (checkpoint path safety). Tests live here
(not inside the shipped skill dir) so install.sh's rsync excludes them
from runtime mirrors.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

# checkpoint_findings is on sys.path via conftest.py's SKILL_SCRIPTS injection
import checkpoint_findings  # type: ignore[import-untyped]
from checkpoint_findings import (  # type: ignore[import-untyped]
    MANIFEST_SCHEMA_VERSION,
    _atomic_write_json,
    _safe_log_error,
    _validate_finding,
    _validate_path_safety,
    read_manifest,
    read_vendor_findings,
    write_manifest,
    write_vendor_findings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def good_finding() -> dict[str, Any]:
    return {
        "id": 1,
        "type": "logic-error",
        "criticality": "high",
        "description": "Off-by-one in pagination",
        "disposition": "fix",
    }


@pytest.fixture
def good_finding_with_optionals(good_finding: dict[str, Any]) -> dict[str, Any]:
    out = dict(good_finding)
    out.update({
        "resolution": "Use range(0, n)",
        "file_path": "src/paginate.py",
        "line_range": {"start": 12, "end": 14},
        "vendor": "claude_code",
    })
    return out


# ---------------------------------------------------------------------------
# R1.S1 — round-trip (write then read back via manifest)
# ---------------------------------------------------------------------------


def test_round_trip_single_vendor(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    write_vendor_findings(
        tmp_path,
        vendor="claude_code",
        review_type="plan",
        target="my-feature",
        findings=[good_finding],
    )
    write_manifest(
        tmp_path,
        review_type="plan",
        target="my-feature",
        vendors=[{
            "name": "claude_code",
            "findings_path": "findings-claude_code-plan.json",
            "finding_count": 1,
        }],
        change_id="my-feature",
    )

    loaded = read_vendor_findings(tmp_path)
    assert set(loaded) == {"claude_code"}
    assert loaded["claude_code"] == [good_finding]


def test_round_trip_multi_vendor(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    vendors_index: list[dict[str, Any]] = []
    for vendor_name in ("claude_code", "codex", "gemini"):
        write_vendor_findings(
            tmp_path,
            vendor=vendor_name,
            review_type="implementation",
            target="my-feature",
            findings=[good_finding],
        )
        vendors_index.append({
            "name": vendor_name,
            "findings_path": f"findings-{vendor_name}-implementation.json",
            "finding_count": 1,
        })
    write_manifest(
        tmp_path,
        review_type="implementation",
        target="my-feature",
        vendors=vendors_index,
        change_id="my-feature",
    )

    loaded = read_vendor_findings(tmp_path)
    assert set(loaded) == {"claude_code", "codex", "gemini"}
    for findings in loaded.values():
        assert findings == [good_finding]


# ---------------------------------------------------------------------------
# R1.S2 — manifest is sufficient (read_vendor_findings uses it as the index)
# ---------------------------------------------------------------------------


def test_read_uses_manifest_index_not_glob(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    """A stray findings-*.json not in the manifest is NOT loaded by read_vendor_findings."""
    write_vendor_findings(
        tmp_path,
        vendor="claude_code",
        review_type="plan",
        target="my-feature",
        findings=[good_finding],
    )
    # Stray file not referenced in manifest
    stray_payload = {
        "review_type": "plan",
        "target": "my-feature",
        "reviewer_vendor": "stray",
        "findings": [good_finding],
    }
    (tmp_path / "findings-stray-plan.json").write_text(json.dumps(stray_payload))

    write_manifest(
        tmp_path,
        review_type="plan",
        target="my-feature",
        vendors=[{
            "name": "claude_code",
            "findings_path": "findings-claude_code-plan.json",
            "finding_count": 1,
        }],
    )

    loaded = read_vendor_findings(tmp_path)
    assert set(loaded) == {"claude_code"}
    assert "stray" not in loaded


# ---------------------------------------------------------------------------
# R1.S3 — manifest preserves existing dispatcher fields
# ---------------------------------------------------------------------------


def test_manifest_has_legacy_fields(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        review_type="plan",
        target="cli-dispatch",
        vendors=[],
        dispatches=[
            {"vendor": "claude_code", "success": True, "model_used": "opus", "elapsed_seconds": 1.2},
            {"vendor": "codex", "success": False, "error_class": "Timeout"},
        ],
        quorum_requested=2,
        quorum_received=1,
    )
    manifest = read_manifest(tmp_path)
    # Legacy fields preserved
    assert manifest["review_type"] == "plan"
    assert manifest["target"] == "cli-dispatch"
    assert len(manifest["dispatches"]) == 2
    assert manifest["dispatches"][0]["vendor"] == "claude_code"
    assert manifest["dispatches"][1]["error_class"] == "Timeout"
    assert manifest["quorum_requested"] == 2
    assert manifest["quorum_received"] == 1
    # Plus new superset fields
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert "created_at" in manifest
    assert "vendors" in manifest


def test_manifest_change_id_optional_null(tmp_path: Path) -> None:
    """CLI callers omit change_id; manifest stores null and reads back as None."""
    write_manifest(
        tmp_path,
        review_type="plan",
        target="cli-dispatch",
        vendors=[],
    )
    manifest = read_manifest(tmp_path)
    assert manifest["change_id"] is None


def test_manifest_change_id_present(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        review_type="plan",
        target="my-feature",
        vendors=[],
        change_id="my-feature",
    )
    manifest = read_manifest(tmp_path)
    assert manifest["change_id"] == "my-feature"


# ---------------------------------------------------------------------------
# R1.S4 — in-process callers may write empty dispatches[]
# ---------------------------------------------------------------------------


def test_in_process_caller_no_dispatch_metadata(tmp_path: Path) -> None:
    """In-process converge() has no per-dispatch metadata — empty dispatches[] is valid."""
    write_manifest(
        tmp_path,
        review_type="plan",
        target="my-feature",
        vendors=[
            {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 0},
            {"name": "codex", "findings_path": "findings-codex-plan.json", "finding_count": 0},
        ],
        change_id="my-feature",
    )
    manifest = read_manifest(tmp_path)
    assert manifest["dispatches"] == []
    # Defaults derived from vendors[]
    assert manifest["quorum_requested"] == 2
    assert manifest["quorum_received"] == 2


def test_quorum_received_derived_from_dispatch_success(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        review_type="plan",
        target="x",
        vendors=[],
        dispatches=[
            {"vendor": "a", "success": True},
            {"vendor": "b", "success": False},
            {"vendor": "c", "success": True},
        ],
    )
    manifest = read_manifest(tmp_path)
    # quorum_received = count of success=True
    assert manifest["quorum_received"] == 2
    # quorum_requested defaults to len(vendors), which is 0 here
    assert manifest["quorum_requested"] == 0


# ---------------------------------------------------------------------------
# R1.S5 — atomic write (no .tmp residue, content fully present)
# ---------------------------------------------------------------------------


def test_atomic_write_no_tmp_residue(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    _atomic_write_json(target, {"hello": "world"})
    assert target.exists()
    assert json.loads(target.read_text()) == {"hello": "world"}
    # No leftover .tmp file
    assert not (tmp_path / "out.json.tmp").exists()


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    _atomic_write_json(target, {"v": 1})
    _atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 2}


def test_atomic_write_calls_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify _atomic_write_json calls os.fsync on both file and parent dir."""
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(checkpoint_findings.os, "fsync", tracking_fsync)
    _atomic_write_json(tmp_path / "out.json", {"x": 1})
    # Must call fsync at least twice: once for file, once for parent dir
    assert len(fsync_calls) >= 2


# ---------------------------------------------------------------------------
# R1.S6 — concurrent dirs (separate output_dir paths don't interfere)
# ---------------------------------------------------------------------------


def test_concurrent_dirs_isolated(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    write_vendor_findings(dir_a, vendor="claude_code", review_type="plan", target="A", findings=[good_finding])
    write_manifest(dir_a, review_type="plan", target="A", vendors=[
        {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 1},
    ])
    write_vendor_findings(dir_b, vendor="claude_code", review_type="plan", target="B", findings=[])
    write_manifest(dir_b, review_type="plan", target="B", vendors=[
        {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 0},
    ])

    assert read_vendor_findings(dir_a)["claude_code"] == [good_finding]
    assert read_vendor_findings(dir_b)["claude_code"] == []


# ---------------------------------------------------------------------------
# R1 — empty round still produces manifest
# ---------------------------------------------------------------------------


def test_empty_round_produces_manifest(tmp_path: Path) -> None:
    write_manifest(tmp_path, review_type="plan", target="x", vendors=[])
    manifest = read_manifest(tmp_path)
    assert manifest["vendors"] == []
    assert manifest["quorum_requested"] == 0
    assert manifest["quorum_received"] == 0


# ---------------------------------------------------------------------------
# R1 — missing per-vendor file caught
# ---------------------------------------------------------------------------


def test_missing_referenced_file_raises(tmp_path: Path) -> None:
    """Manifest references a file that doesn't exist — read_vendor_findings raises."""
    write_manifest(tmp_path, review_type="plan", target="x", vendors=[
        {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 1},
    ])
    # Don't write the actual findings file
    with pytest.raises(FileNotFoundError):
        read_vendor_findings(tmp_path)


# ---------------------------------------------------------------------------
# R5.S1 — artifacts_dir normalized
# ---------------------------------------------------------------------------


def test_artifacts_dir_resolves_relative(tmp_path: Path, good_finding: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative artifacts_dir is resolved to an absolute path before any write."""
    monkeypatch.chdir(tmp_path)
    rel_path = Path("relative/dir")
    fpath = write_vendor_findings(
        rel_path,
        vendor="claude_code",
        review_type="plan",
        target="x",
        findings=[good_finding],
    )
    assert fpath.is_absolute()
    assert fpath.exists()


# ---------------------------------------------------------------------------
# R5.S2 — vendor name rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_vendor", [
    "../escape",
    "vendor/with/slash",
    "vendor with spaces",
    "vendor.with.dots",
    "",
    "vendor:colon",
])
def test_vendor_name_rejected(tmp_path: Path, bad_vendor: str, good_finding: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="vendor"):
        write_vendor_findings(
            tmp_path,
            vendor=bad_vendor,
            review_type="plan",
            target="x",
            findings=[good_finding],
        )
    # Critically, no file should have been created
    assert list(tmp_path.glob("findings-*.json")) == []


def test_manifest_vendor_entry_name_rejected(tmp_path: Path) -> None:
    """Manifest's own vendors[].name is also path-safety checked."""
    with pytest.raises(ValueError, match="path-safety"):
        write_manifest(
            tmp_path,
            review_type="plan",
            target="x",
            vendors=[{"name": "../escape", "findings_path": "findings-x-plan.json", "finding_count": 0}],
        )


# ---------------------------------------------------------------------------
# R5.S3 — review_type constrained
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_review_type", ["plans", "Plan", "implementations", "", "evaluation"])
def test_review_type_rejected(tmp_path: Path, bad_review_type: str, good_finding: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="review_type"):
        write_vendor_findings(
            tmp_path,
            vendor="claude_code",
            review_type=bad_review_type,
            target="x",
            findings=[good_finding],
        )


def test_write_manifest_review_type_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="review_type"):
        write_manifest(tmp_path, review_type="bogus", target="x", vendors=[])


# ---------------------------------------------------------------------------
# R5.S4 — manifest-referenced paths stay within dir
# ---------------------------------------------------------------------------


def test_read_vendor_findings_rejects_non_object_file(tmp_path: Path) -> None:
    """A hand-edited per-vendor file that is a list (not wrapper object) is
    rejected with TypeError — guards against silently mis-reading the shape."""
    write_manifest(tmp_path, review_type="plan", target="x", vendors=[
        {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 0},
    ])
    # Hand-craft a malformed file: raw list instead of wrapper object
    (tmp_path / "findings-claude_code-plan.json").write_text(json.dumps([{"id": 1}]))
    with pytest.raises(TypeError, match="not a JSON object"):
        read_vendor_findings(tmp_path)


def test_read_manifest_rejects_non_object_file(tmp_path: Path) -> None:
    """A hand-edited manifest that is not a JSON object is rejected."""
    (tmp_path / "review-manifest.json").write_text(json.dumps([1, 2, 3]))
    with pytest.raises(TypeError, match="not a JSON object"):
        read_manifest(tmp_path)


def test_read_vendor_findings_rejects_findings_field_not_list(tmp_path: Path) -> None:
    """A per-vendor file with findings as something other than a list is rejected."""
    write_manifest(tmp_path, review_type="plan", target="x", vendors=[
        {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 0},
    ])
    bad_payload = {
        "review_type": "plan",
        "target": "x",
        "reviewer_vendor": "claude_code",
        "findings": "not-a-list",
    }
    (tmp_path / "findings-claude_code-plan.json").write_text(json.dumps(bad_payload))
    with pytest.raises(TypeError, match="findings.*list"):
        read_vendor_findings(tmp_path)


def test_read_vendor_findings_rejects_path_traversal(tmp_path: Path) -> None:
    """Manifest references a findings_path with '..' — read_vendor_findings refuses."""
    # Hand-craft a manifest with a malicious path; bypass our writer's validation
    bad_manifest = {
        "schema_version": 1,
        "change_id": None,
        "review_type": "plan",
        "created_at": "2026-05-08T00:00:00Z",
        "target": "x",
        "dispatches": [],
        "quorum_requested": 1,
        "quorum_received": 1,
        "vendors": [{"name": "claude_code", "findings_path": "../escape.json", "finding_count": 1}],
    }
    (tmp_path / "review-manifest.json").write_text(json.dumps(bad_manifest))
    with pytest.raises(ValueError, match=r"separator|escapes|safety"):
        read_vendor_findings(tmp_path)


# ---------------------------------------------------------------------------
# Per-finding validation
# ---------------------------------------------------------------------------


def test_validate_finding_required_fields(good_finding: dict[str, Any]) -> None:
    _validate_finding(good_finding)
    for missing in ("id", "type", "criticality", "description", "disposition"):
        bad = dict(good_finding)
        del bad[missing]
        with pytest.raises(ValueError, match="required"):
            _validate_finding(bad)


def test_validate_finding_criticality_enum(good_finding: dict[str, Any]) -> None:
    bad = dict(good_finding)
    bad["criticality"] = "blocking"  # not in {low,medium,high,critical}
    with pytest.raises(ValueError, match="criticality"):
        _validate_finding(bad)


def test_validate_finding_disposition_enum(good_finding: dict[str, Any]) -> None:
    bad = dict(good_finding)
    bad["disposition"] = "ignore"  # not in {fix,regenerate,accept,escalate}
    with pytest.raises(ValueError, match="disposition"):
        _validate_finding(bad)


def test_write_vendor_findings_rejects_invalid_finding(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    bad = dict(good_finding)
    bad["criticality"] = "blocking"
    with pytest.raises(ValueError):
        write_vendor_findings(
            tmp_path,
            vendor="claude_code",
            review_type="plan",
            target="x",
            findings=[good_finding, bad],
        )
    # No file should have been created
    assert list(tmp_path.glob("findings-*.json")) == []


def test_write_vendor_findings_accepts_optional_fields(
    tmp_path: Path, good_finding_with_optionals: dict[str, Any]
) -> None:
    write_vendor_findings(
        tmp_path,
        vendor="claude_code",
        review_type="plan",
        target="x",
        findings=[good_finding_with_optionals],
    )
    fpath = tmp_path / "findings-claude_code-plan.json"
    payload = json.loads(fpath.read_text())
    assert payload["findings"][0]["line_range"] == {"start": 12, "end": 14}


def test_wrapper_object_shape(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    """The per-vendor file is a wrapper object {review_type, target, reviewer_vendor, findings}."""
    write_vendor_findings(
        tmp_path,
        vendor="claude_code",
        review_type="plan",
        target="my-feature",
        findings=[good_finding],
    )
    fpath = tmp_path / "findings-claude_code-plan.json"
    payload = json.loads(fpath.read_text())
    assert payload["review_type"] == "plan"
    assert payload["target"] == "my-feature"
    assert payload["reviewer_vendor"] == "claude_code"
    assert payload["findings"] == [good_finding]


def test_reviewer_vendor_can_differ(tmp_path: Path, good_finding: dict[str, Any]) -> None:
    """Caller can override reviewer_vendor (e.g., for misnamed vendor)."""
    write_vendor_findings(
        tmp_path,
        vendor="claude_code",
        review_type="plan",
        target="x",
        findings=[good_finding],
        reviewer_vendor="claude-opus-4-7",
    )
    payload = json.loads((tmp_path / "findings-claude_code-plan.json").read_text())
    assert payload["reviewer_vendor"] == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# _validate_path_safety direct
# ---------------------------------------------------------------------------


def test_validate_path_safety_returns_resolved(tmp_path: Path) -> None:
    resolved = _validate_path_safety(tmp_path / "sub", "claude_code", "plan")
    assert resolved.is_absolute()
    assert resolved == (tmp_path / "sub").resolve()


# ---------------------------------------------------------------------------
# _safe_log_error — handler-failure isolation
# ---------------------------------------------------------------------------


def test_safe_log_error_emits_event_in_extra(caplog: pytest.LogCaptureFixture) -> None:
    """Event string is captured in LogRecord.event so tests can assert structurally."""
    with caplog.at_level(logging.ERROR, logger="checkpoint_findings"):
        _safe_log_error(
            "convergence.synthesis_failed_with_checkpoint",
            change_id="my-feature",
            review_type="plan",
            checkpoint_dir="/tmp/foo",
        )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.event == "convergence.synthesis_failed_with_checkpoint"  # type: ignore[attr-defined]
    assert record.change_id == "my-feature"  # type: ignore[attr-defined]
    assert record.review_type == "plan"  # type: ignore[attr-defined]


def test_safe_log_error_swallows_handler_exception() -> None:
    """A handler that raises in emit() must not propagate to the caller of _safe_log_error.

    This is what protects the original synthesis exception from being masked.
    """

    class ExplodingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
            raise RuntimeError("handler boom")

    handler = ExplodingHandler()
    logger = logging.getLogger("checkpoint_findings")
    # Ensure default raiseExceptions doesn't surface the handler error;
    # our _safe_log_error must catch even when raiseExceptions=True.
    original_raise = logging.raiseExceptions
    logging.raiseExceptions = True
    logger.addHandler(handler)
    try:
        # Must not raise
        _safe_log_error("convergence.test", key="value")
    finally:
        logger.removeHandler(handler)
        logging.raiseExceptions = original_raise


# ---------------------------------------------------------------------------
# Manifest schema_version constant
# ---------------------------------------------------------------------------


def test_schema_version_is_one() -> None:
    assert MANIFEST_SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# read_manifest schema_version validation
# (IMPL_REVIEW round-1 finding C1 — 3-vendor consensus)
# ---------------------------------------------------------------------------


def _write_raw_manifest(out_dir: Path, payload: dict[str, Any]) -> None:
    """Write a raw manifest dict to disk, bypassing write_manifest's schema."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review-manifest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def test_read_manifest_rejects_unknown_schema_version_v2(tmp_path: Path) -> None:
    """Future v2 manifests MUST be refused; the contract docstring at the
    top of checkpoint_findings.py declares this and the JSON Schema
    'description' field on schema_version says 'Readers MUST refuse unknown
    versions.'"""
    _write_raw_manifest(
        tmp_path,
        {
            "schema_version": 2,
            "review_type": "implementation",
            "target": "x",
            "vendors": [],
        },
    )
    with pytest.raises(ValueError, match="schema_version"):
        checkpoint_findings.read_manifest(tmp_path)


def test_read_manifest_rejects_unknown_schema_version_v0(tmp_path: Path) -> None:
    """Pre-v1 manifests MUST be refused (e.g. legacy manifests written by
    review_dispatcher.py before this proposal landed have no
    schema_version field at all)."""
    _write_raw_manifest(
        tmp_path,
        {
            "schema_version": 0,
            "review_type": "implementation",
            "target": "x",
            "vendors": [],
        },
    )
    with pytest.raises(ValueError, match="schema_version"):
        checkpoint_findings.read_manifest(tmp_path)


def test_read_manifest_rejects_missing_schema_version(tmp_path: Path) -> None:
    """A manifest with no schema_version field at all (pre-proposal legacy)
    MUST be refused — the contract requires the field and treats absence as
    a different version."""
    _write_raw_manifest(
        tmp_path,
        {
            "review_type": "implementation",
            "target": "x",
            "vendors": [],
        },
    )
    with pytest.raises(ValueError, match="schema_version"):
        checkpoint_findings.read_manifest(tmp_path)


def test_read_vendor_findings_propagates_schema_version_error(
    tmp_path: Path,
) -> None:
    """read_vendor_findings calls read_manifest, so a schema_version
    rejection MUST bubble up rather than be swallowed."""
    _write_raw_manifest(
        tmp_path,
        {
            "schema_version": 999,
            "review_type": "implementation",
            "target": "x",
            "vendors": [],
        },
    )
    with pytest.raises(ValueError, match="schema_version"):
        checkpoint_findings.read_vendor_findings(tmp_path)


# ---------------------------------------------------------------------------
# write_manifest write-side path-safety
# (IMPL_REVIEW round-1 finding C4 — codex)
# ---------------------------------------------------------------------------


def test_write_manifest_rejects_findings_path_with_separator(tmp_path: Path) -> None:
    """A vendors[].findings_path containing '/' is refused at write time
    (mirrors the read-side check so a malformed manifest never lands)."""
    with pytest.raises(ValueError, match="findings_path"):
        write_manifest(
            tmp_path, review_type="plan", target="x",
            vendors=[{
                "name": "claude_code",
                "findings_path": "subdir/findings-claude_code-plan.json",
                "finding_count": 0,
            }],
        )


def test_write_manifest_rejects_findings_path_with_traversal(tmp_path: Path) -> None:
    """findings_path containing '..' is refused at write time."""
    with pytest.raises(ValueError, match="findings_path"):
        write_manifest(
            tmp_path, review_type="plan", target="x",
            vendors=[{
                "name": "claude_code",
                "findings_path": "../findings-claude_code-plan.json",
                "finding_count": 0,
            }],
        )


def test_write_manifest_rejects_findings_path_non_string(tmp_path: Path) -> None:
    """findings_path must be a string (not None, not a Path object)."""
    with pytest.raises(ValueError, match="findings_path"):
        write_manifest(
            tmp_path, review_type="plan", target="x",
            vendors=[{
                "name": "claude_code",
                "findings_path": 42,
                "finding_count": 0,
            }],
        )


def test_write_manifest_rejects_finding_count_non_int(tmp_path: Path) -> None:
    """finding_count must be an integer when present."""
    with pytest.raises(ValueError, match="finding_count"):
        write_manifest(
            tmp_path, review_type="plan", target="x",
            vendors=[{
                "name": "claude_code",
                "findings_path": "findings-claude_code-plan.json",
                "finding_count": "five",
            }],
        )


def test_write_manifest_accepts_omitted_findings_path(tmp_path: Path) -> None:
    """Backward compat: callers that pass only {name} still work."""
    write_manifest(
        tmp_path, review_type="plan", target="x",
        vendors=[{"name": "claude_code"}],
    )
    assert (tmp_path / "review-manifest.json").exists()


# ---------------------------------------------------------------------------
# _atomic_write_json hygiene
# (IMPL_REVIEW round-1 findings C6 — gemini, C7 — claude_code)
# ---------------------------------------------------------------------------


def test_atomic_write_cleans_tmp_on_typeerror_from_non_serializable(
    tmp_path: Path,
) -> None:
    """When json.dump raises TypeError on a non-serializable payload (the
    realistic encoder failure mode — sets, datetime, custom classes), the
    partial .tmp file MUST be removed. Round-2 review caught that the
    original C7 fix only caught (OSError, ValueError); a real TypeError
    would slip past and leak residue."""
    target = tmp_path / "review-manifest.json"
    tmp = target.with_suffix(target.suffix + ".tmp")

    # Real non-serializable payload — json.dump raises TypeError on a set
    payload = {"vendors": {"claude_code", "codex"}}  # set is not JSON-serializable
    with pytest.raises(TypeError):
        checkpoint_findings._atomic_write_json(target, payload)

    # Target was never created (atomic invariant preserved)
    assert not target.exists()
    # And the .tmp residue was cleaned up (hygiene fix)
    assert not tmp.exists()


def test_atomic_write_cleans_tmp_on_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSError during the inner write block (disk-full, permission, signal)
    also triggers tmp cleanup. Verified via patched os.fsync."""
    target = tmp_path / "review-manifest.json"
    tmp = target.with_suffix(target.suffix + ".tmp")

    real_fsync = os.fsync
    failing_fd: list[int] = []

    def fsync_failing_on_first_file_fd(fd: int) -> None:
        # Fail the FIRST fsync (which is the file fsync inside the with
        # block). Subsequent ones (parent dir) shouldn't run because the
        # exception aborts before then.
        if not failing_fd:
            failing_fd.append(fd)
            raise OSError(28, "No space left on device (simulated)")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync_failing_on_first_file_fd)
    with pytest.raises(OSError, match="No space left"):
        checkpoint_findings._atomic_write_json(target, {"k": "v"})

    assert not target.exists()
    assert not tmp.exists()


def test_atomic_write_cleans_tmp_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If os.replace itself raises (e.g. read-only network filesystem),
    the .tmp residue MUST be cleaned. Round-2 review caught that
    os.replace was outside the original try/except and could leak in
    that narrow case."""
    target = tmp_path / "review-manifest.json"
    tmp = target.with_suffix(target.suffix + ".tmp")

    def failing_replace(*_args: Any, **_kwargs: Any) -> None:
        raise OSError(30, "Read-only file system (simulated)")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="Read-only"):
        checkpoint_findings._atomic_write_json(target, {"k": "v"})

    assert not target.exists()
    # The tmp file was created during the inner write but cleaned by the
    # new outer try/except on the os.replace branch.
    assert not tmp.exists()


def test_atomic_write_tolerates_parent_dir_fsync_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing os.fsync on the parent directory file descriptor (Windows,
    older macOS filesystems) MUST NOT crash the write. The file-level fsync
    at the inner block is the load-bearing durability call; the dir-level
    fsync is best-effort metadata flushing."""
    target = tmp_path / "review-manifest.json"
    real_fsync = os.fsync
    fsync_calls: list[int] = []

    def fsync_failing_on_dir(fd: int) -> None:
        fsync_calls.append(fd)
        # Simulate macOS/Windows behavior: dir fsync fails, file fsync ok.
        # We detect the dir vs file fd by stat type.
        try:
            stat = os.fstat(fd)
            from stat import S_ISDIR
            if S_ISDIR(stat.st_mode):
                raise OSError(22, "Invalid argument (simulated)")
        except OSError:
            raise
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync_failing_on_dir)

    # Write should succeed despite the dir-fsync raising
    checkpoint_findings._atomic_write_json(target, {"k": "v"})
    assert target.exists()
    assert json.loads(target.read_text()) == {"k": "v"}
    # And the dir fsync was attempted (i.e. we exercised the new try/except)
    assert len(fsync_calls) >= 2  # one for file fd, one for dir fd


def test_atomic_write_tolerates_parent_dir_open_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If even opening the parent directory fails (Windows lacks dir fds),
    the write still succeeds — file-level fsync already ran."""
    target = tmp_path / "review-manifest.json"
    real_open = os.open

    def open_failing_on_dir(*args: Any, **kwargs: Any) -> int:
        # First arg is the path
        path = args[0]
        if str(path) == str(tmp_path):
            raise OSError(22, "no directory file descriptors (simulated)")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(os, "open", open_failing_on_dir)

    checkpoint_findings._atomic_write_json(target, {"k": "v"})
    assert target.exists()
