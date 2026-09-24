"""Durable, bounded audit delivery port for local sandbox dispatch."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request


MAX_RECORD_BYTES = 64 * 1024
MAX_OUTBOX_BYTES = 64 * 1024 * 1024
MAX_OUTBOX_RECORDS = 10_000
MAX_DRAIN_RECORDS = 100
MAX_DRAIN_SECONDS = 5.0
LOCK_TIMEOUT_SECONDS = 5.0
MAX_DEAD_LETTER_BYTES = 64 * 1024 * 1024
MAX_DEAD_LETTER_FILES = 16
MAX_DEAD_LETTER_TOTAL_BYTES = 1024 * 1024 * 1024
DEAD_LETTER_RETENTION_SECONDS = 30 * 24 * 60 * 60

logger = logging.getLogger(__name__)


class AuditDeliveryError(RuntimeError):
    """Evidence could not be delivered or durably queued."""


@dataclass(frozen=True)
class AuditDeliveryResult:
    queued: bool
    acknowledged: bool


@dataclass(frozen=True)
class OutboxTelemetry:
    active_records: int
    active_bytes: int
    oldest_age_seconds: float | None
    drain_failures: int
    permanent_rejections: int
    dead_letter_records: int
    dead_letter_bytes: int


Sender = Callable[[dict[str, Any]], tuple[int, dict[str, Any]]]


def _unavailable_sender(_event: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    raise OSError("sandbox audit endpoint is not configured")


def _canonical_line(event: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                event, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise AuditDeliveryError(f"event is not canonical JSON: {exc}") from exc


class _NoRedirectHandler(url_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class CoordinatorAuditSender:
    """Small stdlib transport for ``POST /dispatch/sandbox-events``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 3.0,
    ) -> None:
        parsed = url_parse.urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("invalid coordinator base URL")
        if not api_key:
            raise ValueError("coordinator API key is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._url = f"{base_url.rstrip('/')}/dispatch/sandbox-events"
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._opener = url_request.build_opener(_NoRedirectHandler())

    def __call__(self, event: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        body = _canonical_line(event).rstrip(b"\n")
        request = url_request.Request(
            self._url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": self._api_key,
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                status = response.getcode()
                raw = response.read(MAX_RECORD_BYTES + 1)
        except url_error.HTTPError as exc:
            status = exc.code
            if 300 <= status < 400:
                raise AuditDeliveryError(
                    f"coordinator sandbox audit redirect refused: HTTP {status}"
                ) from exc
            raw = exc.read(MAX_RECORD_BYTES + 1)
        except (url_error.URLError, TimeoutError, OSError) as exc:
            raise OSError("coordinator sandbox audit endpoint unavailable") from exc
        try:
            payload = json.loads(raw) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        return status, payload if isinstance(payload, dict) else {}


class SandboxAuditPort:
    """Deliver synchronously, falling back only for transport/5xx failures."""

    def __init__(
        self,
        *,
        state_root: Path,
        checkout_roots: list[Path],
        sender: Sender = _unavailable_sender,
        max_record_bytes: int = MAX_RECORD_BYTES,
        max_outbox_bytes: int = MAX_OUTBOX_BYTES,
        max_records: int = MAX_OUTBOX_RECORDS,
        max_dead_letter_bytes: int = MAX_DEAD_LETTER_BYTES,
        max_dead_letter_files: int = MAX_DEAD_LETTER_FILES,
        max_dead_letter_total_bytes: int = MAX_DEAD_LETTER_TOTAL_BYTES,
        dead_letter_retention_seconds: float = DEAD_LETTER_RETENTION_SECONDS,
    ) -> None:
        self.state_root = state_root
        self.checkout_roots = checkout_roots
        self.sender = sender
        self.max_record_bytes = max_record_bytes
        self.max_outbox_bytes = max_outbox_bytes
        self.max_records = max_records
        self.max_dead_letter_bytes = max_dead_letter_bytes
        self.max_dead_letter_files = max_dead_letter_files
        self.max_dead_letter_total_bytes = max_dead_letter_total_bytes
        self.dead_letter_retention_seconds = dead_letter_retention_seconds
        self._validate_and_create_root()

    @property
    def outbox_path(self) -> Path:
        return self.state_root / "outbox.jsonl"

    @property
    def dead_letter_path(self) -> Path:
        return self.state_root / "dead-letter.jsonl"

    def _validate_and_create_root(self) -> None:
        if not self.state_root.is_absolute():
            raise AuditDeliveryError("sandbox audit state root must be absolute")
        for candidate in (self.state_root, *self.state_root.parents):
            if candidate.exists() and candidate.is_symlink():
                raise AuditDeliveryError("sandbox audit state root cannot contain symlinks")
        root = self.state_root.resolve(strict=False)
        for checkout in self.checkout_roots:
            checkout = checkout.resolve(strict=False)
            if root == checkout or checkout in root.parents:
                raise AuditDeliveryError("sandbox audit state root must be outside checkout roots")
        self.state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.state_root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise AuditDeliveryError("sandbox audit state root must be an operator-owned directory")
        os.chmod(self.state_root, 0o700)

    def _open_secure(self, path: Path, flags: int = os.O_RDWR | os.O_CREAT) -> int:
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            os.close(fd)
            raise AuditDeliveryError(f"unsafe audit file: {path}")
        os.fchmod(fd, 0o600)
        return fd

    def _locked(self):
        fd = self._open_secure(self.state_root / ".lock")
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise AuditDeliveryError("sandbox audit lock timeout")
                time.sleep(0.01)

    @staticmethod
    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.outbox_path.exists():
            return []
        fd = self._open_secure(self.outbox_path)
        try:
            with os.fdopen(os.dup(fd), "r", encoding="utf-8") as stream:
                records = [json.loads(line) for line in stream if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            raise AuditDeliveryError(f"invalid sandbox audit outbox: {exc}") from exc
        finally:
            os.close(fd)
        if not all(isinstance(record, dict) for record in records):
            raise AuditDeliveryError("invalid sandbox audit outbox record")
        return records

    def _atomic_write(self, path: Path, records: list[dict[str, Any]]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=self.state_root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as stream:
                for record in records:
                    stream.write(_canonical_line(record))
                stream.flush()
                os.fsync(stream.fileno())
            os.close(fd)
            fd = -1
            os.replace(tmp_name, path)
            directory_fd = os.open(self.state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

    def _append_outbox(self, event: dict[str, Any]) -> None:
        line = _canonical_line(event)
        if len(line) > self.max_record_bytes:
            raise AuditDeliveryError("event exceeds 64 KiB record limit")
        lock_fd = self._locked()
        try:
            records = self._read_records()
            current_bytes = sum(len(_canonical_line(record)) for record in records)
            if len(records) >= self.max_records:
                raise AuditDeliveryError("active outbox record limit reached")
            if current_bytes + len(line) > self.max_outbox_bytes:
                raise AuditDeliveryError("active outbox byte limit reached")
            records.append(event)
            self._atomic_write(self.outbox_path, records)
        finally:
            self._unlock(lock_fd)

    def record(self, event: dict[str, Any]) -> AuditDeliveryResult:
        line = _canonical_line(event)
        if len(line) > self.max_record_bytes:
            raise AuditDeliveryError("event exceeds 64 KiB record limit")
        self.drain()
        try:
            status, _payload = self.sender(event)
        except (OSError, TimeoutError):
            self._append_outbox(event)
            return AuditDeliveryResult(queued=True, acknowledged=False)
        if status in (200, 201):
            return AuditDeliveryResult(queued=False, acknowledged=True)
        if status >= 500:
            self._append_outbox(event)
            return AuditDeliveryResult(queued=True, acknowledged=False)
        raise AuditDeliveryError(f"permanent rejection from audit endpoint: HTTP {status}")

    def _append_dead(self, event: dict[str, Any], status: int, payload: dict[str, Any]) -> None:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        metadata = {
            "event": event,
            "response_status": status,
            "response": {"detail": str(detail)[:500]} if detail is not None else {},
        }
        line_size = len(_canonical_line(metadata))
        if line_size > self.max_dead_letter_bytes:
            raise AuditDeliveryError("dead-letter record exceeds active file limit")

        now = time.time()
        rotated = sorted(self.state_root.glob("dead-letter.*.jsonl"))
        for path in rotated:
            if now - path.stat().st_mtime > self.dead_letter_retention_seconds:
                path.unlink()
        rotated = sorted(self.state_root.glob("dead-letter.*.jsonl"))
        records: list[dict[str, Any]] = []
        if self.dead_letter_path.exists():
            fd = self._open_secure(self.dead_letter_path)
            try:
                with os.fdopen(os.dup(fd), "r", encoding="utf-8") as stream:
                    records = [json.loads(line) for line in stream if line.strip()]
            finally:
                os.close(fd)
        active_bytes = sum(len(_canonical_line(record)) for record in records)
        if active_bytes + line_size > self.max_dead_letter_bytes and records:
            if len(rotated) >= self.max_dead_letter_files:
                raise AuditDeliveryError("dead-letter retained file limit reached")
            retained_bytes = sum(path.stat().st_size for path in rotated)
            if retained_bytes + active_bytes + line_size > self.max_dead_letter_total_bytes:
                raise AuditDeliveryError("dead-letter aggregate byte limit reached")
            rotated_path = self.state_root / f"dead-letter.{time.time_ns()}.jsonl"
            os.replace(self.dead_letter_path, rotated_path)
            directory_fd = os.open(self.state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            records = []
        else:
            total_bytes = sum(path.stat().st_size for path in rotated) + active_bytes + line_size
            if total_bytes > self.max_dead_letter_total_bytes:
                raise AuditDeliveryError("dead-letter aggregate byte limit reached")
        records.append(metadata)
        self._atomic_write(self.dead_letter_path, records)

    def _file_telemetry(self, path: Path) -> tuple[int, int]:
        fd = self._open_secure(path, os.O_RDONLY)
        try:
            byte_count = os.fstat(fd).st_size
            record_count = 0
            last_byte = b""
            while chunk := os.read(fd, 64 * 1024):
                record_count += chunk.count(b"\n")
                last_byte = chunk[-1:]
            if byte_count and last_byte != b"\n":
                record_count += 1
            return byte_count, record_count
        finally:
            os.close(fd)

    def drain(self) -> OutboxTelemetry:
        lock_fd = self._locked()
        failures = 0
        rejected = 0
        try:
            records = self._read_records()
            remaining: list[dict[str, Any]] = []
            started = time.monotonic()
            for index, event in enumerate(records):
                if index >= MAX_DRAIN_RECORDS or time.monotonic() - started >= MAX_DRAIN_SECONDS:
                    remaining.extend(records[index:])
                    break
                try:
                    status, payload = self.sender(event)
                except (OSError, TimeoutError):
                    failures += 1
                    remaining.extend(records[index:])
                    break
                if status in (200, 201):
                    continue
                if status >= 500:
                    failures += 1
                    remaining.extend(records[index:])
                    break
                self._append_dead(event, status, payload)
                rejected += 1
            if records:
                self._atomic_write(self.outbox_path, remaining)
            active_bytes = sum(len(_canonical_line(record)) for record in remaining)
            dead_bytes = 0
            dead_records = 0
            if self.dead_letter_path.exists():
                file_bytes, file_records = self._file_telemetry(self.dead_letter_path)
                dead_bytes += file_bytes
                dead_records += file_records
            for path in self.state_root.glob("dead-letter.*.jsonl"):
                file_bytes, file_records = self._file_telemetry(path)
                dead_bytes += file_bytes
                dead_records += file_records
            oldest_age = None
            if remaining and self.outbox_path.exists():
                oldest_age = max(0.0, time.time() - self.outbox_path.stat().st_mtime)
            telemetry = OutboxTelemetry(
                active_records=len(remaining),
                active_bytes=active_bytes,
                oldest_age_seconds=oldest_age,
                drain_failures=failures,
                permanent_rejections=rejected,
                dead_letter_records=dead_records,
                dead_letter_bytes=dead_bytes,
            )
            logger.info("sandbox audit outbox telemetry: %s", telemetry)
            return telemetry
        finally:
            self._unlock(lock_fd)
