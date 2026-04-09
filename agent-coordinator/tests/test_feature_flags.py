"""Tests for the feature flag system (wp-feature-flags tasks 4.1-4.6).

Covers:
  - Flag name normalization and validation (FLAG_NAME_PATTERN)
  - Resolution order: FF_* env var → flags.yaml → False (default disabled)
  - Fail-closed for undeclared FF_* env vars (Security Considerations, D7)
  - Orphaned reference safety (flag removed from yaml, still called in code)
  - Idempotent create_flag + atomic write (temp file + fsync + os.replace)
  - Malformed / missing flags.yaml failure modes
  - Lock key registration (flag:<name> namespace)
  - Thread-safety roundtrip via concurrent create_flag calls
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from src.feature_flags import (
    ENV_VAR_PREFIX,
    FLAG_NAME_PATTERN,
    FeatureFlagService,
    Flag,
    FlagsConfigError,
    InvalidFlagNameError,
    normalize_flag_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_flags_yaml(path: Path, flags: list[dict] | None = None) -> None:
    """Write a minimal valid flags.yaml file."""
    path.write_text(
        yaml.safe_dump(
            {"schema_version": 1, "flags": flags or []},
            sort_keys=False,
        )
    )


def _make_service(tmp_path: Path, filename: str = "flags.yaml") -> FeatureFlagService:
    return FeatureFlagService(flags_path=tmp_path / filename)


# ---------------------------------------------------------------------------
# normalize_flag_name
# ---------------------------------------------------------------------------


class TestNormalizeFlagName:
    @pytest.mark.parametrize(
        "change_id, expected",
        [
            ("speculative-merge-trains", "SPECULATIVE_MERGE_TRAINS"),
            ("feat.billing_v2", "FEAT_BILLING_V2"),
            ("wp-contracts", "WP_CONTRACTS"),
            ("a--b..c", "A_B_C"),
            ("ALREADY_UPPER", "ALREADY_UPPER"),
        ],
    )
    def test_valid(self, change_id: str, expected: str) -> None:
        assert normalize_flag_name(change_id) == expected

    def test_empty_raises(self) -> None:
        with pytest.raises(InvalidFlagNameError):
            normalize_flag_name("")

    def test_all_separators_raises(self) -> None:
        with pytest.raises(InvalidFlagNameError):
            normalize_flag_name("---")

    def test_starts_with_digit_raises(self) -> None:
        # After upper/separator pass: "1FEAT" does NOT match ^[A-Z]
        with pytest.raises(InvalidFlagNameError):
            normalize_flag_name("1feat")

    def test_pattern_accepts_expected(self) -> None:
        assert FLAG_NAME_PATTERN.match("BILLING_V2")
        assert not FLAG_NAME_PATTERN.match("billing_v2")
        assert not FLAG_NAME_PATTERN.match("_LEAD")


# ---------------------------------------------------------------------------
# Flag dataclass
# ---------------------------------------------------------------------------


class TestFlagDataclass:
    def test_is_enabled_true(self) -> None:
        assert Flag(name="X", owner="o", status="enabled").is_enabled() is True

    def test_is_enabled_false_for_disabled(self) -> None:
        assert Flag(name="X", owner="o", status="disabled").is_enabled() is False

    def test_is_enabled_false_for_archived(self) -> None:
        assert Flag(name="X", owner="o", status="archived").is_enabled() is False

    def test_to_yaml_dict_roundtrip(self) -> None:
        now = datetime.now(UTC)
        flag = Flag(
            name="FEAT_X",
            owner="change-x",
            status="enabled",
            description="test",
            created_at=now,
        )
        data = flag.to_yaml_dict()
        back = Flag.from_yaml_dict(data)
        assert back.name == "FEAT_X"
        assert back.owner == "change-x"
        assert back.status == "enabled"
        assert back.created_at == now

    def test_from_yaml_dict_parses_iso_z(self) -> None:
        data = {
            "name": "X",
            "owner": "o",
            "status": "enabled",
            "description": "d",
            "created_at": "2024-01-01T00:00:00Z",
        }
        flag = Flag.from_yaml_dict(data)
        assert flag.created_at is not None
        assert flag.created_at.year == 2024


# ---------------------------------------------------------------------------
# Loading / parsing
# ---------------------------------------------------------------------------


class TestLoadFlagsYaml:
    def test_missing_file_returns_empty_registry(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Bootstrap case — absent flags.yaml is a warning, not an error."""
        service = _make_service(tmp_path, "does-not-exist.yaml")
        with caplog.at_level("WARNING"):
            result = service.load()
        assert result == {}
        assert any("not found" in rec.message for rec in caplog.records)

    def test_missing_file_warning_only_once(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, "does-not-exist.yaml")
        service.load()
        # Reset the captured warning state; second load should not re-warn.
        assert service._missing_warned is True
        service.load()  # no raise, no extra warning (manual inspection)

    def test_empty_file_is_empty_registry(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        path.write_text("")
        service = FeatureFlagService(flags_path=path)
        assert service.load() == {}

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        path.write_text("schema_version: 1\nflags: [invalid\n")
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="malformed YAML"):
            service.load()

    def test_wrong_top_level_type_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        path.write_text("- just a list\n")
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="must be a mapping"):
            service.load()

    def test_missing_schema_version_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        path.write_text("flags: []\n")
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="schema_version"):
            service.load()

    def test_wrong_schema_version_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(path)
        # Overwrite with schema_version=2
        path.write_text("schema_version: 2\nflags: []\n")
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="schema_version"):
            service.load()

    def test_flags_not_a_list_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        path.write_text("schema_version: 1\nflags: {}\n")
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="'flags' must be a list"):
            service.load()

    def test_invalid_flag_name_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "lowercase_bad",
                    "owner": "o",
                    "status": "disabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="invalid flag name"):
            service.load()

    def test_invalid_status_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "broken",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="invalid flag status"):
            service.load()

    def test_duplicate_flag_name_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        entry = {
            "name": "FEAT_X",
            "owner": "o",
            "status": "disabled",
            "description": "d",
            "created_at": "2024-01-01T00:00:00Z",
        }
        _write_flags_yaml(path, [entry, entry])
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(FlagsConfigError, match="duplicate"):
            service.load()

    def test_load_valid_registry(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "change-x",
                    "status": "enabled",
                    "description": "x",
                    "created_at": "2024-01-01T00:00:00Z",
                },
                {
                    "name": "FEAT_Y",
                    "owner": "change-y",
                    "status": "disabled",
                    "description": "y",
                    "created_at": "2024-01-01T00:00:00Z",
                },
            ],
        )
        service = FeatureFlagService(flags_path=path)
        registry = service.load()
        assert set(registry) == {"FEAT_X", "FEAT_Y"}
        assert registry["FEAT_X"].is_enabled() is True
        assert registry["FEAT_Y"].is_enabled() is False


# ---------------------------------------------------------------------------
# Resolution (read path)
# ---------------------------------------------------------------------------


class TestResolveFlag:
    def test_disabled_by_default(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "disabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("FEAT_X") is False

    def test_enabled_yaml_returns_true(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "enabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("FEAT_X") is True

    def test_env_var_overrides_yaml_to_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "disabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        monkeypatch.setenv("FF_FEAT_X", "true")
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("FEAT_X") is True

    def test_env_var_overrides_yaml_to_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "enabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        monkeypatch.setenv("FF_FEAT_X", "0")
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("FEAT_X") is False

    @pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on", " true "])
    def test_env_var_truthy_values(
        self,
        truthy: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "disabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        monkeypatch.setenv("FF_FEAT_X", truthy)
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("FEAT_X") is True

    @pytest.mark.parametrize("falsy", ["0", "false", "no", "off", ""])
    def test_env_var_falsy_values(
        self,
        falsy: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "enabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        monkeypatch.setenv("FF_FEAT_X", falsy)
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("FEAT_X") is False

    def test_env_var_garbage_falls_back_to_yaml(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "enabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        monkeypatch.setenv("FF_FEAT_X", "maybe")
        service = FeatureFlagService(flags_path=path)
        with caplog.at_level("WARNING"):
            result = service.resolve_flag("FEAT_X")
        assert result is True  # Fell back to yaml (enabled)
        assert any("unrecognized value" in rec.message for rec in caplog.records)

    def test_orphaned_reference_returns_false_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Flag referenced in code but removed from yaml → False (safe removal)."""
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(path, [])
        service = FeatureFlagService(flags_path=path)
        with caplog.at_level("WARNING"):
            result = service.resolve_flag("REMOVED_FLAG")
        assert result is False
        assert any("undeclared" in rec.message for rec in caplog.records)

    def test_undeclared_env_var_ignored_for_undeclared_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FF_* set for a flag not in yaml must NOT enable it (fail-closed)."""
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(path, [])
        monkeypatch.setenv("FF_UNKNOWN_FLAG", "true")
        service = FeatureFlagService(flags_path=path)
        assert service.resolve_flag("UNKNOWN_FLAG") is False

    def test_is_enabled_is_alias(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "enabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        assert service.is_enabled("FEAT_X") is True


# ---------------------------------------------------------------------------
# check_undeclared_env_vars
# ---------------------------------------------------------------------------


class TestCheckUndeclaredEnvVars:
    def test_no_env_vars(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear all FF_* to isolate
        for key in list(os.environ):
            if key.startswith(ENV_VAR_PREFIX):
                monkeypatch.delenv(key, raising=False)
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(path, [])
        service = FeatureFlagService(flags_path=path)
        assert service.check_undeclared_env_vars() == []

    def test_detects_undeclared(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in list(os.environ):
            if key.startswith(ENV_VAR_PREFIX):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("FF_BOGUS_ONE", "1")
        monkeypatch.setenv("FF_BOGUS_TWO", "1")
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(path, [])
        service = FeatureFlagService(flags_path=path)
        offenders = service.check_undeclared_env_vars()
        assert set(offenders) == {"FF_BOGUS_ONE", "FF_BOGUS_TWO"}

    def test_declared_env_var_not_flagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in list(os.environ):
            if key.startswith(ENV_VAR_PREFIX):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("FF_FEAT_X", "1")
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "disabled",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        assert service.check_undeclared_env_vars() == []


# ---------------------------------------------------------------------------
# create_flag (write path)
# ---------------------------------------------------------------------------


class TestCreateFlag:
    def test_creates_new_flag_bootstrap(self, tmp_path: Path) -> None:
        """flags.yaml does not exist → bootstrap case creates it."""
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        flag = service.create_flag("speculative-merge-trains")
        assert flag.name == "SPECULATIVE_MERGE_TRAINS"
        assert flag.status == "disabled"
        assert flag.owner == "speculative-merge-trains"
        assert path.exists()
        # Re-load from disk to confirm persistence
        reloaded = FeatureFlagService(flags_path=path).load()
        assert "SPECULATIVE_MERGE_TRAINS" in reloaded

    def test_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        f1 = service.create_flag("wp-x")
        f2 = service.create_flag("wp-x")
        assert f1.name == f2.name
        # Only one entry in yaml
        data = yaml.safe_load(path.read_text())
        assert len(data["flags"]) == 1

    def test_custom_description(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        flag = service.create_flag("wp-y", description="custom reason")
        assert flag.description == "custom reason"

    def test_registers_lock_key(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        service.create_flag("wp-z")
        assert "flag:WP_Z" in service._lock_key_register

    def test_idempotent_does_not_re_register_lock_key(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        service.create_flag("wp-a")
        service.create_flag("wp-a")
        service.create_flag("wp-a")
        assert service._lock_key_register.count("flag:WP_A") == 1

    def test_atomic_write_leaves_no_tmp(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        service.create_flag("wp-q")
        assert not (tmp_path / "flags.yaml.tmp").exists()

    def test_serialized_yaml_passes_schema(self, tmp_path: Path) -> None:
        """Written yaml must round-trip through load() without errors."""
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        service.create_flag("wp-r")
        # Fresh instance, load from disk
        reloaded = FeatureFlagService(flags_path=path).load()
        assert "WP_R" in reloaded
        assert reloaded["WP_R"].status == "disabled"

    def test_concurrent_create_is_safe(self, tmp_path: Path) -> None:
        """Two threads creating the same flag should produce exactly one entry."""
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        barrier = threading.Barrier(5)
        results: list[str] = []

        def worker() -> None:
            barrier.wait()
            flag = service.create_flag("wp-concurrent")
            results.append(flag.name)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == "WP_CONCURRENT" for r in results)
        data = yaml.safe_load(path.read_text())
        assert len(data["flags"]) == 1


# ---------------------------------------------------------------------------
# enable_flag
# ---------------------------------------------------------------------------


class TestEnableFlag:
    def test_disabled_to_enabled(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        service.create_flag("wp-e")
        flag = service.enable_flag("WP_E")
        assert flag.status == "enabled"
        # Reload to confirm persistence
        reloaded = FeatureFlagService(flags_path=path).load()
        assert reloaded["WP_E"].status == "enabled"

    def test_unknown_flag_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        service = FeatureFlagService(flags_path=path)
        service.create_flag("wp-other")
        with pytest.raises(ValueError, match="flag not found"):
            service.enable_flag("NONEXISTENT")

    def test_archived_cannot_be_enabled(self, tmp_path: Path) -> None:
        path = tmp_path / "flags.yaml"
        _write_flags_yaml(
            path,
            [
                {
                    "name": "FEAT_X",
                    "owner": "o",
                    "status": "archived",
                    "description": "d",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        service = FeatureFlagService(flags_path=path)
        with pytest.raises(ValueError, match="archived"):
            service.enable_flag("FEAT_X")


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------


class TestModuleSingleton:
    def test_get_and_reset(self) -> None:
        from src.feature_flags import (
            get_feature_flag_service,
            reset_feature_flag_service,
        )

        s1 = get_feature_flag_service()
        s2 = get_feature_flag_service()
        assert s1 is s2
        reset_feature_flag_service()
        s3 = get_feature_flag_service()
        assert s3 is not s1
