"""Provider-independent embedding contract for semantic indexing.

This module intentionally has no CocoIndex, model, HTTP, or coordinator imports.
Concrete adapters implement :class:`EmbeddingProvider` lazily at the indexing
boundary while orchestration can validate and fingerprint their contract cheaply.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit, urlunsplit


_ENV_REFERENCE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VAULT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_MAX_PARAMETER_TEXT_LENGTH = 128
_MAX_SAFE_MESSAGE_LENGTH = 512
_INDEXING_PARAMETER_KEYS = frozenset(
    {"input_type", "prompt_name", "truncate", "normalize"}
)
_TRUNCATE_VALUES = frozenset({"start", "end", "none"})


class EmbeddingProviderKind(StrEnum):
    """Supported provider configuration boundaries."""

    LOCAL = "local"
    OPENAI_COMPATIBLE = "openai_compatible"


class CredentialScheme(StrEnum):
    """Credential stores accepted by configuration without accepting raw secrets."""

    ENV = "env"
    VAULT = "vault"


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """A reference to a credential, never the credential value itself."""

    scheme: CredentialScheme
    reference: str = field(repr=False)

    @classmethod
    def parse(cls, value: str) -> CredentialRef:
        if not isinstance(value, str) or ":" not in value:
            raise ValueError("credential reference must use env: or vault:")
        raw_scheme, reference = value.split(":", 1)
        try:
            scheme = CredentialScheme(raw_scheme)
        except ValueError as error:
            raise ValueError("credential reference must use env: or vault:") from error
        if scheme is CredentialScheme.ENV:
            valid = bool(_ENV_REFERENCE_RE.fullmatch(reference))
        else:
            segments = reference.split("/")
            valid = bool(segments) and all(
                segment not in {"", ".", ".."}
                and bool(_VAULT_SEGMENT_RE.fullmatch(segment))
                for segment in segments
            )
        if not valid or len(reference) > 240:
            raise ValueError("credential reference is empty or unsafe")
        return cls(scheme=scheme, reference=reference)

    def __str__(self) -> str:
        return f"{self.scheme.value}:***"

    def __repr__(self) -> str:
        return f"CredentialRef(scheme={self.scheme.value!r}, reference='***')"


IndexingParameterValue = str | bool


def canonicalize_indexing_parameters(
    parameters: Mapping[str, object] | None,
) -> Mapping[str, IndexingParameterValue]:
    """Validate the public whitelist and return an immutable key-sorted mapping."""

    values = {} if parameters is None else dict(parameters)
    unsupported = sorted(set(values) - _INDEXING_PARAMETER_KEYS)
    if unsupported:
        raise ValueError(f"unsupported indexing parameter: {', '.join(unsupported)}")

    canonical: dict[str, IndexingParameterValue] = {}
    for key in sorted(values):
        value = values[key]
        if key == "normalize":
            if not isinstance(value, bool):
                raise ValueError("normalize must be a boolean")
        elif key == "truncate":
            if not isinstance(value, str) or value not in _TRUNCATE_VALUES:
                raise ValueError("truncate must be start, end, or none")
        else:
            if (
                not isinstance(value, str)
                or not value
                or len(value) > _MAX_PARAMETER_TEXT_LENGTH
            ):
                raise ValueError(
                    f"{key} must be a non-empty string no longer than "
                    f"{_MAX_PARAMETER_TEXT_LENGTH} characters"
                )
        canonical[key] = value
    return MappingProxyType(canonical)


@dataclass(frozen=True, slots=True)
class EmbeddingContract:
    """Complete, non-secret contract that determines indexed vector output."""

    provider_kind: EmbeddingProviderKind
    model_id: str
    dimension: int
    indexing_params: Mapping[str, object] = field(default_factory=dict)
    base_url: str | None = None
    credential_ref: CredentialRef | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        try:
            provider_kind = EmbeddingProviderKind(self.provider_kind)
        except ValueError as error:
            raise ValueError(
                f"unsupported provider_kind {self.provider_kind!r}"
            ) from error
        object.__setattr__(self, "provider_kind", provider_kind)

        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be an explicit non-empty string")
        object.__setattr__(self, "model_id", self.model_id.strip())
        if isinstance(self.dimension, bool) or not isinstance(self.dimension, int):
            raise ValueError("dimension must be a positive integer")
        if self.dimension <= 0:
            raise ValueError("dimension must be a positive integer")

        parameters = canonicalize_indexing_parameters(self.indexing_params)
        object.__setattr__(self, "indexing_params", parameters)

        if provider_kind is EmbeddingProviderKind.LOCAL:
            if self.base_url is not None or self.credential_ref is not None:
                raise ValueError(
                    "local embedding contracts cannot contain remote configuration"
                )
            return

        if self.base_url is None:
            raise ValueError("base_url is required for an OpenAI-compatible provider")
        normalized_url = _normalize_safe_base_url(self.base_url)
        object.__setattr__(self, "base_url", normalized_url)
        if not isinstance(self.credential_ref, CredentialRef):
            raise ValueError(
                "credential_ref is required for an OpenAI-compatible provider"
            )

    @property
    def indexing_parameters(self) -> Mapping[str, IndexingParameterValue]:
        return self.indexing_params  # type: ignore[return-value]

    @property
    def canonical_fingerprint_payload(self) -> str:
        """Canonical JSON used for identity; credential references are omitted."""

        payload: dict[str, object] = {
            "schema_version": 1,
            "provider": self.provider_kind.value,
            "model": self.model_id,
            "dimension": self.dimension,
            "indexing_params": dict(self.indexing_parameters),
        }
        if self.base_url is not None:
            payload["base_url"] = self.base_url
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            self.canonical_fingerprint_payload.encode("utf-8")
        ).hexdigest()


def _normalize_safe_base_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("base_url must be a non-empty HTTP(S) URL")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain credentials, query, or fragment")

    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("base_url contains an invalid port") from error
    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


class EmbeddingReadinessState(StrEnum):
    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"


class EmbeddingErrorCode(StrEnum):
    """Sanitized orchestration taxonomy; never carries provider response bodies."""

    MISSING_DEPENDENCY = "missing_dependency"
    MISSING_CREDENTIAL = "missing_credential"
    ENDPOINT_UNAVAILABLE = "endpoint_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_FAILURE = "provider_failure"
    DIMENSION_MISMATCH = "dimension_mismatch"
    INVALID_RESPONSE = "invalid_response"


_NOT_CONFIGURED_CODES = frozenset(
    {
        EmbeddingErrorCode.MISSING_DEPENDENCY,
        EmbeddingErrorCode.MISSING_CREDENTIAL,
        EmbeddingErrorCode.ENDPOINT_UNAVAILABLE,
        EmbeddingErrorCode.MODEL_UNAVAILABLE,
    }
)
_FAILED_CODES = frozenset(
    {
        EmbeddingErrorCode.PROVIDER_FAILURE,
        EmbeddingErrorCode.DIMENSION_MISMATCH,
        EmbeddingErrorCode.INVALID_RESPONSE,
    }
)
_RETRYABLE_CODES = frozenset(
    {
        EmbeddingErrorCode.ENDPOINT_UNAVAILABLE,
        EmbeddingErrorCode.PROVIDER_FAILURE,
    }
)


@dataclass(frozen=True, slots=True)
class EmbeddingReadiness:
    """Provider readiness mapped to durable orchestration dispositions."""

    state: EmbeddingReadinessState
    error_code: EmbeddingErrorCode | None = None
    safe_message: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", EmbeddingReadinessState(self.state))
        if self.error_code is not None:
            object.__setattr__(self, "error_code", EmbeddingErrorCode(self.error_code))
        if self.state is EmbeddingReadinessState.READY:
            if self.error_code is not None or self.safe_message is not None:
                raise ValueError("ready state cannot contain an error")
            return
        if self.error_code is None or not self.safe_message:
            raise ValueError("non-ready state requires an error code and safe message")
        if len(self.safe_message) > _MAX_SAFE_MESSAGE_LENGTH or any(
            ord(char) < 32 for char in self.safe_message
        ):
            raise ValueError("safe message must be bounded and contain no controls")
        if (
            self.state is EmbeddingReadinessState.NOT_CONFIGURED
            and self.error_code not in _NOT_CONFIGURED_CODES
        ):
            raise ValueError("not_configured state requires a configuration error code")
        if (
            self.state is EmbeddingReadinessState.FAILED
            and self.error_code not in _FAILED_CODES
        ):
            raise ValueError("failed state requires a runtime error code")

    @classmethod
    def ready(cls) -> EmbeddingReadiness:
        return cls(EmbeddingReadinessState.READY)

    @classmethod
    def not_configured(
        cls, error_code: EmbeddingErrorCode, safe_message: str
    ) -> EmbeddingReadiness:
        return cls(
            EmbeddingReadinessState.NOT_CONFIGURED,
            error_code,
            safe_message,
        )

    @classmethod
    def failed(
        cls, error_code: EmbeddingErrorCode, safe_message: str
    ) -> EmbeddingReadiness:
        return cls(EmbeddingReadinessState.FAILED, error_code, safe_message)

    @property
    def retryable(self) -> bool:
        return self.error_code in _RETRYABLE_CODES


class EmbeddingProviderError(RuntimeError):
    """Runtime embedding failure with a bounded, persistence-safe taxonomy."""

    def __init__(self, error_code: EmbeddingErrorCode, safe_message: str) -> None:
        readiness = EmbeddingReadiness.failed(error_code, safe_message)
        self.error_code = readiness.error_code
        self.safe_message = readiness.safe_message
        super().__init__(safe_message)

    @property
    def retryable(self) -> bool:
        return self.error_code in _RETRYABLE_CODES


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Light interface consumed by orchestration and the CocoIndex adapter."""

    @property
    def provider_kind(self) -> EmbeddingProviderKind: ...

    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def indexing_parameters(self) -> Mapping[str, IndexingParameterValue]: ...

    @property
    def fingerprint(self) -> str: ...

    async def check_readiness(self) -> EmbeddingReadiness: ...

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...
