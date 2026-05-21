"""Access-log redaction for SSE token-in-URL.

IMPL_REVIEW R2-id=13 (high security, cross-vendor confirmed): the
``GET /events/work`` endpoint accepts the SSE auth JWT in the ``token=``
query parameter. Without redaction, uvicorn's access logger writes the full
URL — including the JWT — to stdout (and any log aggregator). The token is
short-lived but valid for the change_ids in its payload.

This module exposes ``install_token_redaction_filter()`` which registers a
``logging.Filter`` on the ``uvicorn.access`` logger that rewrites the
``token=<value>`` substring of any log record to ``token=<redacted>``. The
filter is idempotent: re-registration is a no-op.

The redaction is applied at the *logging* layer rather than the
*middleware* layer because uvicorn captures the request URL from the ASGI
scope BEFORE any ASGI middleware runs (see
``uvicorn.protocols.http.h11_impl``); rewriting scope["query_string"] in
middleware does not reach the access log line. Filter-based redaction is
also resilient to changes in uvicorn's internal log format.
"""

from __future__ import annotations

import logging
import re

_TOKEN_RE = re.compile(r"token=[^&\s\"']+", flags=re.IGNORECASE)
_FILTER_MARKER = "_sse_token_redaction_installed"


class _TokenRedactionFilter(logging.Filter):
    """Replace any ``token=<value>`` substring with ``token=<redacted>``.

    The substitution runs against both ``record.msg`` and any args that
    end up in the formatted record. Conservative on args (only strs are
    rewritten) to avoid breaking non-string args that some callers pass.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # When args are present, the token typically arrives as ONE of the
        # args (uvicorn access log format is a template like
        # '%s - "%s %s HTTP/%s" %d' with the path as an arg). Redacting
        # record.msg in that case can clobber a %s placeholder and break
        # arg-to-specifier count. Args-only redaction is the right discipline.
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(self._scrub(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: self._scrub(v) for k, v in record.args.items()}
            return True
        # No-args shape: msg is the whole formatted string and may carry the
        # token literal (e.g., logger.info("GET /events/work?token=...")).
        if isinstance(record.msg, str) and "token=" in record.msg.lower():
            record.msg = _TOKEN_RE.sub("token=<redacted>", record.msg)
        return True

    @staticmethod
    def _scrub(value: object) -> object:
        if isinstance(value, str) and "token=" in value.lower():
            return _TOKEN_RE.sub("token=<redacted>", value)
        return value


def install_token_redaction_filter(logger_name: str = "uvicorn.access") -> None:
    """Install the redaction filter on the named logger (idempotent).

    Call from ``main()`` BEFORE ``uvicorn.run`` so the filter is in place
    when the access logger emits its first request. Also safe to call from
    tests that exercise the filter against a stub logger.
    """
    logger = logging.getLogger(logger_name)
    # Idempotency: tag the logger so duplicate calls don't stack filters.
    if getattr(logger, _FILTER_MARKER, False):
        return
    logger.addFilter(_TokenRedactionFilter())
    setattr(logger, _FILTER_MARKER, True)


def redact_token(text: str) -> str:
    """Pure-function form of the redaction, for non-logging call sites.

    Useful when emitting custom audit logs or building error messages that
    might include the original request URL.
    """
    return _TOKEN_RE.sub("token=<redacted>", text)
