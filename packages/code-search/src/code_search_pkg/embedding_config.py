# pyright: reportMissingImports=false
"""Lazy, explicit embedding-provider configuration.

The provider contract is constructed before this module is called. In
particular, callers must supply a model and vector dimension; this module does
not guess either value, download a default model, or select a remote endpoint.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NoReturn, Protocol, TypeGuard

from .embedding_protocol import (
    CredentialRef,
    CredentialScheme,
    EmbeddingContract,
    EmbeddingErrorCode,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderKind,
    EmbeddingReadiness,
    IndexingParameterValue,
)

_SAFE_MESSAGES = {
    EmbeddingErrorCode.MISSING_DEPENDENCY: "embedding provider dependency is unavailable",
    EmbeddingErrorCode.MISSING_CREDENTIAL: "embedding provider credential is unavailable",
    EmbeddingErrorCode.ENDPOINT_UNAVAILABLE: "embedding provider endpoint is unavailable",
    EmbeddingErrorCode.MODEL_UNAVAILABLE: "configured embedding model is unavailable",
    EmbeddingErrorCode.PROVIDER_FAILURE: "embedding provider request failed",
    EmbeddingErrorCode.DIMENSION_MISMATCH: "embedding response dimension does not match the contract",
    EmbeddingErrorCode.INVALID_RESPONSE: "embedding provider returned an invalid response",
}
_NOT_CONFIGURED_CODES = frozenset(
    {
        EmbeddingErrorCode.MISSING_DEPENDENCY,
        EmbeddingErrorCode.MISSING_CREDENTIAL,
        EmbeddingErrorCode.ENDPOINT_UNAVAILABLE,
        EmbeddingErrorCode.MODEL_UNAVAILABLE,
    }
)


class ProviderAdapterFailure(RuntimeError):
    """Sanitized provider/configuration failure used at adapter boundaries."""

    def __init__(self, error_code: EmbeddingErrorCode) -> None:
        self.error_code = EmbeddingErrorCode(error_code)
        self.safe_message = _SAFE_MESSAGES[self.error_code]
        super().__init__(self.safe_message)


class LocalModel(Protocol):
    def get_sentence_embedding_dimension(self) -> int | None: ...

    def encode(
        self, texts: Sequence[str], **parameters: object
    ) -> Sequence[Sequence[float]]: ...


class OpenAIEmbeddingTransport(Protocol):
    async def embed(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        texts: Sequence[str],
        dimension: int,
        indexing_parameters: Mapping[str, object],
    ) -> object: ...


CredentialResolver = Callable[[CredentialRef], str | None]
LocalModelLoader = Callable[[str], LocalModel]


class _ConfiguredProvider:
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
    def indexing_parameters(self) -> Mapping[str, IndexingParameterValue]:
        return self._contract.indexing_parameters

    @property
    def fingerprint(self) -> str:
        return self._contract.fingerprint


class LocalEmbeddingProvider(_ConfiguredProvider):
    """Lazy sentence-transformers adapter for an explicit local contract."""

    def __init__(
        self,
        contract: EmbeddingContract,
        *,
        model_loader: LocalModelLoader | None = None,
    ) -> None:
        if contract.provider_kind is not EmbeddingProviderKind.LOCAL:
            raise ValueError("local provider requires a local embedding contract")
        super().__init__(contract)
        self._model_loader = model_loader or _load_sentence_transformer
        self._model: LocalModel | None = None
        self._load_lock = asyncio.Lock()

    def __repr__(self) -> str:
        return (
            f"LocalEmbeddingProvider(model_id={self.model_id!r}, "
            f"dimension={self.dimension})"
        )

    async def _get_model(self) -> LocalModel:
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._model_loader, self.model_id)
        return self._model

    async def _validate_model(self) -> LocalModel:
        model = await self._get_model()
        get_dimension = getattr(model, "get_sentence_embedding_dimension", None)
        if callable(get_dimension):
            actual_dimension = get_dimension()
            if actual_dimension is not None and actual_dimension != self.dimension:
                raise ProviderAdapterFailure(EmbeddingErrorCode.DIMENSION_MISMATCH)
        return model

    async def check_readiness(self) -> EmbeddingReadiness:
        try:
            await self._validate_model()
        except Exception as error:
            return _readiness_for_error(_classify_local_error(error))
        return EmbeddingReadiness.ready()

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        text_list = _validate_texts(texts)
        try:
            model = await self._validate_model()
            parameters = _local_encode_parameters(self.indexing_parameters)
            response = await asyncio.to_thread(model.encode, text_list, **parameters)
            return _validate_vectors(response, len(text_list), self.dimension)
        except ProviderAdapterFailure as error:
            _raise_embedding_error(error)
        except Exception as error:
            _raise_embedding_error(_classify_local_error(error))


class OpenAICompatibleEmbeddingProvider(_ConfiguredProvider):
    """Lazy data-plane adapter for any explicit OpenAI-compatible endpoint."""

    def __init__(
        self,
        contract: EmbeddingContract,
        *,
        environment: Mapping[str, str] | None = None,
        credential_resolver: CredentialResolver | None = None,
        transport: OpenAIEmbeddingTransport | None = None,
    ) -> None:
        if contract.provider_kind is not EmbeddingProviderKind.OPENAI_COMPATIBLE:
            raise ValueError(
                "OpenAI-compatible provider requires a remote embedding contract"
            )
        super().__init__(contract)
        self._environment = os.environ if environment is None else environment
        self._credential_resolver = credential_resolver
        self._transport = transport or UrllibOpenAIEmbeddingTransport()

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleEmbeddingProvider("
            f"model_id={self.model_id!r}, dimension={self.dimension}, "
            f"base_url={self._contract.base_url!r})"
        )

    def _resolve_api_key(self) -> str:
        reference = self._contract.credential_ref
        if reference is None:
            raise ProviderAdapterFailure(EmbeddingErrorCode.MISSING_CREDENTIAL)
        if reference.scheme is CredentialScheme.ENV:
            credential = self._environment.get(reference.reference)
        elif self._credential_resolver is not None:
            credential = self._credential_resolver(reference)
        else:
            credential = None
        if not isinstance(credential, str) or not credential:
            raise ProviderAdapterFailure(EmbeddingErrorCode.MISSING_CREDENTIAL)
        return credential

    async def _perform(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        api_key = self._resolve_api_key()
        try:
            response = await self._transport.embed(
                base_url=self._contract.base_url or "",
                api_key=api_key,
                model_id=self.model_id,
                texts=texts,
                dimension=self.dimension,
                indexing_parameters=self.indexing_parameters,
            )
        except ProviderAdapterFailure:
            raise
        except (ConnectionError, TimeoutError, OSError) as error:
            raise ProviderAdapterFailure(
                EmbeddingErrorCode.ENDPOINT_UNAVAILABLE
            ) from error
        except Exception as error:
            raise ProviderAdapterFailure(EmbeddingErrorCode.PROVIDER_FAILURE) from error
        return _validate_vectors(response, len(texts), self.dimension)

    async def check_readiness(self) -> EmbeddingReadiness:
        try:
            await self._perform(["code-search readiness probe"])
        except ProviderAdapterFailure as error:
            return _readiness_for_error(error)
        except EmbeddingProviderError as error:
            return EmbeddingReadiness.failed(
                error.error_code or EmbeddingErrorCode.PROVIDER_FAILURE,
                error.safe_message
                or _SAFE_MESSAGES[EmbeddingErrorCode.PROVIDER_FAILURE],
            )
        return EmbeddingReadiness.ready()

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        text_list = _validate_texts(texts)
        try:
            return await self._perform(text_list)
        except ProviderAdapterFailure as error:
            _raise_embedding_error(error)


class CocoIndexSingleTextEmbedder:
    """Expose the batch protocol through CocoIndex's single-text call shape."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def __coco_memo_key__(self) -> object:
        """Return the complete, stable identity of embedding computation."""

        return (
            "code-search-single-text-embedder-v1",
            self._provider.fingerprint,
            self._provider.dimension,
            tuple(sorted(self._provider.indexing_parameters.items())),
        )

    async def __coco_vector_schema__(self) -> Any:
        """Provide CocoIndex's pinned public vector-schema protocol."""

        import numpy as np
        from cocoindex.resources.schema import VectorSchema

        return VectorSchema(
            dtype=np.dtype(np.float32),
            size=self._provider.dimension,
        )

    async def embed(self, text: str, **parameters: object) -> Any:
        if parameters != dict(self._provider.indexing_parameters):
            raise ValueError(
                "embedding parameters differ from the frozen indexing contract"
            )
        vectors = await self._provider.embed([text])
        if len(vectors) != 1:
            raise EmbeddingProviderError(
                EmbeddingErrorCode.INVALID_RESPONSE,
                _SAFE_MESSAGES[EmbeddingErrorCode.INVALID_RESPONSE],
            )
        import numpy as np

        return np.asarray(vectors[0], dtype=np.float32)


def build_embedding_provider(
    contract: EmbeddingContract,
    *,
    environment: Mapping[str, str] | None = None,
    credential_resolver: CredentialResolver | None = None,
    local_model_loader: LocalModelLoader | None = None,
    remote_transport: OpenAIEmbeddingTransport | None = None,
) -> EmbeddingProvider:
    """Construct a lazy provider from a complete, explicit contract."""

    if contract.provider_kind is EmbeddingProviderKind.LOCAL:
        return LocalEmbeddingProvider(contract, model_loader=local_model_loader)
    return OpenAICompatibleEmbeddingProvider(
        contract,
        environment=environment,
        credential_resolver=credential_resolver,
        transport=remote_transport,
    )


class UrllibOpenAIEmbeddingTransport:
    """Dependency-light OpenAI embeddings transport, invoked only on demand."""

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
        payload: dict[str, object] = {
            "model": model_id,
            "input": list(texts),
            "dimensions": dimension,
            **indexing_parameters,
        }
        return await asyncio.to_thread(
            self._request,
            f"{base_url.rstrip('/')}/embeddings",
            api_key,
            payload,
        )

    @staticmethod
    def _request(url: str, api_key: str, payload: Mapping[str, object]) -> object:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in {401, 403}:
                code = EmbeddingErrorCode.MISSING_CREDENTIAL
            elif error.code == 404:
                code = EmbeddingErrorCode.MODEL_UNAVAILABLE
            elif error.code in {408, 502, 503, 504}:
                code = EmbeddingErrorCode.ENDPOINT_UNAVAILABLE
            else:
                code = EmbeddingErrorCode.PROVIDER_FAILURE
            raise ProviderAdapterFailure(code) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProviderAdapterFailure(
                EmbeddingErrorCode.ENDPOINT_UNAVAILABLE
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE) from error


def _load_sentence_transformer(model_id: str) -> LocalModel:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise ProviderAdapterFailure(EmbeddingErrorCode.MISSING_DEPENDENCY) from error
    try:
        return SentenceTransformer(model_id)  # type: ignore[no-any-return]
    except (FileNotFoundError, OSError) as error:
        raise ProviderAdapterFailure(EmbeddingErrorCode.MODEL_UNAVAILABLE) from error


def _local_encode_parameters(
    parameters: Mapping[str, IndexingParameterValue],
) -> dict[str, object]:
    values: dict[str, object] = {key: value for key, value in parameters.items()}
    if "normalize" in values:
        values["normalize_embeddings"] = values.pop("normalize")
    return values


def _validate_texts(texts: Sequence[str]) -> list[str]:
    if isinstance(texts, (str, bytes)):
        raise ValueError("texts must be a sequence of strings")
    values = list(texts)
    if not values or any(not isinstance(text, str) for text in values):
        raise ValueError("texts must be a non-empty sequence of strings")
    return values


def _validate_vectors(
    response: object,
    expected_count: int,
    dimension: int,
) -> list[list[float]]:
    raw_vectors: object = response
    to_list = getattr(response, "tolist", None)
    if callable(to_list):
        try:
            raw_vectors = to_list()
        except Exception as error:
            raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE) from error
    if isinstance(response, Mapping):
        data = response.get("data")
        if not _is_non_text_sequence(data):
            raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
        indexed: list[tuple[int, object]] = []
        for fallback_index, item in enumerate(data):
            if not isinstance(item, Mapping) or "embedding" not in item:
                raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
            index = item.get("index", fallback_index)
            if isinstance(index, bool) or not isinstance(index, int):
                raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
            indexed.append((index, item["embedding"]))
        if len({index for index, _vector in indexed}) != len(indexed):
            raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
        raw_vectors = [vector for _index, vector in sorted(indexed)]

    if not _is_non_text_sequence(raw_vectors):
        raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
    if len(raw_vectors) != expected_count:
        raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)

    vectors: list[list[float]] = []
    for raw_vector in raw_vectors:
        if not _is_non_text_sequence(raw_vector):
            raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
        if len(raw_vector) != dimension:
            raise ProviderAdapterFailure(EmbeddingErrorCode.DIMENSION_MISMATCH)
        vector: list[float] = []
        for value in raw_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
            number = float(value)
            if not math.isfinite(number):
                raise ProviderAdapterFailure(EmbeddingErrorCode.INVALID_RESPONSE)
            vector.append(number)
        vectors.append(vector)
    return vectors


def _is_non_text_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _classify_local_error(error: Exception) -> ProviderAdapterFailure:
    if isinstance(error, ProviderAdapterFailure):
        return error
    if isinstance(error, ImportError):
        code = EmbeddingErrorCode.MISSING_DEPENDENCY
    elif isinstance(error, (FileNotFoundError, OSError)):
        code = EmbeddingErrorCode.MODEL_UNAVAILABLE
    else:
        code = EmbeddingErrorCode.PROVIDER_FAILURE
    return ProviderAdapterFailure(code)


def _readiness_for_error(error: ProviderAdapterFailure) -> EmbeddingReadiness:
    if error.error_code in _NOT_CONFIGURED_CODES:
        return EmbeddingReadiness.not_configured(error.error_code, error.safe_message)
    return EmbeddingReadiness.failed(error.error_code, error.safe_message)


def _raise_embedding_error(error: ProviderAdapterFailure) -> NoReturn:
    if error.error_code in _NOT_CONFIGURED_CODES:
        raise error
    raise EmbeddingProviderError(error.error_code, error.safe_message) from error
