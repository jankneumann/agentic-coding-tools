"""Tests for Cloudflare Access origin verification (src/cloudflare_access.py).

Uses a locally generated RSA keypair and an injected ``signing_key_resolver``
so no network / JWKS fetch happens. Tokens are minted with PyJWT exactly as
Cloudflare Access would (RS256, ``aud`` = application AUD tag, ``iss`` = team
domain).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.cloudflare_access import (
    CloudflareAccessError,
    CloudflareAccessMiddleware,
    CloudflareAccessVerifier,
)
from src.config import CloudflareAccessConfig

TEAM_DOMAIN = "https://testteam.cloudflareaccess.com"
AUD = "test-audience-tag-abc123"
JWT_HEADER = "Cf-Access-Jwt-Assertion"


@pytest.fixture(scope="module")
def rsa_keys() -> tuple[rsa.RSAPrivateKey, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(scope="module")
def private_pem(rsa_keys: tuple[rsa.RSAPrivateKey, object]) -> bytes:
    private_key, _ = rsa_keys
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture
def verifier(rsa_keys: tuple[rsa.RSAPrivateKey, object]) -> CloudflareAccessVerifier:
    _, public_key = rsa_keys

    def resolver(_token: str) -> object:
        return public_key

    return CloudflareAccessVerifier(
        TEAM_DOMAIN, [AUD], signing_key_resolver=resolver
    )


def _mint(
    private_pem: bytes,
    *,
    aud: str | list[str] = AUD,
    iss: str = TEAM_DOMAIN,
    expired: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(minutes=5)
    payload = {
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": exp,
        "email": "agent@example.com",
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")


# ── Verifier unit tests ──────────────────────────────────────────────────────


def test_valid_token_verifies(verifier, private_pem):
    claims = verifier.verify(_mint(private_pem))
    assert claims["aud"] == AUD
    assert claims["iss"] == TEAM_DOMAIN


def test_wrong_audience_rejected(verifier, private_pem):
    with pytest.raises(jwt.InvalidAudienceError):
        verifier.verify(_mint(private_pem, aud="some-other-app"))


def test_wrong_issuer_rejected(verifier, private_pem):
    with pytest.raises(jwt.InvalidIssuerError):
        verifier.verify(_mint(private_pem, iss="https://evil.cloudflareaccess.com"))


def test_expired_token_rejected(verifier, private_pem):
    with pytest.raises(jwt.ExpiredSignatureError):
        verifier.verify(_mint(private_pem, expired=True))


def test_wrong_key_rejected(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    token = jwt.encode(
        {
            "aud": AUD,
            "iss": TEAM_DOMAIN,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        other_pem,
        algorithm="RS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        verifier.verify(token)


def test_multiple_audiences_any_match(rsa_keys, private_pem):
    _, public_key = rsa_keys
    verifier = CloudflareAccessVerifier(
        TEAM_DOMAIN, ["app-one", AUD], signing_key_resolver=lambda _t: public_key
    )
    assert verifier.verify(_mint(private_pem))["aud"] == AUD


def test_verifier_requires_team_domain():
    with pytest.raises(CloudflareAccessError):
        CloudflareAccessVerifier("", [AUD])


def test_verifier_requires_audiences():
    with pytest.raises(CloudflareAccessError):
        CloudflareAccessVerifier(TEAM_DOMAIN, [])


# ── Middleware integration tests ─────────────────────────────────────────────


def _app(verifier: CloudflareAccessVerifier) -> TestClient:
    async def protected(_request):
        return PlainTextResponse("ok")

    async def health(_request):
        return PlainTextResponse("healthy")

    app = Starlette(
        routes=[
            Route("/locks/status/x", protected, methods=["GET", "POST"]),
            Route("/health", health),
        ]
    )
    app.add_middleware(
        CloudflareAccessMiddleware,
        verifier=verifier,
        exempt_paths=["/live", "/ready", "/health", "/metrics"],
    )
    # raise_server_exceptions=False so a 500 (should not happen) surfaces as a
    # response rather than bubbling into the test.
    return TestClient(app, raise_server_exceptions=False)


def test_middleware_blocks_missing_token(verifier):
    resp = _app(verifier).get("/locks/status/x")
    assert resp.status_code == 403
    assert "missing" in resp.json()["detail"]


def test_middleware_blocks_invalid_token(verifier):
    resp = _app(verifier).get(
        "/locks/status/x", headers={JWT_HEADER: "not-a-jwt"}
    )
    assert resp.status_code == 403
    assert "invalid" in resp.json()["detail"]


def test_middleware_allows_valid_token(verifier, private_pem):
    resp = _app(verifier).get(
        "/locks/status/x", headers={JWT_HEADER: _mint(private_pem)}
    )
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_middleware_exempts_health(verifier):
    resp = _app(verifier).get("/health")
    assert resp.status_code == 200
    assert resp.text == "healthy"


def test_middleware_allows_options_preflight(verifier):
    # OPTIONS carries no assertion; must not be blocked.
    resp = _app(verifier).options("/locks/status/x")
    assert resp.status_code != 403


# ── Config tests ─────────────────────────────────────────────────────────────


@pytest.fixture
def clean_cf_env(monkeypatch):
    for var in (
        "CF_ACCESS_TEAM_DOMAIN",
        "CF_ACCESS_AUD",
        "CF_ACCESS_ENABLED",
        "CF_ACCESS_EXEMPT_PATHS",
        "CF_ACCESS_JWKS_CACHE_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_config_disabled_by_default(clean_cf_env):
    cfg = CloudflareAccessConfig.from_env()
    assert cfg.enabled is False


def test_config_enabled_when_both_set(clean_cf_env):
    clean_cf_env.setenv("CF_ACCESS_TEAM_DOMAIN", "myteam.cloudflareaccess.com")
    clean_cf_env.setenv("CF_ACCESS_AUD", AUD)
    cfg = CloudflareAccessConfig.from_env()
    assert cfg.enabled is True
    # Bare host normalized to https URL.
    assert cfg.team_domain == "https://myteam.cloudflareaccess.com"
    assert cfg.audiences == [AUD]


def test_config_explicit_disable_wins(clean_cf_env):
    clean_cf_env.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN)
    clean_cf_env.setenv("CF_ACCESS_AUD", AUD)
    clean_cf_env.setenv("CF_ACCESS_ENABLED", "false")
    assert CloudflareAccessConfig.from_env().enabled is False


def test_config_multiple_audiences(clean_cf_env):
    clean_cf_env.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN)
    clean_cf_env.setenv("CF_ACCESS_AUD", "aud-one, aud-two ,aud-three")
    assert CloudflareAccessConfig.from_env().audiences == [
        "aud-one",
        "aud-two",
        "aud-three",
    ]


def test_config_default_exempt_paths(clean_cf_env):
    assert CloudflareAccessConfig.from_env().exempt_paths == [
        "/live",
        "/ready",
        "/health",
        "/metrics",
    ]
