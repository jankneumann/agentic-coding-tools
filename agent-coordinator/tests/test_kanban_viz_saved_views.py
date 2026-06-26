"""Tests for the extended saved-view schema — task 3.8.

Covers pr_origins and hidden_rows optional fields via schema validation,
plus round-trip PUT → GET via the coordinator API.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Schema validation helper
# ---------------------------------------------------------------------------


def _load_schema() -> dict[str, Any]:
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "schemas" / "kanban_viz" / "saved-view.json"
    )
    return json.loads(schema_path.read_text())


def _validate(instance: dict[str, Any]) -> None:
    """Validate instance against the saved-view JSON schema.

    Raises jsonschema.ValidationError on failure.
    """
    import jsonschema  # type: ignore[import]

    schema = _load_schema()
    jsonschema.validate(instance=instance, schema=schema)


def _minimal_view(*, name: str = "test-view", **view_extras: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": "2025-06-01T00:00:00Z",
        "git_sha": "abc1234",
        "generator": "test",
        "view": {
            "name": name,
            "filters": {},
            **view_extras,
        },
    }


# ---------------------------------------------------------------------------
# 3.8a — saved-view with new fields validates
# ---------------------------------------------------------------------------


class TestNewFieldsValidate:
    def test_pr_origins_field_validates(self) -> None:
        """pr_origins with valid origin values must validate."""
        instance = _minimal_view(pr_origins=["openspec", "codex", "manual"])
        _validate(instance)

    def test_hidden_rows_field_validates(self) -> None:
        """hidden_rows with valid row values must validate."""
        instance = _minimal_view(hidden_rows=["prs", "proposals"])
        _validate(instance)

    def test_both_new_fields_together_validates(self) -> None:
        """pr_origins and hidden_rows can coexist."""
        instance = _minimal_view(
            pr_origins=["jules", "dependabot"],
            hidden_rows=["issues"],
        )
        _validate(instance)

    def test_empty_pr_origins_validates(self) -> None:
        instance = _minimal_view(pr_origins=[])
        _validate(instance)

    def test_empty_hidden_rows_validates(self) -> None:
        instance = _minimal_view(hidden_rows=[])
        _validate(instance)


# ---------------------------------------------------------------------------
# 3.8b — old views without new fields still validate
# ---------------------------------------------------------------------------


class TestOldViewsStillValid:
    def test_view_without_new_fields_validates(self) -> None:
        """Pre-existing views without pr_origins / hidden_rows still valid."""
        instance = _minimal_view()
        _validate(instance)

    def test_view_with_existing_filters_validates(self) -> None:
        """Views with the existing filters shape still validate."""
        instance = _minimal_view()
        instance["view"]["filters"]["change_ids"] = ["my-change"]
        instance["view"]["filters"]["vendors"] = ["claude"]
        _validate(instance)


# ---------------------------------------------------------------------------
# 3.8c — bogus values fail validation
# ---------------------------------------------------------------------------


class TestBogusValuesFail:
    def test_pr_origins_bogus_value_fails(self) -> None:
        import jsonschema  # type: ignore[import]

        instance = _minimal_view(pr_origins=["bogus"])
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance)

    def test_hidden_rows_bogus_value_fails(self) -> None:
        import jsonschema  # type: ignore[import]

        instance = _minimal_view(hidden_rows=["worktrees"])
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance)

    def test_pr_origins_not_array_fails(self) -> None:
        import jsonschema  # type: ignore[import]

        instance = _minimal_view(pr_origins="openspec")  # string, not array
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance)


# ---------------------------------------------------------------------------
# Round-trip via API: PUT then GET
# ---------------------------------------------------------------------------

_TEST_KEY = "saved-views-test-key-001"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_KEY}"}


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from src.config import reset_config

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    monkeypatch.setenv("KANBAN_VIZ_DIR", str(tmp_path / "views"))
    reset_config()
    yield
    reset_config()


class TestRoundTripAPI:
    def test_put_saved_view_with_new_fields_accepted(
        self, _api_config: None, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PUT a view with pr_origins + hidden_rows is accepted (200/201).

        Also verifies the written file contains the new fields by reading
        from disk directly (the coordinator has no GET endpoint for saved-views).
        """
        from fastapi.testclient import TestClient

        from src.coordination_api import create_coordination_api

        # COORDINATOR_WORKDIR_ROOT controls where the coordinator writes files
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        monkeypatch.setenv("COORDINATOR_WORKDIR_ROOT", str(workdir))

        app = create_coordination_api()

        payload = {
            "schema_version": 1,
            "generated_at": "2025-06-01T00:00:00Z",
            "git_sha": "abc1234",
            "generator": "kanban-viz-spa",
            "view": {
                "name": "My Board",
                "filters": {"change_ids": ["foo"]},
                "pr_origins": ["openspec", "codex"],
                "hidden_rows": ["proposals"],
            },
        }

        with TestClient(app, raise_server_exceptions=False) as client:
            put_resp = client.put(
                "/kanban-viz/saved-views/my-board",
                json=payload,
                headers=_auth_headers(),
            )
            assert put_resp.status_code in (200, 201), put_resp.text

        # Read the written file and verify new fields are present
        written_files = list(workdir.rglob("*.json"))
        assert written_files, "No JSON file written to workdir"
        written = json.loads(written_files[0].read_text())
        assert written["view"]["pr_origins"] == ["openspec", "codex"]
        assert written["view"]["hidden_rows"] == ["proposals"]


# ---------------------------------------------------------------------------
# Task 5.1 — hidden_repos field validation (extend-kanban-viz-multi-repo-proposals)
# ---------------------------------------------------------------------------


class TestHiddenReposField:
    def test_hidden_repos_valid_entry_validates(self) -> None:
        """view.hidden_repos with a valid owner/repo string must validate."""
        instance = _minimal_view(hidden_repos=["jankneumann/scratch"])
        _validate(instance)

    def test_hidden_repos_multiple_valid_entries_validates(self) -> None:
        """Multiple valid owner/repo strings in hidden_repos must validate."""
        instance = _minimal_view(
            hidden_repos=["jankneumann/agentic-coding-tools", "owner/newsletter-aggregator"]
        )
        _validate(instance)

    def test_hidden_repos_empty_array_validates(self) -> None:
        """Empty hidden_repos array must validate."""
        instance = _minimal_view(hidden_repos=[])
        _validate(instance)

    def test_pre_existing_view_without_hidden_repos_validates(self) -> None:
        """Saved view without hidden_repos (pre-existing) must still validate."""
        instance = _minimal_view()
        _validate(instance)

    def test_hidden_repos_with_other_fields_validates(self) -> None:
        """hidden_repos coexists with pr_origins and hidden_rows."""
        instance = _minimal_view(
            pr_origins=["openspec"],
            hidden_rows=["issues"],
            hidden_repos=["owner/repo"],
        )
        _validate(instance)

    def test_hidden_repos_invalid_entry_fails(self) -> None:
        """hidden_repos entry not matching ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ must fail."""
        import jsonschema  # type: ignore[import]

        instance = _minimal_view(hidden_repos=["not_a_valid_entry"])
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance)

    def test_hidden_repos_entry_missing_slash_fails(self) -> None:
        """hidden_repos entry without a slash must fail validation."""
        import jsonschema  # type: ignore[import]

        instance = _minimal_view(hidden_repos=["owneronly"])
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance)

    def test_hidden_repos_not_array_fails(self) -> None:
        """hidden_repos as a string (not array) must fail validation."""
        import jsonschema  # type: ignore[import]

        instance = _minimal_view(hidden_repos="jankneumann/scratch")  # type: ignore[arg-type]
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance)

    def test_hidden_repos_round_trip_via_api(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PUT a saved view with hidden_repos is accepted and field survives on disk."""
        from fastapi.testclient import TestClient

        from src.config import reset_config
        from src.coordination_api import create_coordination_api

        test_key_hr = "hidden-repos-test-key-001"
        monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
        monkeypatch.setenv("COORDINATION_API_KEYS", test_key_hr)
        monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        monkeypatch.setenv("COORDINATOR_WORKDIR_ROOT", str(workdir))
        monkeypatch.setenv("KANBAN_VIZ_DIR", str(tmp_path / "views"))
        reset_config()

        payload = {
            "schema_version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "git_sha": "abc1234",
            "generator": "kanban-viz-spa",
            "view": {
                "name": "Multi-Repo Board",
                "filters": {},
                "hidden_repos": ["jankneumann/scratch-repo"],
            },
        }

        app = create_coordination_api()
        with TestClient(app, raise_server_exceptions=False) as client:
            put_resp = client.put(
                "/kanban-viz/saved-views/multi-repo",
                json=payload,
                headers={"Authorization": f"Bearer {test_key_hr}"},
            )
            assert put_resp.status_code in (200, 201), put_resp.text

        written_files = list(workdir.rglob("*.json"))
        assert written_files, "No JSON file written"
        written = json.loads(written_files[0].read_text())
        assert written["view"]["hidden_repos"] == ["jankneumann/scratch-repo"]

        reset_config()
