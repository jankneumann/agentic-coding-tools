"""Bounded, built-in secret scanner that never sends source content remotely."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SecretScanError(RuntimeError):
    """A sanitized fail-closed scanner failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SecretScanStatus(StrEnum):
    CLEAN = "clean"
    FINDING = "finding"


@dataclass(frozen=True, slots=True)
class SecretScanResult:
    status: SecretScanStatus
    reason: str
    rule_id: str | None = None


_RULES: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "private_key",
        re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    ),
    ("aws_access_key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "credential_assignment",
        re.compile(
            rb"""(?ix)
            \b(?:password|passwd|secret|api[_-]?key|token)
            \s*[:=]\s*
            ["']?[A-Za-z0-9_./+=-]{20,}
            """
        ),
    ),
    (
        "jwt",
        re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
)


class LocalSecretScanner:
    """Scan bounded local bytes using pinned built-in rules and safe evidence."""

    def __init__(
        self,
        *,
        max_file_bytes: int = 1_048_576,
        per_file_timeout_seconds: float = 0.5,
        operation_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if per_file_timeout_seconds <= 0:
            raise ValueError("per_file_timeout_seconds must be positive")
        if operation_timeout_seconds <= 0:
            raise ValueError("operation_timeout_seconds must be positive")
        self._max_file_bytes = max_file_bytes
        self._per_file_timeout_seconds = per_file_timeout_seconds
        self._operation_timeout_seconds = operation_timeout_seconds
        self._operation_deadline: float | None = None
        self._clock = clock

    def scan_bytes(
        self,
        content: bytes,
        *,
        operation_deadline: float | None = None,
    ) -> SecretScanResult:
        """Scan bytes locally, failing closed on bounds, timeout, or internal error."""

        try:
            if not isinstance(content, bytes):
                raise TypeError("content must be bytes")
            if len(content) > self._max_file_bytes:
                raise SecretScanError(
                    "scanner_input_too_large",
                    "local secret scan input exceeds the configured bound",
                )
            started = self._clock()
            operation_deadline = self._effective_operation_deadline(
                started,
                operation_deadline,
            )
            file_deadline = started + self._per_file_timeout_seconds
            self._check_deadlines(file_deadline, operation_deadline)
            for rule_id, pattern in _RULES:
                self._check_deadlines(file_deadline, operation_deadline)
                if pattern.search(content) is not None:
                    return SecretScanResult(
                        status=SecretScanStatus.FINDING,
                        reason="secret_detected",
                        rule_id=rule_id,
                    )
            self._check_deadlines(file_deadline, operation_deadline)
            return SecretScanResult(
                status=SecretScanStatus.CLEAN,
                reason="clean",
            )
        except SecretScanError:
            raise
        except Exception as error:
            raise SecretScanError(
                "scanner_error",
                "local secret scanner failed",
            ) from error

    def scan_file(
        self,
        path: str | Path,
        *,
        operation_deadline: float | None = None,
    ) -> SecretScanResult:
        """Read at most the configured local bound and scan it."""

        try:
            with Path(path).open("rb") as handle:
                content = handle.read(self._max_file_bytes + 1)
        except (OSError, RuntimeError, ValueError) as error:
            raise SecretScanError(
                "scanner_error",
                "local secret scanner failed",
            ) from error
        return self.scan_bytes(content, operation_deadline=operation_deadline)

    def _effective_operation_deadline(
        self,
        started: float,
        requested_deadline: float | None,
    ) -> float:
        if self._operation_deadline is None:
            self._operation_deadline = started + self._operation_timeout_seconds
        if requested_deadline is None:
            return self._operation_deadline
        return min(self._operation_deadline, requested_deadline)

    def _check_deadlines(
        self,
        file_deadline: float,
        operation_deadline: float | None,
    ) -> None:
        now = self._clock()
        if now > file_deadline or (
            operation_deadline is not None and now > operation_deadline
        ):
            raise SecretScanError(
                "scanner_timeout",
                "local secret scanner exceeded its time bound",
            )
