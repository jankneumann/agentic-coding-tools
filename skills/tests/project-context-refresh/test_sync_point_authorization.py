"""Explicit sync-point authorization for the mutating refresh path (ri-11 D5).

``checkout_policy`` has carried an ``approved_sync_point`` branch since it was
written, with nothing that reaches it: ``cli._require_mutation`` always
classified with ``sync_point=False``, so ``refresh`` was mechanically unable to
run from the shared checkout where ``merge-pull-requests`` operates. These tests
pin both halves of the contract:

* unauthorized — the classification is ``shared_checkout_blocked`` and the
  mutating path refuses;
* authorized — ``--sync-point`` classifies as ``approved_sync_point`` and the
  mutating path runs.

Assertions are on the ``PolicyReason`` values, never on the human message beside
them, so re-wording a message cannot silently retire the guard.

Authorization is an explicit *caller* opt-in. The environment must not be able to
grant it: an environment sniff would re-open shared-checkout writes for every
skill that happens to run on ``main``, which is precisely the property the guard
exists to protect. That is tested here rather than assumed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import cli
from registry import Producer, ProducerError, ProducerSpec, register

# ``skills/shared`` holds the checkout-policy guard. ``cli`` puts it on sys.path
# on import, but this module must not depend on that side effect surviving an
# import-order change, so it inserts the directory itself.
_SHARED_DIR = Path(cli.__file__).resolve().parents[2] / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

import checkout_policy

FULL_SHA = "b" * 40
PRODUCER_ID = "documentation.inventory"


class _FreshProducer(Producer):
    """A trivially fresh producer, so these tests exercise the guard only."""

    def __init__(self, pid: str = PRODUCER_ID) -> None:
        self.spec = ProducerSpec(
            producer_id=pid,
            producer_version="1",
            owner="owner",
            inputs=("x",),
            outputs=(),
        )

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        from _runtime import (
            ProducerResult,
            ProducerStatus,
            ValidationResult,
            ValidationStatus,
        )

        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version="1",
            status=ProducerStatus.FRESH,
            validations=(
                ValidationResult(
                    validation_id=f"{self.spec.producer_id}-check",
                    status=ValidationStatus.PASSED,
                    summary="ok",
                ),
            ),
        )


@pytest.fixture
def shared_checkout(tmp_path, monkeypatch):
    """A real git checkout that is *not* a managed worktree, on a local profile.

    ``AGENT_EXECUTION_ENV=local`` is pinned explicitly: the checkout policy allows
    every mutation when the execution environment provides isolation, so a test
    that inherited a cloud profile would pass without ever reaching the branch
    under test.
    """
    monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    register(_FreshProducer())
    return tmp_path


def _refresh_argv(repository, *flags: str) -> list[str]:
    # Producer-scoped so the run exercises the guard and one trivial producer,
    # not the durable store or the architecture owner.
    return [
        "--repo",
        str(repository),
        "--revision",
        FULL_SHA,
        "refresh",
        *flags,
        "--producer",
        PRODUCER_ID,
    ]


def test_unauthorized_shared_checkout_classifies_as_blocked(shared_checkout):
    policy = checkout_policy.classify_checkout(cwd=shared_checkout, sync_point=False)

    assert policy.allowed is False
    assert policy.reason == "shared_checkout_blocked"


def test_refresh_refuses_a_shared_checkout_without_authorization(shared_checkout):
    with pytest.raises(ProducerError) as excinfo:
        cli.main(_refresh_argv(shared_checkout))

    # The refusal must carry the policy decision, not just a string: assert the
    # machine-readable reason the guard produced.
    cause = excinfo.value.__cause__
    assert isinstance(cause, checkout_policy.CheckoutPolicyError)
    assert cause.policy.reason == "shared_checkout_blocked"


def test_sync_point_authorization_classifies_as_approved(shared_checkout):
    policy = checkout_policy.classify_checkout(cwd=shared_checkout, sync_point=True)

    assert policy.allowed is True
    assert policy.reason == "approved_sync_point"


def test_refresh_runs_on_a_shared_checkout_with_sync_point_authorization(
    shared_checkout, capsys
):
    code = cli.main(_refresh_argv(shared_checkout, "--sync-point"))
    capsys.readouterr()

    assert code == 0


def test_the_flag_threads_sync_point_into_the_policy_call(shared_checkout, monkeypatch):
    """The flag must reach ``require_mutation_allowed``, not merely skip the guard.

    A ``--sync-point`` that bypassed the guard entirely would pass the
    runs-without-raising test above while removing the check instead of
    authorizing it.
    """
    seen: list[bool] = []
    real = checkout_policy.require_mutation_allowed

    def spy(**kwargs):
        seen.append(bool(kwargs.get("sync_point")))
        return real(**kwargs)

    monkeypatch.setattr(checkout_policy, "require_mutation_allowed", spy)

    cli.main(_refresh_argv(shared_checkout, "--sync-point"))

    assert seen == [True]


def test_the_default_is_unauthorized(shared_checkout, monkeypatch):
    """Safe default: without the flag the policy is still consulted with False."""
    seen: list[bool] = []
    real = checkout_policy.require_mutation_allowed

    def spy(**kwargs):
        seen.append(bool(kwargs.get("sync_point")))
        return real(**kwargs)

    monkeypatch.setattr(checkout_policy, "require_mutation_allowed", spy)

    with pytest.raises(ProducerError):
        cli.main(_refresh_argv(shared_checkout))

    assert seen == [False]


def test_authorization_is_never_inferred_from_the_environment(
    shared_checkout, monkeypatch
):
    """No environment variable may grant what only the caller can grant (D5)."""
    for name in (
        "SYNC_POINT",
        "PROJECT_CONTEXT_SYNC_POINT",
        "CONTEXT_REFRESH_SYNC_POINT",
        "CI",
    ):
        monkeypatch.setenv(name, "1")

    with pytest.raises(ProducerError):
        cli.main(_refresh_argv(shared_checkout))


def test_refresh_check_has_no_sync_point_flag(shared_checkout):
    """The read-only path has no mutation to authorize, so it offers no flag."""
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--repo",
                str(shared_checkout),
                "--revision",
                FULL_SHA,
                "refresh-check",
                "--sync-point",
            ]
        )
