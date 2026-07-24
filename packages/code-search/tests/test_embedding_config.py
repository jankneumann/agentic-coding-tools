from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from code_search_pkg.embedding_config import (
    CocoIndexSingleTextEmbedder,
    LocalEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    ProviderAdapterFailure,
    build_embedding_provider,
)
from code_search_pkg.embedding_protocol import (
    CredentialRef,
    EmbeddingContract,
    EmbeddingErrorCode,
    EmbeddingProviderError,
    EmbeddingProviderKind,
    EmbeddingReadinessState,
)


def local_contract(*, dimension: int = 3) -> EmbeddingContract:
    return EmbeddingContract(
        provider_kind=EmbeddingProviderKind.LOCAL,
        model_id="sentence-transformers/example",
        dimension=dimension,
        indexing_params={"normalize": True},
    )


def remote_contract(*, dimension: int = 3) -> EmbeddingContract:
    return EmbeddingContract(
        provider_kind=EmbeddingProviderKind.OPENAI_COMPATIBLE,
        model_id="embedding-model",
        dimension=dimension,
        base_url="https://gateway.example.test/v1",
        credential_ref=CredentialRef.parse("env:CODE_SEARCH_API_KEY"),
        indexing_params={"input_type": "document"},
    )


class FakeLocalModel:
    def __init__(
        self,
        *,
        dimension: int = 3,
        vectors: Sequence[Sequence[float]] | None = None,
    ) -> None:
        self.dimension = dimension
        self.vectors = vectors
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension

    def encode(
        self, texts: Sequence[str], **parameters: object
    ) -> Sequence[Sequence[float]]:
        text_list = list(texts)
        self.calls.append((text_list, dict(parameters)))
        return self.vectors or [
            [float(len(text))] * self.dimension for text in text_list
        ]


class FakeRemoteTransport:
    def __init__(
        self,
        result: object = ((1.0, 2.0, 3.0),),
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def embed(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        texts: Sequence[str],
        dimension: int,
        indexing_parameters: Mapping[str, object],
    ) -> object:
        self.calls.append(
            {
                "base_url": base_url,
                "api_key": api_key,
                "model_id": model_id,
                "texts": list(texts),
                "dimension": dimension,
                "indexing_parameters": dict(indexing_parameters),
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


class ArrayLikeVectors:
    """Small stand-in for the ndarray returned by sentence-transformers."""

    def tolist(self) -> list[list[float]]:
        return [[1.0, 2.0, 3.0]]


def test_local_provider_is_lazy_until_readiness_or_embedding() -> None:
    calls: list[str] = []
    model = FakeLocalModel()

    def load(model_id: str) -> FakeLocalModel:
        calls.append(model_id)
        return model

    provider = build_embedding_provider(local_contract(), local_model_loader=load)

    assert isinstance(provider, LocalEmbeddingProvider)
    assert calls == []


@pytest.mark.asyncio
async def test_local_readiness_loads_once_and_validates_declared_dimension() -> None:
    calls: list[str] = []
    model = FakeLocalModel()

    def load(model_id: str) -> FakeLocalModel:
        calls.append(model_id)
        return model

    provider = LocalEmbeddingProvider(local_contract(), model_loader=load)

    assert (await provider.check_readiness()).state is EmbeddingReadinessState.READY
    assert (await provider.check_readiness()).state is EmbeddingReadinessState.READY
    assert calls == ["sentence-transformers/example"]


@pytest.mark.asyncio
async def test_local_missing_dependency_and_dimension_mismatch_use_protocol_taxonomy() -> (
    None
):
    def missing(_model_id: str) -> object:
        raise ImportError("sentence_transformers and a secret-looking path")

    unavailable = LocalEmbeddingProvider(local_contract(), model_loader=missing)
    missing_result = await unavailable.check_readiness()

    assert missing_result.state is EmbeddingReadinessState.NOT_CONFIGURED
    assert missing_result.error_code is EmbeddingErrorCode.MISSING_DEPENDENCY
    assert "secret-looking" not in (missing_result.safe_message or "")

    mismatch = LocalEmbeddingProvider(
        local_contract(), model_loader=lambda _model_id: FakeLocalModel(dimension=4)
    )
    mismatch_result = await mismatch.check_readiness()

    assert mismatch_result.state is EmbeddingReadinessState.FAILED
    assert mismatch_result.error_code is EmbeddingErrorCode.DIMENSION_MISMATCH


@pytest.mark.asyncio
async def test_local_embedding_maps_parameters_and_validates_every_vector() -> None:
    model = FakeLocalModel(vectors=((1.0, 2.0, 3.0), (4.0, 5.0)))
    provider = LocalEmbeddingProvider(
        local_contract(), model_loader=lambda _model_id: model
    )

    with pytest.raises(EmbeddingProviderError) as raised:
        await provider.embed(["one", "two"])

    assert raised.value.error_code is EmbeddingErrorCode.DIMENSION_MISMATCH
    assert model.calls == [
        (["one", "two"], {"normalize_embeddings": True}),
    ]


@pytest.mark.asyncio
async def test_local_embedding_accepts_sentence_transformer_array_output() -> None:
    model = FakeLocalModel()
    model.vectors = ArrayLikeVectors()  # type: ignore[assignment]
    provider = LocalEmbeddingProvider(
        local_contract(), model_loader=lambda _model_id: model
    )

    assert await provider.embed(["one"]) == [[1.0, 2.0, 3.0]]


def test_remote_provider_is_lazy_and_does_not_resolve_credentials_at_build_time() -> (
    None
):
    environment: dict[str, str] = {}
    transport = FakeRemoteTransport()

    provider = build_embedding_provider(
        remote_contract(),
        environment=environment,
        remote_transport=transport,
    )

    assert isinstance(provider, OpenAICompatibleEmbeddingProvider)
    assert transport.calls == []
    environment["CODE_SEARCH_API_KEY"] = "late-bound-secret"


@pytest.mark.asyncio
async def test_missing_remote_credential_is_not_configured_without_network() -> None:
    transport = FakeRemoteTransport()
    provider = OpenAICompatibleEmbeddingProvider(
        remote_contract(),
        environment={},
        transport=transport,
    )

    readiness = await provider.check_readiness()

    assert readiness.state is EmbeddingReadinessState.NOT_CONFIGURED
    assert readiness.error_code is EmbeddingErrorCode.MISSING_CREDENTIAL
    assert transport.calls == []


@pytest.mark.asyncio
async def test_env_credential_is_resolved_transiently_and_never_exposed() -> None:
    secret = "do-not-persist-this-key"
    transport = FakeRemoteTransport()
    provider = OpenAICompatibleEmbeddingProvider(
        remote_contract(),
        environment={"CODE_SEARCH_API_KEY": secret},
        transport=transport,
    )

    assert (await provider.check_readiness()).state is EmbeddingReadinessState.READY

    assert transport.calls[0]["api_key"] == secret
    assert secret not in repr(provider)
    assert secret not in provider.fingerprint
    assert secret not in provider._contract.canonical_fingerprint_payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_state", "expected_code"),
    [
        (
            ProviderAdapterFailure(EmbeddingErrorCode.ENDPOINT_UNAVAILABLE),
            EmbeddingReadinessState.NOT_CONFIGURED,
            EmbeddingErrorCode.ENDPOINT_UNAVAILABLE,
        ),
        (
            ProviderAdapterFailure(EmbeddingErrorCode.MODEL_UNAVAILABLE),
            EmbeddingReadinessState.NOT_CONFIGURED,
            EmbeddingErrorCode.MODEL_UNAVAILABLE,
        ),
        (
            ProviderAdapterFailure(EmbeddingErrorCode.PROVIDER_FAILURE),
            EmbeddingReadinessState.FAILED,
            EmbeddingErrorCode.PROVIDER_FAILURE,
        ),
    ],
)
async def test_remote_readiness_maps_sanitized_transport_errors(
    error: Exception,
    expected_state: EmbeddingReadinessState,
    expected_code: EmbeddingErrorCode,
) -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        remote_contract(),
        environment={"CODE_SEARCH_API_KEY": "secret"},
        transport=FakeRemoteTransport(error=error),
    )

    readiness = await provider.check_readiness()

    assert readiness.state is expected_state
    assert readiness.error_code is expected_code
    assert "secret" not in (readiness.safe_message or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        ({"data": "not-a-vector-list"}, EmbeddingErrorCode.INVALID_RESPONSE),
        (((1.0, 2.0),), EmbeddingErrorCode.DIMENSION_MISMATCH),
        (((1.0, float("nan"), 3.0),), EmbeddingErrorCode.INVALID_RESPONSE),
        (((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)), EmbeddingErrorCode.INVALID_RESPONSE),
    ],
)
async def test_remote_embedding_validates_shape_count_dimension_and_finiteness(
    response: object,
    expected_code: EmbeddingErrorCode,
) -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        remote_contract(),
        environment={"CODE_SEARCH_API_KEY": "secret"},
        transport=FakeRemoteTransport(result=response),
    )

    with pytest.raises(EmbeddingProviderError) as raised:
        await provider.embed(["only-one"])

    assert raised.value.error_code is expected_code


@pytest.mark.asyncio
async def test_cocoindex_adapter_embeds_one_text_without_changing_frozen_parameters() -> (
    None
):
    model = FakeLocalModel()
    provider = LocalEmbeddingProvider(
        local_contract(), model_loader=lambda _model_id: model
    )
    adapter = CocoIndexSingleTextEmbedder(provider)

    vector = await adapter.embed("hello", normalize=True)

    assert vector.tolist() == [5.0, 5.0, 5.0]
    assert str(vector.dtype) == "float32"
    with pytest.raises(ValueError, match="frozen indexing contract"):
        await adapter.embed("hello", normalize=False)


@pytest.mark.asyncio
async def test_cocoindex_adapter_provides_stable_memo_and_vector_schema() -> None:
    first = CocoIndexSingleTextEmbedder(
        LocalEmbeddingProvider(
            local_contract(),
            model_loader=lambda _model_id: FakeLocalModel(),
        )
    )
    equivalent = CocoIndexSingleTextEmbedder(
        LocalEmbeddingProvider(
            local_contract(),
            model_loader=lambda _model_id: FakeLocalModel(),
        )
    )
    changed = CocoIndexSingleTextEmbedder(
        LocalEmbeddingProvider(
            local_contract(dimension=4),
            model_loader=lambda _model_id: FakeLocalModel(dimension=4),
        )
    )

    assert first.__coco_memo_key__() == equivalent.__coco_memo_key__()
    assert first.__coco_memo_key__() != changed.__coco_memo_key__()
    schema = await first.__coco_vector_schema__()
    assert schema.size == 3
    assert str(schema.dtype) == "float32"


def test_provider_configuration_imports_no_coordinator_control_plane() -> None:
    import code_search_pkg.embedding_config as module

    source_names = set(module.__dict__)
    assert not any("coordinator" in name.lower() for name in source_names)
