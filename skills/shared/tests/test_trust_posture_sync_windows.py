"""Tests for the trust posture ``sync_windows`` declaration and authorization."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

SKILLS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILLS_ROOT.parent
sys.path.insert(0, str(SKILLS_ROOT))
from shared import github_classifier  # noqa: E402
from shared import trust_posture as tp  # noqa: E402

LIVE_DIGEST = "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24"

GATES_BLOCK = "gates:\n  merge:\n    disposition: block\n"

WINDOW = {
    "id": "nightly-drain",
    "cadence": "0 3 * * 1-5",
    "skills": ["merge-pull-requests", "update-specs"],
    "allowed_sources": ["openspec", "dependabot"],
    "auto_merge_ceiling": "plan",
}


def contract(tmp_path: Path, windows: object = ..., *, raw: str | None = None) -> Path:
    """Write a contract; ``windows=...`` omits the key entirely."""
    body = "schema_version: 1\n" + GATES_BLOCK
    if raw is not None:
        body += raw
    elif windows is not ...:
        body += yaml.safe_dump({"sync_windows": windows}, sort_keys=False)
    path = tmp_path / "TRUST_POSTURE.md"
    path.write_text(f"---\n{body}---\n\nprose\n", encoding="utf-8")
    return path


def load(tmp_path: Path, windows: object = ...) -> tp.TrustPosture:
    return tp.load_posture(path=contract(tmp_path, windows))


def window(**overrides: object) -> dict:
    w = copy.deepcopy(WINDOW)
    w.update(overrides)
    return w


# --------------------------------------------------------------------------- #
# Absent windows
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value", [..., None, []])
def test_absent_null_empty_declare_nothing(tmp_path: Path, value: object) -> None:
    posture = load(tmp_path, value)
    assert posture.sync_windows == ()
    for skill in tp.SYNC_SKILLS:
        with pytest.raises(tp.SyncWindowNotAuthorized):
            tp.authorize_sync_window(posture, "nightly-drain", skill)


def test_no_contract_file_and_none_fail_closed(tmp_path: Path) -> None:
    absent = tp.load_posture(path=tmp_path / "missing.md")
    assert absent.present is False
    for posture in (absent, None):
        with pytest.raises(tp.SyncWindowNotAuthorized):
            tp.authorize_sync_window(posture, "any", "merge-pull-requests")


# --------------------------------------------------------------------------- #
# Valid windows
# --------------------------------------------------------------------------- #

def test_valid_window_round_trips(tmp_path: Path) -> None:
    posture = load(tmp_path, [WINDOW])
    (w,) = posture.sync_windows
    assert w.id == "nightly-drain"
    assert w.cadence == "0 3 * * 1-5"
    assert set(w.skills) == {"merge-pull-requests", "update-specs"}
    assert set(w.allowed_sources) == {"openspec", "dependabot"}
    assert w.auto_merge_ceiling is tp.MergeCeiling.PLAN


def test_authorize_returns_window_and_refuses_unlisted(tmp_path: Path) -> None:
    posture = load(tmp_path, [WINDOW])
    got = tp.authorize_sync_window(posture, "nightly-drain", "merge-pull-requests")
    assert got is posture.sync_windows[0]
    with pytest.raises(tp.SyncWindowNotAuthorized, match="cleanup-feature"):
        tp.authorize_sync_window(posture, "nightly-drain", "cleanup-feature")
    with pytest.raises(tp.SyncWindowNotAuthorized, match="other-window"):
        tp.authorize_sync_window(posture, "other-window", "merge-pull-requests")


def test_unknown_skill_is_usage_error(tmp_path: Path) -> None:
    posture = load(tmp_path, [WINDOW])
    with pytest.raises(ValueError) as exc:
        tp.authorize_sync_window(posture, "nightly-drain", "autopilot")
    assert not isinstance(exc.value, tp.SyncWindowNotAuthorized)


# --------------------------------------------------------------------------- #
# Malformed windows
# --------------------------------------------------------------------------- #

def _bad(**overrides: object) -> dict:
    return window(**overrides)


def _without(key: str) -> dict:
    w = window()
    del w[key]
    return w


MALFORMED = {
    "unknown field": (window(extra=1), "extra"),
    "missing id": (_without("id"), "'id'"),
    "missing cadence": (_without("cadence"), "'cadence'"),
    "missing skills": (_without("skills"), "'skills'"),
    "empty skills": (_bad(skills=[]), "skills"),
    "empty sources": (_bad(allowed_sources=[]), "allowed_sources"),
    "repeated skill": (_bad(skills=["update-specs", "update-specs"]), "repeats"),
    "repeated source": (_bad(allowed_sources=["jules", "jules"]), "repeats"),
    "unknown skill": (_bad(skills=["autopilot"]), "autopilot"),
    "unknown source": (_bad(allowed_sources=["gitlab"]), "gitlab"),
    "unknown ceiling": (_bad(auto_merge_ceiling="all"), "auto_merge_ceiling"),
    "non-kebab id": (_bad(id="Nightly_Drain"), "kebab-case"),
    "four-field cadence": (_bad(cadence="0 3 * *"), "cadence"),
    "six-field cadence": (_bad(cadence="0 0 3 * * 1"), "cadence"),
    "macro cadence": (_bad(cadence="@daily"), "cadence"),
    "named day cadence": (_bad(cadence="0 3 * * MON"), "cadence"),
    "non-string cadence": (_bad(cadence=5), "cadence"),
    "scalar skills": (_bad(skills="update-specs"), "skills"),
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_malformed_window_rejected_naming_window(tmp_path: Path, name: str) -> None:
    entry, needle = MALFORMED[name]
    path = contract(tmp_path, [entry])
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(path=path)
    msg = str(exc.value)
    assert "sync_windows[0]" in msg
    assert needle in msg
    assert tp.validate_posture_file(path)


def test_duplicate_id_rejected(tmp_path: Path) -> None:
    path = contract(tmp_path, [window(), window(cadence="5 4 * * *")])
    with pytest.raises(tp.PostureValidationError, match=r"sync_windows\[1\].*duplicate"):
        tp.load_posture(path=path)


@pytest.mark.parametrize("value", ["daily", {"id": "x"}, 5, True])
def test_non_list_container_rejected(tmp_path: Path, value: object) -> None:
    with pytest.raises(tp.PostureValidationError, match="sync_windows"):
        tp.load_posture(path=contract(tmp_path, value))


def test_non_mapping_entry_rejected_with_index(tmp_path: Path) -> None:
    path = contract(tmp_path, [WINDOW, "nightly"])
    with pytest.raises(tp.PostureValidationError, match=r"sync_windows\[1\]"):
        tp.load_posture(path=path)


def test_malformed_window_not_silently_dropped(tmp_path: Path) -> None:
    path = contract(tmp_path, [WINDOW, window(id="second", cadence="bad")])
    with pytest.raises(tp.PostureValidationError):
        tp.load_posture(path=path)


# --------------------------------------------------------------------------- #
# Ceiling
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "ceiling, permitted",
    [
        ("none", set()),
        ("automation", {"automation"}),
        ("plan", {"automation", "plan"}),
        ("implementation", {"automation", "plan", "implementation"}),
    ],
)
def test_ceiling_ordering(ceiling: str, permitted: set) -> None:
    c = tp.MergeCeiling(ceiling)
    for kind in ("automation", "plan", "implementation"):
        assert c.permits(kind) is (kind in permitted)


@pytest.mark.parametrize("ceiling", [c.value for c in tp.MergeCeiling])
@pytest.mark.parametrize("kind", ["", "unknown", "none", None, 3, "PLAN"])
def test_no_ceiling_permits_unknown_kind(ceiling: str, kind: object) -> None:
    assert tp.MergeCeiling(ceiling).permits(kind) is False


# --------------------------------------------------------------------------- #
# Vocabulary parity
# --------------------------------------------------------------------------- #

def test_sources_match_classifier_origins() -> None:
    assert tp.SYNC_SOURCES == github_classifier.PR_ORIGINS


def test_ranked_kinds_match_classify_kind() -> None:
    path = SKILLS_ROOT / "merge-pull-requests" / "scripts" / "classify_kind.py"
    spec = importlib.util.spec_from_file_location("_classify_kind_parity", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(tp._KIND_RANK) == set(mod.KIND_TO_SKILL)


def test_ceiling_values_are_none_plus_kinds() -> None:
    assert {c.value for c in tp.MergeCeiling} == {"none", *tp._KIND_RANK}


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #

def _gates_only_digest(posture: tp.TrustPosture) -> str:
    canonical = {g.value: posture.disposition_for(g).to_canonical() for g in tp.Gate}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def test_digest_without_windows_is_gates_only(tmp_path: Path) -> None:
    for value in (..., None, []):
        posture = load(tmp_path, value)
        assert tp.posture_digest(posture) == _gates_only_digest(posture)
    assert tp.posture_digest(None) == _gates_only_digest(tp.TrustPosture(gates={}))


def test_live_posture_digest_pinned() -> None:
    posture = tp.load_posture(path=REPO_ROOT / "TRUST_POSTURE.md")
    assert posture.sync_windows == ()
    assert tp.posture_digest(posture) == LIVE_DIGEST


def test_window_changes_digest(tmp_path: Path) -> None:
    base = tp.posture_digest(load(tmp_path))
    with_window = tp.posture_digest(load(tmp_path, [WINDOW]))
    widened = tp.posture_digest(load(tmp_path, [window(auto_merge_ceiling="implementation")]))
    assert len({base, with_window, widened}) == 3


def test_digest_ignores_ordering(tmp_path: Path) -> None:
    other = window(id="weekly", cadence="0 5 * * 0")
    a = tp.posture_digest(load(tmp_path, [WINDOW, other]))
    b = tp.posture_digest(load(tmp_path, [other, WINDOW]))
    assert a == b
    flipped = window(
        skills=list(reversed(WINDOW["skills"])),
        allowed_sources=list(reversed(WINDOW["allowed_sources"])),
    )
    assert tp.posture_digest(load(tmp_path, [WINDOW])) == tp.posture_digest(
        load(tmp_path, [flipped])
    )


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #

def test_show_prints_sync_windows_after_gates(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    path = contract(tmp_path, [WINDOW])
    assert tp._main(["show", str(path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    idx = lines.index("sync_windows:")
    assert all(g.value in " ".join(lines[:idx]) for g in tp.Gate)
    assert "nightly-drain" in lines[idx + 1]
    assert "ceiling=plan" in lines[idx + 1]


def test_show_without_windows(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert tp._main(["show", str(contract(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert "sync_windows:\n  (none declared)" in out


# --------------------------------------------------------------------------- #
# Live files
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["TRUST_POSTURE.md", "TRUST_POSTURE.template.md"])
def test_live_and_template_validate_with_no_window(name: str) -> None:
    path = REPO_ROOT / name
    assert tp.validate_posture_file(path) == []
    assert tp.load_posture(path=path).sync_windows == ()
