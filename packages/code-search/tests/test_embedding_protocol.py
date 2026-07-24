from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from code_search_pkg.embedding_protocol import (
    CredentialRef,
    EmbeddingContract,
    EmbeddingErrorCode,
    EmbeddingProvider,
    EmbeddingProviderKind,
    EmbeddingReadiness,
    EmbeddingReadinessState,
    canonicalize_indexing_parameters,
)


class FakeProvider:
    def __init__(self, contract: EmbeddingContract) -> None:
        self._contract = contract

    @property
    def provider_kind(self) -> EmbeddingProviderKind:
        return self._contract.provider_kind

    @property
    def model_id(self) -> str:
        return self._contract.model_id

    @property
    def dimension(self) -> int:
        return self._contract.dimension

    @property
    def indexing_parameters(self) -> Mapping[str, str | bool]:
        return self._contract.indexing_parameters

    @property
    def fingerprint(self) -> str:
        return self._contract.fingerprint

    async def check_readiness(self) -> EmbeddingReadiness:
        return EmbeddingReadiness.ready()

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[float(len(text))] * self.dimension for text in texts]


def test_contract_requires_an_explicit_model_and_positive_non_boolean_dimension() -> (
    None
):
    with pytest.raises(ValueError, match="model_id"):
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.LOCAL,
            model_id=" ",
            dimension=768,
        )

    with pytest.raises(ValueError, match="dimension"):
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.LOCAL,
            model_id="sentence-transformers/all-mpnet-base-v2",
            dimension=True,
        )


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"api_key": "secret"}, "unsupported indexing parameter"),
        ({"temperature": 0.0}, "unsupported indexing parameter"),
        ({"truncate": "middle"}, "truncate"),
        ({"normalize": "true"}, "normalize"),
        ({"input_type": "x" * 129}, "input_type"),
    ],
)
def test_indexing_parameters_are_strictly_whitelisted(
    parameters: Mapping[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        canonicalize_indexing_parameters(parameters)


def test_fingerprint_is_canonical_and_excludes_credential_references() -> None:
    first = EmbeddingContract(
        provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
        model_id="text-embedding-3-small",
        dimension=1536,
        base_url="https://gateway.example.test/v1",
        credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
        indexing_params={
            "normalize": True,
            "input_type": "document",
            "truncate": "end",
        },
    )
    second = EmbeddingContract(
        provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
        model_id="text-embedding-3-small",
        dimension=1536,
        base_url="https://gateway.example.test/v1",
        credential_ref=CredentialRef.parse("vault:code-search/alternate-key"),
        indexing_params={
            "truncate": "end",
            "input_type": "document",
            "normalize": True,
        },
    )

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert "CODE_SEARCH_KEY" not in first.canonical_fingerprint_payload
    assert "alternate-key" not in second.canonical_fingerprint_payload


def test_computation_affecting_contract_changes_produce_distinct_fingerprints() -> None:
    baseline = EmbeddingContract(
        provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
        model_id="text-embedding-3-small",
        dimension=1536,
        base_url="https://gateway.example.test/v1",
        credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
        indexing_params={"normalize": True},
    )

    changed = [
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-large",
            dimension=1536,
            base_url="https://gateway.example.test/v1",
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
            indexing_params={"normalize": True},
        ),
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-small",
            dimension=3072,
            base_url="https://gateway.example.test/v1",
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
            indexing_params={"normalize": True},
        ),
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-small",
            dimension=1536,
            base_url="https://other.example.test/v1",
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
            indexing_params={"normalize": True},
        ),
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-small",
            dimension=1536,
            base_url="https://gateway.example.test/v1",
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
            indexing_params={"normalize": False},
        ),
    ]

    assert all(contract.fingerprint != baseline.fingerprint for contract in changed)


def test_credential_reference_has_a_sanitized_string_representation() -> None:
    credential = CredentialRef.parse("vault:teams/search/gateway-key")

    assert credential.reference == "teams/search/gateway-key"
    assert str(credential) == "vault:***"
    assert "gateway-key" not in repr(credential)


@pytest.mark.parametrize(
    "value",
    [
        "literal-secret",
        "env:",
        "env:WITH SPACE",
        "file:/tmp/key",
        "vault:../../escape",
    ],
)
def test_credential_reference_rejects_unscoped_or_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="credential"):
        CredentialRef.parse(value)


def test_openai_compatible_contract_requires_safe_explicit_endpoint_and_reference() -> (
    None
):
    with pytest.raises(ValueError, match="base_url"):
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-small",
            dimension=1536,
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
        )

    with pytest.raises(ValueError, match="credential_ref"):
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-small",
            dimension=1536,
            base_url="https://gateway.example.test/v1",
        )

    with pytest.raises(ValueError, match="credentials, query, or fragment"):
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
            model_id="text-embedding-3-small",
            dimension=1536,
            base_url="https://user:secret@gateway.example.test/v1?key=secret",
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
        )


def test_local_contract_rejects_remote_configuration() -> None:
    with pytest.raises(ValueError, match="local"):
        EmbeddingContract(
            provider_kind=EmbeddingProviderKind.LOCAL,
            model_id="sentence-transformers/all-mpnet-base-v2",
            dimension=768,
            base_url="https://gateway.example.test/v1",
            credential_ref=CredentialRef.parse("env:CODE_SEARCH_KEY"),
        )


def test_readiness_taxonomy_distinguishes_configuration_from_runtime_failure() -> None:
    missing_credential = EmbeddingReadiness.not_configured(
        EmbeddingErrorCode.MISSING_CREDENTIAL,
        "configured credential reference is unavailable",
    )
    provider_failure = EmbeddingReadiness.failed(
        EmbeddingErrorCode.PROVIDER_FAILURE,
        "provider readiness request failed",
    )

    assert missing_credential.state is EmbeddingReadinessState.NOT_CONFIGURED
    assert missing_credential.retryable is False
    assert provider_failure.state is EmbeddingReadinessState.FAILED
    assert provider_failure.retryable is True


def test_readiness_taxonomy_rejects_mismatched_states_and_error_codes() -> None:
    with pytest.raises(ValueError, match="configuration error code"):
        EmbeddingReadiness.not_configured(
            EmbeddingErrorCode.PROVIDER_FAILURE,
            "wrong disposition",
        )

    with pytest.raises(ValueError, match="runtime error code"):
        EmbeddingReadiness.failed(
            EmbeddingErrorCode.MISSING_DEPENDENCY,
            "wrong disposition",
        )


@pytest.mark.asyncio
async def test_provider_protocol_exposes_the_light_frozen_boundary() -> None:
    contract = EmbeddingContract(
        provider_kind=EmbeddingProviderKind.LOCAL,
        model_id="sentence-transformers/all-mpnet-base-v2",
        dimension=3,
        indexing_params={"normalize": True},
    )
    provider = FakeProvider(contract)

    assert isinstance(provider, EmbeddingProvider)
    assert (await provider.check_readiness()).state is EmbeddingReadinessState.READY
    assert await provider.embed(["a", "ab"]) == [
        [1.0, 1.0, 1.0],
        [2.0, 2.0, 2.0],
    ]
