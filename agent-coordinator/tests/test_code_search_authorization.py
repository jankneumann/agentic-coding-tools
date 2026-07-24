from __future__ import annotations

from dataclasses import replace

import pytest

from src.code_search_authorization import (
    ExplicitScopeRequest,
    PrincipalCodeSearchGrant,
    ScopeForbiddenError,
    ScopeRejectedError,
    WorkPackageScopeRecord,
    WorkPackageScopeRequest,
    authorize_code_search_scope,
    glob_to_postgres_regex,
    validate_safe_glob,
)

REVISION = "a" * 40


def _grant(**updates: object) -> PrincipalCodeSearchGrant:
    values: dict[str, object] = {
        "principal_id": "codex",
        "repo_slug": "agentic_coding_tools",
        "namespace_kind": "main",
        "namespace_key": "main",
        "read_allow": ("agent-coordinator/**",),
        "deny": ("agent-coordinator/private/**",),
    }
    values.update(updates)
    return PrincipalCodeSearchGrant(**values)


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "/absolute/**",
        "./relative/**",
        "a//b",
        "a/",
        "a/./b",
        "a/../b",
        "a\\b",
        "a/\x00/b",
        "a/\nb",
        "x" * 513,
    ],
)
def test_safe_glob_rejects_noncanonical_patterns(pattern: str) -> None:
    with pytest.raises(ValueError):
        validate_safe_glob(pattern)


@pytest.mark.parametrize(
    ("pattern", "matches", "misses"),
    [
        ("agent-coordinator/**", "agent-coordinator/src/code_search.py", "skills/x.py"),
        ("**/*.py", "agent-coordinator/src/code_search.py", "README.md"),
        ("src/test?.py", "src/test1.py", "src/test10.py"),
        ("src/[ab].py", "src/a.py", "src/c.py"),
    ],
)
def test_postgres_regex_has_shared_glob_semantics(pattern: str, matches: str, misses: str) -> None:
    import re

    expression = glob_to_postgres_regex(pattern)
    assert re.fullmatch(expression.removeprefix("^").removesuffix("$"), matches)
    assert not re.fullmatch(expression.removeprefix("^").removesuffix("$"), misses)


@pytest.mark.asyncio
async def test_explicit_scope_can_only_narrow_principal_grant() -> None:
    effective = await authorize_code_search_scope(
        principal_id="codex",
        repo_slug="agentic_coding_tools",
        namespace_kind="main",
        namespace_key="main",
        source_revision=REVISION,
        grant=_grant(),
        requested_scope=ExplicitScopeRequest(
            read_allow=("**",),
            deny=("agent-coordinator/generated/**",),
        ),
        paths=("agent-coordinator/src/**",),
    )

    assert effective.allows("agent-coordinator/src/code_search.py")
    assert not effective.allows("skills/worktree/scripts/worktree.py")
    assert not effective.allows("agent-coordinator/private/key.py")
    assert not effective.allows("agent-coordinator/generated/models.py")
    assert not effective.allows("agent-coordinator/tests/test_code_search.py")
    assert effective.allow_path_regexes
    assert effective.deny_path_regexes
    assert effective.path_regexes


@pytest.mark.asyncio
async def test_deny_wins_over_every_allow_layer() -> None:
    effective = await authorize_code_search_scope(
        principal_id="codex",
        repo_slug="agentic_coding_tools",
        namespace_kind="main",
        namespace_key="main",
        source_revision=REVISION,
        grant=_grant(deny=("agent-coordinator/**/secret*.py",)),
        requested_scope=ExplicitScopeRequest(
            read_allow=("agent-coordinator/**",),
            deny=(),
        ),
    )
    assert not effective.allows("agent-coordinator/src/secret_key.py")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grant",
    [
        None,
        _grant(principal_id="other"),
        _grant(repo_slug="other_repo"),
        _grant(namespace_kind="feature"),
        _grant(namespace_kind="feature", namespace_key="other"),
    ],
)
async def test_principal_grant_is_bound_to_identity_repo_and_namespace(
    grant: PrincipalCodeSearchGrant | None,
) -> None:
    with pytest.raises(ScopeForbiddenError):
        await authorize_code_search_scope(
            principal_id="codex",
            repo_slug="agentic_coding_tools",
            namespace_kind="main",
            namespace_key="main",
            source_revision=REVISION,
            grant=grant,
            requested_scope=ExplicitScopeRequest(
                read_allow=("agent-coordinator/**",),
                deny=(),
            ),
        )


@pytest.mark.asyncio
async def test_work_package_scope_is_bound_to_immutable_provenance() -> None:
    async def resolver(
        repo_slug: str,
        change_id: str,
        package_id: str,
        source_revision: str,
    ) -> WorkPackageScopeRecord | None:
        assert (repo_slug, change_id, package_id, source_revision) == (
            "agentic_coding_tools",
            "change",
            "wp-service",
            REVISION,
        )
        return WorkPackageScopeRecord(
            repo_slug=repo_slug,
            change_id=change_id,
            package_id=package_id,
            source_revision=source_revision,
            read_allow=("agent-coordinator/src/**",),
            deny=("agent-coordinator/src/generated/**",),
        )

    effective = await authorize_code_search_scope(
        principal_id="codex",
        repo_slug="agentic_coding_tools",
        namespace_kind="main",
        namespace_key="main",
        source_revision=REVISION,
        grant=_grant(),
        requested_scope=WorkPackageScopeRequest(
            change_id="change",
            package_id="wp-service",
            scope_revision=REVISION,
        ),
        work_package_resolver=resolver,
    )

    assert effective.source == "work_package"
    assert effective.authority == "work_package_registry"
    assert effective.allows("agent-coordinator/src/code_search.py")
    assert not effective.allows("agent-coordinator/tests/test_code_search.py")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_resolver", "stale", "cross_repo"])
async def test_work_package_scope_rejects_stale_or_cross_repository_replay(
    failure: str,
) -> None:
    request = WorkPackageScopeRequest(
        change_id="change",
        package_id="wp-service",
        scope_revision=OTHER_REVISION if failure == "stale" else REVISION,
    )

    async def resolver(
        repo_slug: str,
        change_id: str,
        package_id: str,
        source_revision: str,
    ) -> WorkPackageScopeRecord | None:
        record = WorkPackageScopeRecord(
            repo_slug=repo_slug,
            change_id=change_id,
            package_id=package_id,
            source_revision=source_revision,
            read_allow=("agent-coordinator/**",),
            deny=(),
        )
        return replace(record, repo_slug="other_repo") if failure == "cross_repo" else record

    with pytest.raises(ScopeRejectedError):
        await authorize_code_search_scope(
            principal_id="codex",
            repo_slug="agentic_coding_tools",
            namespace_kind="main",
            namespace_key="main",
            source_revision=REVISION,
            grant=_grant(),
            requested_scope=request,
            work_package_resolver=None if failure == "missing_resolver" else resolver,
        )


OTHER_REVISION = "b" * 40
