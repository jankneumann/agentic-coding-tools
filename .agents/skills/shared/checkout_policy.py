"""Shared checkout mutation policy for OpenSpec skills.

Local CLI runs use the shared checkout as an orchestration surface. Mutating
skills must write inside managed ``.git-worktrees/`` checkouts unless they are
explicit sync-point operations. Cloud and harness environments may write in
place because filesystem isolation is provided externally.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

try:
    from . import environment_profile
except ImportError:  # pragma: no cover - direct script execution path
    # Allow ``python skills/shared/checkout_policy.py`` from repo-root skill
    # instructions, matching the existing active_agents.py CLI style.
    _SHARED_DIR = Path(__file__).resolve().parent
    if str(_SHARED_DIR.parent) not in sys.path:
        sys.path.insert(0, str(_SHARED_DIR.parent))
    from shared import environment_profile  # type: ignore[no-redef]

PolicyReason = Literal[
    "isolated_harness",
    "managed_worktree",
    "approved_sync_point",
    "shared_checkout_blocked",
]


@dataclass(frozen=True)
class CheckoutPolicy:
    """Decision returned by the checkout mutation policy guard."""

    allowed: bool
    reason: PolicyReason
    isolation_provided: bool
    cwd: Path
    repo_root: Path
    worktree_root: Path | None
    message: str

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["cwd"] = str(self.cwd)
        data["repo_root"] = str(self.repo_root)
        data["worktree_root"] = str(self.worktree_root) if self.worktree_root else None
        return data


class CheckoutPolicyError(RuntimeError):
    """Raised when repository mutation is not allowed from this checkout."""

    def __init__(self, policy: CheckoutPolicy) -> None:
        super().__init__(policy.message)
        self.policy = policy


def classify_checkout(
    *,
    cwd: Path | str | None = None,
    repo_root: Path | str | None = None,
    sync_point: bool = False,
    agent_id: str | None = None,
) -> CheckoutPolicy:
    """Classify whether repo mutation is allowed from *cwd*.

    The function does not create worktrees. Callers that need mutation should
    first use ``worktree.py setup`` and then call this guard to verify that the
    resulting checkout is acceptable.
    """

    resolved_cwd = Path(cwd or Path.cwd()).resolve()
    resolved_repo_root = _resolve_repo_root(resolved_cwd, repo_root)
    profile = environment_profile.detect(agent_id=agent_id)
    worktree_root = _managed_worktree_root(resolved_cwd, resolved_repo_root)

    if profile.isolation_provided:
        return CheckoutPolicy(
            allowed=True,
            reason="isolated_harness",
            isolation_provided=True,
            cwd=resolved_cwd,
            repo_root=resolved_repo_root,
            worktree_root=worktree_root,
            message=(
                "Mutation allowed: execution environment already provides "
                "filesystem isolation."
            ),
        )

    if worktree_root is not None:
        return CheckoutPolicy(
            allowed=True,
            reason="managed_worktree",
            isolation_provided=False,
            cwd=resolved_cwd,
            repo_root=resolved_repo_root,
            worktree_root=worktree_root,
            message=f"Mutation allowed inside managed worktree: {worktree_root}",
        )

    if sync_point:
        return CheckoutPolicy(
            allowed=True,
            reason="approved_sync_point",
            isolation_provided=False,
            cwd=resolved_cwd,
            repo_root=resolved_repo_root,
            worktree_root=None,
            message=(
                "Mutation allowed for explicit sync-point operation. Caller "
                "must still enforce clean-tree and active-agent guards."
            ),
        )

    return CheckoutPolicy(
        allowed=False,
        reason="shared_checkout_blocked",
        isolation_provided=False,
        cwd=resolved_cwd,
        repo_root=resolved_repo_root,
        worktree_root=None,
        message=(
            "Mutation blocked from local shared checkout. Run worktree.py setup "
            "and perform writes inside the managed worktree, or invoke an "
            "explicit sync-point skill with its clean-tree and active-agent guards."
        ),
    )


def require_mutation_allowed(
    *,
    cwd: Path | str | None = None,
    repo_root: Path | str | None = None,
    sync_point: bool = False,
    agent_id: str | None = None,
) -> CheckoutPolicy:
    """Return the policy or raise when mutation is not allowed."""

    policy = classify_checkout(
        cwd=cwd,
        repo_root=repo_root,
        sync_point=sync_point,
        agent_id=agent_id,
    )
    if not policy.allowed:
        raise CheckoutPolicyError(policy)
    return policy


def _resolve_repo_root(cwd: Path, repo_root: Path | str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()

    parts = cwd.parts
    if ".git-worktrees" in parts:
        marker_index = parts.index(".git-worktrees")
        if marker_index > 0:
            return Path(*parts[:marker_index]).resolve()

    git_root = _git_toplevel(cwd)
    if git_root is not None:
        return git_root
    return cwd


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    root = result.stdout.strip()
    return Path(root).resolve() if root else None


def _managed_worktree_root(cwd: Path, repo_root: Path) -> Path | None:
    marker = repo_root / ".git-worktrees"
    try:
        relative = cwd.relative_to(marker)
    except ValueError:
        return None

    parts = relative.parts
    if not parts:
        return None
    # Single-agent: .git-worktrees/<change-id>
    # Parallel: .git-worktrees/<change-id>/<agent-id>
    depth = 2 if len(parts) >= 2 and _looks_like_agent_worktree(parts[1]) else 1
    return marker.joinpath(*parts[:depth]).resolve()


def _looks_like_agent_worktree(path_part: str) -> bool:
    return path_part.startswith(("wp-", "v")) or path_part in {
        "cleanup",
        "integrator",
    }


def _cmd_require_mutation(args: argparse.Namespace) -> int:
    policy = classify_checkout(
        cwd=args.cwd,
        repo_root=args.repo_root,
        sync_point=args.sync_point,
        agent_id=args.agent_id,
    )
    if args.json:
        print(json.dumps(policy.to_jsonable(), indent=2, sort_keys=True))
    elif policy.allowed:
        print(policy.message)
    else:
        print(policy.message, file=sys.stderr)
    return 0 if policy.allowed else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checkout_policy",
        description="Enforce local shared-checkout mutation policy.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    require = sub.add_parser(
        "require-mutation",
        help="Exit non-zero unless mutation is allowed from this checkout.",
    )
    require.add_argument("--cwd", default=None, help="Directory to classify.")
    require.add_argument("--repo-root", default=None, help="Shared repository root.")
    require.add_argument("--sync-point", action="store_true")
    require.add_argument("--agent-id", default=None)
    require.add_argument("--json", action="store_true")
    require.set_defaults(func=_cmd_require_mutation)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
