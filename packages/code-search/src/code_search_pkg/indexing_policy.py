"""Fail-closed, path-only eligibility policy evaluated before source reads."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path, PurePosixPath

from pathspec import PathSpec

from .source_proof import SourceProofError, normalize_repository_path

POLICY_VERSION = 1
HARD_SECURITY_POLICY_VERSION = 1
SECRET_SCANNER_POLICY = "local_required"
_GITIGNORE_TIMEOUT_SECONDS = 10.0

_SECRET_BASENAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "service-account.json",
        "service_account.json",
    }
)
_SECRET_SUFFIXES = frozenset({".cer", ".crt", ".key", ".p12", ".pem", ".pfx"})
_GENERATED_OR_DEPENDENCY_DIRS = frozenset(
    {
        ".cache",
        ".coverage",
        ".git",
        ".gradle",
        ".mypy_cache",
        ".next",
        ".nuxt",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".turbo",
        ".venv",
        "__pycache__",
        "bower_components",
        "build",
        "coverage",
        "dist",
        "generated",
        "node_modules",
        "out",
        "target",
        "vendor",
        "venv",
    }
)


class PolicyError(RuntimeError):
    """A sanitized policy failure that must stop indexing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EligibilityReason(StrEnum):
    ELIGIBLE = "eligible"
    PATH_ESCAPE = "path_escape"
    HARD_SECRET_PATH = "hard_secret_path"
    GENERATED_OR_DEPENDENCY = "generated_or_dependency"
    DENIED = "denied"
    NOT_INCLUDED = "not_included"
    EXCLUDED = "excluded"
    GITIGNORED = "gitignored"
    OUTSIDE_READ_SCOPE = "outside_read_scope"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    path: str
    eligible: bool
    reason: EligibilityReason


@dataclass(frozen=True, slots=True)
class IndexingPolicy:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    read_allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    respect_gitignore: bool = True
    secret_scan: str = SECRET_SCANNER_POLICY

    def __post_init__(self) -> None:
        for field_name in ("include", "exclude", "read_allow", "deny"):
            raw_patterns = tuple(getattr(self, field_name))
            if len(raw_patterns) != len(set(raw_patterns)):
                raise PolicyError("invalid_policy", "policy rules must be unique")
            normalized = tuple(
                sorted(_validate_pattern(pattern) for pattern in raw_patterns)
            )
            _compile_patterns(normalized)
            object.__setattr__(self, field_name, normalized)
        if self.respect_gitignore is not True:
            raise PolicyError(
                "invalid_policy",
                "indexing policy must respect Git ignore rules",
            )
        if self.secret_scan != SECRET_SCANNER_POLICY:
            raise PolicyError(
                "invalid_policy",
                "indexing policy requires the local secret scanner",
            )

    @property
    def fingerprint(self) -> str:
        payload = {
            "deny": list(self.deny),
            "exclude": list(self.exclude),
            "hard_security_policy_version": HARD_SECURITY_POLICY_VERSION,
            "include": list(self.include),
            "policy_version": POLICY_VERSION,
            "read_allow": list(self.read_allow),
            "respect_gitignore": self.respect_gitignore,
            "secret_scan": self.secret_scan,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GitIgnoreMatcher:
    """Use local Git itself for root and nested gitignore semantics."""

    def __init__(self, repo_root: str | Path) -> None:
        self._repo_root = Path(repo_root).expanduser().resolve(strict=False)

    def __call__(self, path: str) -> bool:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repo_root),
                    "check-ignore",
                    "--quiet",
                    "--no-index",
                    "--",
                    path,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=_GITIGNORE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PolicyError(
                "gitignore_check_failed",
                "Git ignore policy could not be evaluated",
            ) from error
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise PolicyError(
            "gitignore_check_failed",
            "Git ignore policy could not be evaluated",
        )


GitIgnorePredicate = Callable[[str], bool]


def evaluate_path(
    repo_root: str | Path,
    candidate: str | Path,
    policy: IndexingPolicy,
    *,
    gitignore_matcher: GitIgnorePredicate | None = None,
) -> EligibilityDecision:
    """Evaluate a candidate without opening it; hard and explicit denies win."""

    try:
        path = normalize_repository_path(repo_root, candidate)
    except SourceProofError:
        return EligibilityDecision(
            path="<rejected>",
            eligible=False,
            reason=EligibilityReason.PATH_ESCAPE,
        )

    if _is_hard_secret_path(path):
        return _rejected(path, EligibilityReason.HARD_SECRET_PATH)
    if _is_generated_or_dependency(path):
        return _rejected(path, EligibilityReason.GENERATED_OR_DEPENDENCY)
    if _matches_any(path, policy.deny):
        return _rejected(path, EligibilityReason.DENIED)
    if policy.include and not _matches_any(path, policy.include):
        return _rejected(path, EligibilityReason.NOT_INCLUDED)
    if _matches_any(path, policy.exclude):
        return _rejected(path, EligibilityReason.EXCLUDED)

    matcher = gitignore_matcher
    if matcher is None:
        matcher = GitIgnoreMatcher(repo_root)
    try:
        if policy.respect_gitignore and matcher(path):
            return _rejected(path, EligibilityReason.GITIGNORED)
    except PolicyError:
        raise
    except Exception as error:
        raise PolicyError(
            "gitignore_check_failed",
            "Git ignore policy could not be evaluated",
        ) from error

    if policy.read_allow and not _matches_any(path, policy.read_allow):
        return _rejected(path, EligibilityReason.OUTSIDE_READ_SCOPE)
    return EligibilityDecision(
        path=path,
        eligible=True,
        reason=EligibilityReason.ELIGIBLE,
    )


def _rejected(path: str, reason: EligibilityReason) -> EligibilityDecision:
    return EligibilityDecision(path=path, eligible=False, reason=reason)


def _validate_pattern(pattern: object) -> str:
    if not isinstance(pattern, str) or not pattern or "\x00" in pattern:
        raise PolicyError("invalid_policy", "policy contains an invalid path rule")
    normalized = pattern.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or normalized.startswith("!"):
        raise PolicyError("invalid_policy", "policy contains an invalid path rule")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        raise PolicyError("invalid_policy", "policy contains an invalid path rule")
    return normalized


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return bool(patterns) and _compile_patterns(patterns).match_file(path)


@lru_cache(maxsize=256)
def _compile_patterns(patterns: tuple[str, ...]) -> PathSpec:
    try:
        return PathSpec.from_lines("gitignore", patterns)
    except Exception as error:
        raise PolicyError(
            "invalid_policy",
            "policy contains an invalid path rule",
        ) from error


def _is_hard_secret_path(path: str) -> bool:
    pure = PurePosixPath(path)
    lower_parts = tuple(part.lower() for part in pure.parts)
    basename = lower_parts[-1]
    if basename == ".env" or basename.startswith(".env."):
        return True
    if basename in _SECRET_BASENAMES:
        return True
    if any(part.startswith((".secret", ".credential")) for part in lower_parts):
        return True
    return pure.suffix.lower() in _SECRET_SUFFIXES


def _is_generated_or_dependency(path: str) -> bool:
    lower_parts = {part.lower() for part in PurePosixPath(path).parts}
    if lower_parts & _GENERATED_OR_DEPENDENCY_DIRS:
        return True
    lowered = path.lower()
    return lowered.endswith((".min.js", ".min.css", ".map"))
