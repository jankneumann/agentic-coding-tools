"""Contract tests for the probe block and probe cache schemas (task 1.1).

Schema layer only. The last-token ``login`` and help-token rules are enforced in
agents_config.validate and pinned in task 4.1.
"""
from __future__ import annotations

import copy
import json
import re

import pytest
from jsonschema import Draft202012Validator
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CONTRACTS = change_dir(REPO_ROOT, "add-local-agent-probe") / "contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


PROBE_SCHEMA = _load("cli-probe-block.schema.json")
CACHE_SCHEMA = _load("vendor-probe-cache.schema.json")
PROBE = Draft202012Validator(PROBE_SCHEMA)
CACHE = Draft202012Validator(CACHE_SCHEMA)


def _walk_patterns(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pattern" and isinstance(value, str):
                yield value
            else:
                yield from _walk_patterns(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_patterns(item)


@pytest.mark.parametrize("schema", [PROBE_SCHEMA, CACHE_SCHEMA])
def test_schemas_are_valid_and_patterns_ecma_compatible(schema):
    Draft202012Validator.check_schema(schema)
    for pattern in _walk_patterns(schema):
        assert "(?i)" not in pattern
        re.compile(pattern)


# ---------------------------------------------------------------- probe block


@pytest.mark.parametrize(
    "block",
    [
        {},
        {"version_args": ["--version"]},
        {"auth_status_args": ["login", "status"]},
        {"help_args": {"review": ["review", "--help"]}},
        {"credential_files": ["~/.codex/auth.json"]},
        {"ignore_flags": ["--foo"]},
    ],
)
def test_probe_block_accepts(block):
    assert not list(PROBE.iter_errors(block))


@pytest.mark.parametrize(
    "block",
    [
        {"auth_status_args": ["auth", "print-api-key"]},
        {"auth_status_args": ["auth", "Print-API-Key"]},
        {"version_args": ["--print-bearer-token"]},
        {"version_args": ["--show-token"]},
        {"help_args": {"m": ["--credentials"]}},
        {"help_args": {"m": ["logout", "--help"]}},
        {"version_args": []},
        {"help_args": {"m": []}},
        {"help_args": {}},
        {"credential_files": []},
        {"ignore_flags": []},
        {"ignore_flags": ["noDash"]},
        {"mystery": 1},
    ],
)
def test_probe_block_rejects(block):
    assert list(PROBE.iter_errors(block))


# ---------------------------------------------------------------------- cache

TS = "2026-10-30T00:00:00Z"
FP = "sha256:" + "a" * 64


def _lane(**over):
    lane = {
        "agent_id": "claude-main",
        "command": "claude",
        "cli_realpath": "/usr/bin/claude",
        "cli_version": "1.0.0",
        "config_fingerprint": FP,
        "probed_at": TS,
        "ttl_seconds": 3600,
        "l0": {"ok": True},
        "modes": {"review": {"ok": True}},
        "l2": {"status": "auth_ok", "method": "status_command"},
    }
    lane.update(over)
    return lane


def _cache(**over):
    cache = {"schema_version": 1, "lanes": {"claude-main": _lane()}}
    cache.update(over)
    return cache


def test_cache_accepts_baseline():
    assert not list(CACHE.iter_errors(_cache()))


def test_cache_accepts_failure_without_lane_entry():
    cache = _cache(
        lanes={},
        runtime_failures={
            "claude-main": {
                "error_class": "auth_required",
                "observed_at": TS,
                "ttl_seconds": 600,
            }
        },
    )
    assert not list(CACHE.iter_errors(cache))


def test_cache_rejects_nested_runtime_failure_in_lane():
    lane = _lane(
        runtime_failure={
            "error_class": "auth_required",
            "observed_at": TS,
            "ttl_seconds": 600,
        }
    )
    assert list(CACHE.iter_errors(_cache(lanes={"claude-main": lane})))


@pytest.mark.parametrize("reason", ["auth_failed", "bogus"])
def test_cache_rejects_non_tier_reason(reason):
    lane = _lane(l0={"ok": False, "reason": reason})
    assert list(CACHE.iter_errors(_cache(lanes={"claude-main": lane})))
    lane = _lane(modes={"review": {"ok": False, "reason": reason}})
    assert list(CACHE.iter_errors(_cache(lanes={"claude-main": lane})))


def test_cache_rejects_failed_tier_without_reason():
    lane = _lane(l0={"ok": False})
    assert list(CACHE.iter_errors(_cache(lanes={"claude-main": lane})))


def test_cache_missing_flags_requires_list():
    good = _lane(
        modes={"review": {"ok": False, "reason": "missing_flags", "missing_flags": ["--x"]}}
    )
    assert not list(CACHE.iter_errors(_cache(lanes={"a": good})))
    bad = copy.deepcopy(good)
    del bad["modes"]["review"]["missing_flags"]
    assert list(CACHE.iter_errors(_cache(lanes={"a": bad})))


def test_cache_l2_requires_method():
    lane = _lane(l2={"status": "auth_ok"})
    assert list(CACHE.iter_errors(_cache(lanes={"a": lane})))


def test_cache_method_none_rejects_auth_ok():
    lane = _lane(l2={"status": "auth_ok", "method": "none"})
    assert list(CACHE.iter_errors(_cache(lanes={"a": lane})))
    lane = _lane(l2={"status": "auth_unknown", "method": "none"})
    assert not list(CACHE.iter_errors(_cache(lanes={"a": lane})))


def test_cache_rejects_bad_fingerprint_and_version():
    assert list(CACHE.iter_errors(_cache(schema_version=2)))
    lane = _lane(config_fingerprint="md5:abc")
    assert list(CACHE.iter_errors(_cache(lanes={"a": lane})))
