"""Guardrails engine for Agent Coordinator.

Provides deterministic pattern-matching to detect and block destructive operations.
Patterns are stored in the database with a hardcoded fallback registry.
"""

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db

# =============================================================================
# Hardcoded fallback patterns (used when database is unavailable)
# =============================================================================

FALLBACK_PATTERNS: list[dict[str, Any]] = [
    {
        "name": "git_force_push",
        "category": "git",
        "pattern": r"git\s+push\s+.*--force",
        "severity": "block",
        "min_trust_level": 3,
    },
    {
        "name": "git_reset_hard",
        "category": "git",
        "pattern": r"git\s+reset\s+--hard",
        "severity": "block",
        "min_trust_level": 3,
    },
    {
        "name": "git_clean_force",
        "category": "git",
        "pattern": r"git\s+clean\s+-[fd]",
        "severity": "block",
        "min_trust_level": 3,
    },
    {
        "name": "git_branch_delete",
        "category": "git",
        "pattern": r"git\s+(branch\s+-D|push\s+.*--delete)",
        "severity": "warn",
        "min_trust_level": 3,
    },
    {
        "name": "rm_recursive_force",
        "category": "file",
        "pattern": r"rm\s+-r[f]?\s+/",
        "severity": "block",
        "min_trust_level": 4,
    },
    {
        "name": "rm_rf",
        "category": "file",
        "pattern": r"rm\s+-rf\s+",
        "severity": "block",
        "min_trust_level": 3,
    },
    {
        "name": "drop_table",
        "category": "database",
        "pattern": r"DROP\s+TABLE",
        "severity": "block",
        "min_trust_level": 4,
    },
    {
        "name": "truncate_table",
        "category": "database",
        "pattern": r"TRUNCATE\s+",
        "severity": "block",
        "min_trust_level": 4,
    },
    {
        "name": "env_file_modify",
        "category": "credential",
        "pattern": r"\.(env|env\.local|env\.production)",
        "severity": "warn",
        "min_trust_level": 2,
    },
    {
        "name": "credentials_file",
        "category": "credential",
        "pattern": r"(credentials|secrets|passwords)\.(json|yaml|yml|txt)",
        "severity": "warn",
        "min_trust_level": 2,
    },
    {
        "name": "deploy_command",
        "category": "deployment",
        "pattern": r"(kubectl\s+apply|terraform\s+apply|docker\s+push)",
        "severity": "block",
        "min_trust_level": 3,
    },
]


@dataclass
class GuardrailPattern:
    """A destructive operation pattern."""

    name: str
    category: str
    pattern: str
    severity: str = "block"  # 'block', 'warn', 'log'
    min_trust_level: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuardrailPattern":
        return cls(
            name=data["name"],
            category=data["category"],
            pattern=data["pattern"],
            severity=data.get("severity", "block"),
            min_trust_level=int(data.get("min_trust_level", 3)),
        )


@dataclass
class GuardrailViolation:
    """A detected guardrail violation."""

    pattern_name: str
    category: str
    severity: str
    matched_text: str | None = None
    blocked: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuardrailViolation":
        return cls(
            pattern_name=data["pattern_name"],
            category=data["category"],
            severity=data.get("severity", "block"),
            matched_text=data.get("matched_text"),
            blocked=data.get("blocked", True),
        )


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""

    safe: bool
    violations: list[GuardrailViolation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuardrailResult":
        violations = []
        for v in data.get("violations", []):
            violations.append(GuardrailViolation.from_dict(v))
        return cls(
            safe=data.get("safe", True),
            violations=violations,
        )


class GuardrailsService:
    """Service for detecting and blocking destructive operations."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db
        self._patterns_cache: list[GuardrailPattern] | None = None
        self._cache_expiry: float = 0

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def _load_patterns(self) -> list[GuardrailPattern]:
        """Load patterns from database with cache, falling back to code registry."""
        config = get_config()
        now = time.monotonic()

        if self._patterns_cache and now < self._cache_expiry:
            return self._patterns_cache

        try:
            rows = await self.db.query(
                "operation_guardrails",
                "enabled=eq.true",
            )
            self._patterns_cache = [GuardrailPattern.from_dict(row) for row in rows]
            self._cache_expiry = now + config.guardrails.patterns_cache_ttl_seconds
            return self._patterns_cache
        except Exception:
            if config.guardrails.enable_code_fallback:
                self._patterns_cache = [
                    GuardrailPattern.from_dict(p) for p in FALLBACK_PATTERNS
                ]
                # Short cache for fallback — retry DB sooner
                self._cache_expiry = now + 30
                return self._patterns_cache
            raise

    async def check_operation(
        self,
        operation_text: str,
        file_paths: list[str] | None = None,
        trust_level: int = 2,
        agent_id: str | None = None,
    ) -> GuardrailResult:
        """Check an operation for destructive patterns.

        Args:
            operation_text: The operation text to scan (command, result, etc.)
            file_paths: File paths involved in the operation
            trust_level: Agent's trust level (higher = more permissive)
            agent_id: Agent performing the operation (for logging)

        Returns:
            GuardrailResult indicating whether the operation is safe
        """
        patterns = await self._load_patterns()
        violations: list[GuardrailViolation] = []
        safe = True

        # Combine operation text and file paths for matching
        full_text = operation_text
        if file_paths:
            full_text += "\n" + "\n".join(file_paths)

        for pattern in patterns:
            match = re.search(pattern.pattern, full_text, re.IGNORECASE)
            if match and trust_level < pattern.min_trust_level:
                blocked = pattern.severity == "block"
                if blocked:
                    safe = False

                violations.append(
                    GuardrailViolation(
                        pattern_name=pattern.name,
                        category=pattern.category,
                        severity=pattern.severity,
                        matched_text=match.group(0)[:200],
                        blocked=blocked,
                    )
                )

        result = GuardrailResult(safe=safe, violations=violations)

        # Audit: log all violations
        if violations:
            try:
                config = get_config()
                await get_audit_service().log_operation(
                    agent_id=agent_id or config.agent.agent_id,
                    operation="guardrail_violation",
                    parameters={"operation_text": operation_text[:200]},
                    result={
                        "safe": safe,
                        "violation_count": len(violations),
                        "blocked": not safe,
                        "patterns": [v.pattern_name for v in violations],
                    },
                    success=True,
                )
            except Exception as exc:
                print(
                    f"agent-coordinator: audit failed for guardrail_violation: {exc}",
                    file=sys.stderr,
                )

        return result


# Global service instance
_guardrails_service: GuardrailsService | None = None


def get_guardrails_service() -> GuardrailsService:
    """Get the global guardrails service instance."""
    global _guardrails_service
    if _guardrails_service is None:
        _guardrails_service = GuardrailsService()
    return _guardrails_service
