from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from code_search_pkg.indexing_policy import (
    EligibilityReason,
    GitIgnoreMatcher,
    IndexingPolicy,
    PolicyError,
    evaluate_path,
)


def _policy(**overrides: object) -> IndexingPolicy:
    values: dict[str, object] = {
        "include": ("**/*.py",),
        "exclude": (),
        "read_allow": ("src/**",),
        "deny": (),
    }
    values.update(overrides)
    return IndexingPolicy(**values)


def test_eligible_path_is_normalized_and_auditable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

    decision = evaluate_path(
        repo,
        "src/./app.py",
        _policy(),
        gitignore_matcher=lambda _path: False,
    )

    assert decision.eligible is True
    assert decision.path == "src/app.py"
    assert decision.reason is EligibilityReason.ELIGIBLE


def test_explicit_deny_wins_without_consulting_later_matchers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "blocked.py").write_text("do_not_read = True\n", encoding="utf-8")

    def forbidden_gitignore_call(_path: str) -> bool:
        raise AssertionError("deny must decide before later policy checks")

    decision = evaluate_path(
        repo,
        "src/blocked.py",
        _policy(deny=("src/blocked.py",)),
        gitignore_matcher=forbidden_gitignore_call,
    )

    assert decision == decision.__class__(
        path="src/blocked.py",
        eligible=False,
        reason=EligibilityReason.DENIED,
    )


@pytest.mark.parametrize(
    "path,reason",
    [
        (".env", EligibilityReason.HARD_SECRET_PATH),
        ("src/.env.production", EligibilityReason.HARD_SECRET_PATH),
        ("config/credentials.json", EligibilityReason.HARD_SECRET_PATH),
        ("keys/id_rsa", EligibilityReason.HARD_SECRET_PATH),
        ("node_modules/pkg/index.py", EligibilityReason.GENERATED_OR_DEPENDENCY),
        (".git/config", EligibilityReason.GENERATED_OR_DEPENDENCY),
        ("build/generated.py", EligibilityReason.GENERATED_OR_DEPENDENCY),
        ("generated/client.py", EligibilityReason.GENERATED_OR_DEPENDENCY),
        ("vendor/pkg/module.py", EligibilityReason.GENERATED_OR_DEPENDENCY),
        ("src/__pycache__/cached.py", EligibilityReason.GENERATED_OR_DEPENDENCY),
    ],
)
def test_hard_exclusions_cannot_be_overridden_by_allow_rules(
    tmp_path: Path,
    path: str,
    reason: EligibilityReason,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    decision = evaluate_path(
        repo,
        path,
        _policy(include=("**",), read_allow=("**",)),
        gitignore_matcher=lambda _path: False,
    )

    assert decision.eligible is False
    assert decision.reason is reason


@pytest.mark.parametrize(
    "policy,path,reason",
    [
        (_policy(include=("src/**",)), "docs/guide.md", EligibilityReason.NOT_INCLUDED),
        (
            _policy(exclude=("src/omitted/**",)),
            "src/omitted/a.py",
            EligibilityReason.EXCLUDED,
        ),
        (
            _policy(read_allow=("lib/**",)),
            "src/app.py",
            EligibilityReason.OUTSIDE_READ_SCOPE,
        ),
    ],
)
def test_configured_intersection_records_non_sensitive_reason(
    tmp_path: Path,
    policy: IndexingPolicy,
    path: str,
    reason: EligibilityReason,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    decision = evaluate_path(
        repo,
        path,
        policy,
        gitignore_matcher=lambda _path: False,
    )

    assert decision.eligible is False
    assert decision.reason is reason


def test_nested_gitignore_rules_use_git_semantics(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "init", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    (repo / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / ".gitignore").write_text(
        "ignored.py\n!keep.tmp\n", encoding="utf-8"
    )
    matcher = GitIgnoreMatcher(repo)
    policy = _policy(include=("**",), read_allow=("**",))

    ignored = evaluate_path(repo, "src/ignored.py", policy, gitignore_matcher=matcher)
    root_rule = evaluate_path(repo, "src/drop.tmp", policy, gitignore_matcher=matcher)
    negated = evaluate_path(repo, "src/keep.tmp", policy, gitignore_matcher=matcher)

    assert ignored.reason is EligibilityReason.GITIGNORED
    assert root_rule.reason is EligibilityReason.GITIGNORED
    assert negated.eligible is True


def test_gitignore_matcher_errors_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "not-a-repository"
    repo.mkdir()

    with pytest.raises(PolicyError) as caught:
        evaluate_path(
            repo,
            "src/app.py",
            _policy(),
            gitignore_matcher=GitIgnoreMatcher(repo),
        )

    assert caught.value.code == "gitignore_check_failed"
    assert str(repo) not in str(caught.value)


def test_escaping_symlink_is_rejected_before_eligibility(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("sensitive = True\n", encoding="utf-8")
    (repo / "src" / "linked.py").symlink_to(outside)

    decision = evaluate_path(
        repo,
        "src/linked.py",
        _policy(),
        gitignore_matcher=lambda _path: False,
    )

    assert decision.reason is EligibilityReason.PATH_ESCAPE
    assert decision.eligible is False


def test_recursive_glob_matches_a_top_level_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    decision = evaluate_path(
        repo,
        "app.py",
        _policy(read_allow=()),
        gitignore_matcher=lambda _path: False,
    )

    assert decision.eligible is True


def test_gitignore_recursive_glob_matches_zero_middle_directories(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    policy = _policy(include=("src/**/test*.py",), read_allow=("src/**",))

    decision = evaluate_path(
        repo,
        "src/test_app.py",
        policy,
        gitignore_matcher=lambda _path: False,
    )

    assert decision.eligible is True


def test_policy_fingerprint_is_canonical_and_includes_hard_policy_version() -> None:
    first = IndexingPolicy(
        include=("src/**", "**/*.py"),
        exclude=("dist/**", "build/**"),
        read_allow=("src/**",),
        deny=("src/private/**",),
    )
    reordered = IndexingPolicy(
        include=("**/*.py", "src/**"),
        exclude=("build/**", "dist/**"),
        read_allow=("src/**",),
        deny=("src/private/**",),
    )
    changed = IndexingPolicy(
        include=("**/*.py", "src/**"),
        exclude=("build/**",),
        read_allow=("src/**",),
        deny=("src/private/**",),
    )

    assert first.fingerprint == reordered.fingerprint
    assert first.fingerprint != changed.fingerprint
    assert len(first.fingerprint) == 64


@pytest.mark.parametrize("pattern", ["", "/absolute/**", "../outside/**", "a/../../b"])
def test_invalid_scope_patterns_fail_closed(pattern: str) -> None:
    with pytest.raises(PolicyError) as caught:
        IndexingPolicy(read_allow=(pattern,))

    assert caught.value.code == "invalid_policy"
