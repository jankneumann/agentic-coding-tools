"""Tests for IMPL_REVIEW R2-id=13: SSE token-in-URL access-log redaction.

Verifies that ``install_token_redaction_filter`` masks ``token=<value>``
substrings before they reach a log handler — the JWT in
``/events/work?change_ids=…&token=<JWT>`` must never appear in stdout
or any log aggregator.
"""
from __future__ import annotations

import io
import logging

from src.sse_log_redaction import (
    install_token_redaction_filter,
    redact_token,
)


def test_redact_token_pure_function() -> None:
    """Pure-function form replaces token= values across common URL shapes."""
    samples = [
        ("GET /events/work?change_ids=abc&token=eyJabc.def.ghi HTTP/1.1",
         "GET /events/work?change_ids=abc&token=<redacted> HTTP/1.1"),
        ("token=secret-abc-123",
         "token=<redacted>"),
        # Multiple tokens (defensive): each gets redacted independently
        ("foo?token=A&bar?token=B",
         "foo?token=<redacted>&bar?token=<redacted>"),
        # Case-insensitive match — handlers may title-case query strings
        ("Token=ABC",
         "token=<redacted>"),
        # No token present → unchanged
        ("GET /health HTTP/1.1",
         "GET /health HTTP/1.1"),
    ]
    for input_, expected in samples:
        assert redact_token(input_) == expected, (
            f"redact_token({input_!r}) → expected {expected!r}, "
            f"got {redact_token(input_)!r}"
        )


def test_filter_redacts_string_msg_when_attached_to_logger() -> None:
    """Filter rewrites record.msg so downstream handlers see the redacted form."""
    logger = logging.getLogger("test_sse_redaction_msg")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    # Reset the install marker for a clean test
    if hasattr(logger, "_sse_token_redaction_installed"):
        delattr(logger, "_sse_token_redaction_installed")

    install_token_redaction_filter(logger.name)

    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(CaptureHandler())
    logger.info(
        "127.0.0.1:54321 - 'GET /events/work?token=eyJABC.def.ghi HTTP/1.1' 200 OK",
    )
    assert len(captured) == 1
    assert "eyJABC" not in captured[0], f"Token leaked: {captured[0]}"
    assert "token=<redacted>" in captured[0]


def test_filter_redacts_string_args() -> None:
    """When the access logger uses %-formatting with string args, the args are
    scrubbed before formatting so the final emitted line has no token.

    Mirrors uvicorn's actual access-log format where the FULL path (including
    query string) is passed as one arg, not split into path + query.
    """
    logger = logging.getLogger("test_sse_redaction_args")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    if hasattr(logger, "_sse_token_redaction_installed"):
        delattr(logger, "_sse_token_redaction_installed")

    install_token_redaction_filter(logger.name)

    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(CaptureHandler())
    # uvicorn passes the full request-line (including query string) as a
    # single %s arg; that's the only arg that can carry the JWT.
    logger.info(
        '%s - "%s %s" %d %s',
        "127.0.0.1:54321",
        "GET",
        "/events/work?change_ids=abc&token=eyJ.real.jwt HTTP/1.1",
        200,
        "OK",
    )
    assert len(captured) == 1
    assert "eyJ" not in captured[0]
    assert "token=<redacted>" in captured[0]


def test_install_is_idempotent() -> None:
    """Calling install twice doesn't stack two filters or break logging."""
    logger = logging.getLogger("test_sse_redaction_idempotent")
    logger.handlers.clear()
    # Reset marker
    if hasattr(logger, "_sse_token_redaction_installed"):
        delattr(logger, "_sse_token_redaction_installed")

    # Capture initial filter count
    initial_filter_count = len(logger.filters)

    install_token_redaction_filter(logger.name)
    after_first = len(logger.filters)
    install_token_redaction_filter(logger.name)
    after_second = len(logger.filters)

    assert after_first == initial_filter_count + 1
    assert after_second == after_first, (
        "Re-installing must be a no-op; got "
        f"filters before/first/second: "
        f"{initial_filter_count}/{after_first}/{after_second}"
    )


def test_filter_passes_through_non_token_records() -> None:
    """Logger records without 'token=' substring are emitted unchanged."""
    logger = logging.getLogger("test_sse_redaction_passthrough")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    if hasattr(logger, "_sse_token_redaction_installed"):
        delattr(logger, "_sse_token_redaction_installed")

    install_token_redaction_filter(logger.name)

    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(CaptureHandler())
    logger.info("/health response 200")
    assert captured == ["/health response 200"]


def test_filter_does_not_clobber_non_string_args() -> None:
    """Filter scrubs string args but leaves non-string args (ints, dicts)
    untouched so downstream formatting succeeds."""
    logger = logging.getLogger("test_sse_redaction_nonstring")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    if hasattr(logger, "_sse_token_redaction_installed"):
        delattr(logger, "_sse_token_redaction_installed")

    install_token_redaction_filter(logger.name)

    captured: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(CaptureHandler())
    logger.info("status=%d count=%d", 200, 5)
    assert captured == ["status=200 count=5"]


def test_filter_handles_io_stream_capture() -> None:
    """End-to-end: an in-memory StreamHandler sees the redacted output."""
    logger = logging.getLogger("test_sse_redaction_stream")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    if hasattr(logger, "_sse_token_redaction_installed"):
        delattr(logger, "_sse_token_redaction_installed")

    install_token_redaction_filter(logger.name)

    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(h)
    # Mirror uvicorn: full path-with-query as one arg
    logger.info(
        '%s - "%s %s" %d',
        "192.0.2.10",
        "GET",
        "/events/work?token=eyJSECRET-TOKEN-XYZ HTTP/1.1",
        200,
    )
    output = stream.getvalue()
    assert "eyJSECRET-TOKEN-XYZ" not in output
    assert "token=<redacted>" in output
