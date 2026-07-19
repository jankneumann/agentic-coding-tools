"""Cloudflare Access (Zero Trust) origin verification.

Defense-in-depth for the public coordinator API. When the coordinator is
fronted by a Cloudflare Tunnel + a Cloudflare Access application, Cloudflare
authenticates the caller at the edge — a *service token* for machine-to-machine
agents (Claude Code Web, Codex cloud, ...) or SSO for humans — and injects a
signed assertion JWT in the ``Cf-Access-Jwt-Assertion`` request header. This
module verifies that assertion at the origin so requests that did not transit
Cloudflare Access are rejected, closing the "someone reached the origin
directly" bypass.

Why verify at the origin at all? With a Cloudflare Tunnel, ``cloudflared``
connects to ``localhost:8081``, so every request — genuine Access traffic and
any direct hit alike — appears to originate from ``127.0.0.1``. The signed
assertion JWT is therefore the only trustworthy signal that a request really
passed through Access.

Standard, non-custom verification: PyJWT + Cloudflare's published JWKS
(``https://<team>.cloudflareaccess.com/cdn-cgi/access/certs``), RS256, audience
(``aud``) pinned to the Access application's Application Audience (AUD) tag, and
issuer (``iss``) pinned to the team domain. No bespoke token format or crypto.

Fail-closed: when enabled, any non-exempt request without a valid assertion is
rejected with HTTP 403. When disabled (env unset), the middleware is a
pass-through, preserving local/dev behavior.

This is implemented as a *pure ASGI* middleware (not
``starlette.middleware.base.BaseHTTPMiddleware``) so it never buffers the
long-lived SSE response served by ``GET /events/work``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Header Cloudflare Access injects after it authenticates a request at the edge.
# Starlette lower-cases header names in the ASGI scope, so we match on lower.
_ACCESS_JWT_HEADER = "cf-access-jwt-assertion"

# Path appended to the team domain to fetch the Access signing keys (JWKS).
_CERTS_PATH = "/cdn-cgi/access/certs"

# Cloudflare Access assertions are RS256-signed.
_ALGORITHMS = ["RS256"]


class CloudflareAccessError(RuntimeError):
    """Raised when Cloudflare Access is enabled but misconfigured."""


class CloudflareAccessVerifier:
    """Verify a Cloudflare Access assertion JWT.

    The signing key is resolved from Cloudflare's JWKS endpoint via
    ``jwt.PyJWKClient`` (which caches keys in-process). ``signing_key_resolver``
    can be injected in tests to avoid network access.
    """

    def __init__(
        self,
        team_domain: str,
        audiences: list[str],
        *,
        jwks_cache_seconds: int = 3600,
        signing_key_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        if not team_domain:
            raise CloudflareAccessError(
                "CF_ACCESS_TEAM_DOMAIN is required when Cloudflare Access is enabled"
            )
        if not audiences:
            raise CloudflareAccessError(
                "CF_ACCESS_AUD is required when Cloudflare Access is enabled"
            )
        self.team_domain = team_domain.rstrip("/")
        self.audiences = list(audiences)
        self.certs_url = f"{self.team_domain}{_CERTS_PATH}"
        self._jwks_cache_seconds = jwks_cache_seconds
        self._resolver = signing_key_resolver
        self._jwks_client: Any = None

    def _signing_key(self, token: str) -> Any:
        if self._resolver is not None:
            return self._resolver(token)
        import jwt  # PyJWT

        if self._jwks_client is None:
            # PyJWKClient caches fetched keys in-process for ``lifespan`` seconds
            # and only re-fetches on cache miss (e.g. Cloudflare key rotation).
            self._jwks_client = jwt.PyJWKClient(
                self.certs_url,
                cache_keys=True,
                lifespan=self._jwks_cache_seconds,
            )
        return self._jwks_client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> dict[str, Any]:
        """Return the decoded claims, or raise on any verification failure.

        This is a blocking call (JWKS fetch on cache miss + RSA verify); callers
        in async contexts should run it via ``run_in_threadpool``.
        """
        import jwt  # PyJWT

        signing_key = self._signing_key(token)
        return jwt.decode(
            token,
            signing_key,
            algorithms=_ALGORITHMS,
            audience=self.audiences,
            issuer=self.team_domain,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )


class CloudflareAccessMiddleware:
    """Pure-ASGI middleware enforcing a valid Cloudflare Access assertion.

    Exempt requests (health probes, metrics, CORS preflight ``OPTIONS``) pass
    straight through. Every other request must carry a valid
    ``Cf-Access-Jwt-Assertion`` header or it is rejected with HTTP 403 before
    it reaches any route.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        verifier: CloudflareAccessVerifier,
        exempt_paths: list[str] | None = None,
    ) -> None:
        self.app = app
        self.verifier = verifier
        # Normalize (strip trailing slash) for consistent prefix matching.
        self.exempt = [p.rstrip("/") or "/" for p in (exempt_paths or [])]

    def _is_exempt(self, path: str) -> bool:
        normalized = path.rstrip("/") or "/"
        for exempt in self.exempt:
            if normalized == exempt or path == exempt:
                return True
            # Prefix match so a mounted sub-app (e.g. /metrics) is fully exempt.
            if exempt != "/" and path.startswith(exempt + "/"):
                return True
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")

        # CORS preflight carries no assertion; the browser is redirected to the
        # Access login by Cloudflare before any real request is made.
        if method == "OPTIONS" or self._is_exempt(path):
            await self.app(scope, receive, send)
            return

        token = Headers(scope=scope).get(_ACCESS_JWT_HEADER)
        if not token:
            await self._deny(scope, receive, send, "missing Cloudflare Access assertion")
            return

        try:
            await run_in_threadpool(self.verifier.verify, token)
        except Exception as exc:  # noqa: BLE001 — any failure denies access
            logger.warning("Cloudflare Access verification failed: %s", exc)
            await self._deny(scope, receive, send, "invalid Cloudflare Access assertion")
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _deny(
        scope: Scope, receive: Receive, send: Send, detail: str
    ) -> None:
        response = JSONResponse({"detail": detail}, status_code=403)
        await response(scope, receive, send)


def install_cloudflare_access(app: ASGIApp, config: Any) -> bool:
    """Add the Cloudflare Access middleware to ``app`` when enabled.

    ``config`` is a ``CloudflareAccessConfig``. Returns True when the middleware
    was installed, False when Access verification is disabled. Raises
    ``CloudflareAccessError`` when enabled but misconfigured (fail-fast at
    startup rather than silently accepting unauthenticated traffic).
    """
    if not getattr(config, "enabled", False):
        return False

    verifier = CloudflareAccessVerifier(
        config.team_domain,
        config.audiences,
        jwks_cache_seconds=config.jwks_cache_seconds,
    )
    app.add_middleware(  # type: ignore[attr-defined]
        CloudflareAccessMiddleware,
        verifier=verifier,
        exempt_paths=config.exempt_paths,
    )
    logger.info(
        "Cloudflare Access origin verification enabled (team=%s, audiences=%d, exempt=%s)",
        config.team_domain,
        len(config.audiences),
        ",".join(config.exempt_paths),
    )
    return True
