from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from code_search_pkg.secret_scanner import (
    LocalSecretScanner,
    SecretScanError,
    SecretScanStatus,
)


def _clock(values: list[float]) -> object:
    iterator: Iterator[float] = iter(values)
    last = values[-1]

    def now() -> float:
        nonlocal iterator
        return next(iterator, last)

    return now


def test_local_scanner_accepts_ordinary_source() -> None:
    scanner = LocalSecretScanner()

    result = scanner.scan_bytes(b"def answer() -> int:\n    return 42\n")

    assert result.status is SecretScanStatus.CLEAN
    assert result.reason == "clean"
    assert result.rule_id is None


@pytest.mark.parametrize(
    "content,rule_id",
    [
        (b"-----BEGIN " + b"PRIVATE KEY-----\nnot-real\n", "private_key"),
        (b"access = " + b"AKIA" + b"A" * 16, "aws_access_key"),
        (b"password = '" + b"x" * 32 + b"'", "credential_assignment"),
    ],
)
def test_local_scanner_returns_only_sanitized_finding_evidence(
    content: bytes,
    rule_id: str,
) -> None:
    scanner = LocalSecretScanner()

    result = scanner.scan_bytes(content)

    assert result.status is SecretScanStatus.FINDING
    assert result.reason == "secret_detected"
    assert result.rule_id == rule_id
    assert content.decode(errors="ignore") not in repr(result)


def test_local_scanner_fails_closed_when_file_exceeds_bound() -> None:
    scanner = LocalSecretScanner(max_file_bytes=8)

    with pytest.raises(SecretScanError) as caught:
        scanner.scan_bytes(b"123456789")

    assert caught.value.code == "scanner_input_too_large"
    assert "123456789" not in str(caught.value)


def test_local_scanner_fails_closed_when_operation_deadline_elapsed() -> None:
    scanner = LocalSecretScanner(clock=_clock([10.0]))

    with pytest.raises(SecretScanError) as caught:
        scanner.scan_bytes(b"ordinary", operation_deadline=9.0)

    assert caught.value.code == "scanner_timeout"


def test_local_scanner_fails_closed_when_per_file_deadline_elapsed() -> None:
    scanner = LocalSecretScanner(
        per_file_timeout_seconds=0.1,
        clock=_clock([0.0, 1.0]),
    )

    with pytest.raises(SecretScanError) as caught:
        scanner.scan_bytes(b"ordinary")

    assert caught.value.code == "scanner_timeout"


def test_local_scanner_has_a_default_bounded_operation_deadline() -> None:
    current = [0.0]
    scanner = LocalSecretScanner(
        operation_timeout_seconds=30.0,
        clock=lambda: current[0],
    )
    assert scanner.scan_bytes(b"first").status is SecretScanStatus.CLEAN
    current[0] = 31.0

    with pytest.raises(SecretScanError) as caught:
        scanner.scan_bytes(b"second")

    assert caught.value.code == "scanner_timeout"


def test_scan_file_reads_only_the_bounded_local_file(tmp_path: Path) -> None:
    path = tmp_path / "source.py"
    path.write_bytes(b"print('local')\n")
    scanner = LocalSecretScanner(max_file_bytes=1024)

    result = scanner.scan_file(path)

    assert result.status is SecretScanStatus.CLEAN


def test_scan_file_sanitizes_local_io_errors(tmp_path: Path) -> None:
    missing = tmp_path / "sensitive-name-do-not-persist.txt"
    scanner = LocalSecretScanner()

    with pytest.raises(SecretScanError) as caught:
        scanner.scan_file(missing)

    assert caught.value.code == "scanner_error"
    assert str(missing) not in str(caught.value)
    assert "sensitive-name" not in str(caught.value)


def test_scanner_converts_unexpected_internal_errors_to_sanitized_failure() -> None:
    scanner = LocalSecretScanner(
        clock=lambda: (_ for _ in ()).throw(RuntimeError("raw"))
    )

    with pytest.raises(SecretScanError) as caught:
        scanner.scan_bytes(b"ordinary")

    assert caught.value.code == "scanner_error"
    assert "raw" not in str(caught.value)
