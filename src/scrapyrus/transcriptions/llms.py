from __future__ import annotations

import math
from typing import Any, ClassVar

import requests


LLM_REQUEST_TIMEOUT = 60


class LLMProviderBase:
    """Base class for inference-server provider implementations.

    Subclasses are registered in definition order. Their ``initialize``
    methods form a chain of responsibility for inference server URLs.
    """

    _providers: ClassVar[list[type[LLMProviderBase]]] = []

    def __init_subclass__(
        cls,
        *,
        register: bool = True,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if register:
            LLMProviderBase._providers.append(cls)

    @classmethod
    def registered_providers(cls) -> tuple[type[LLMProviderBase], ...]:
        """Return provider classes in responsibility-chain order."""

        return tuple(cls._providers)

    @classmethod
    def initialize(
        cls, inference_server_url: str, modelname: str, api_key: str
    ) -> LLMProviderBase | None:
        """Return a provider instance if *cls* handles the server URL."""

        raise NotImplementedError

    def token_count(self, text: str) -> int:
        """Return the number of model tokens required by *text*."""

        raise NotImplementedError

    def context_length(self) -> int:
        """Return the model's available context size in tokens."""

        raise NotImplementedError

    def embedding_length(self) -> int:
        """Return the number of values in an embedding."""

        raise NotImplementedError

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the embedding for *text*."""

        raise NotImplementedError


def initialize_llm_provider(
    inference_server_url: str, modelname: str, api_key: str
) -> LLMProviderBase:
    """Initialize the first registered provider responsible for a server."""

    for provider_type in LLMProviderBase.registered_providers():
        provider = provider_type.initialize(inference_server_url, modelname, api_key)
        if provider is not None:
            return provider
    raise ValueError(
        f"No registered LLM provider handles inference server {inference_server_url!r}"
    )


class VLLMProvider(LLMProviderBase):
    """Provider for a vLLM OpenAI-compatible inference server."""

    def __init__(self, inference_server_url: str, modelname: str, api_key: str) -> None:
        self.inference_server_url = _vllm_base_url(inference_server_url)
        self.modelname = modelname
        self.api_key = api_key
        self._context_length: int | None = None
        self._embedding_length: int | None = None

    @classmethod
    def initialize(
        cls, inference_server_url: str, modelname: str, api_key: str
    ) -> VLLMProvider | None:
        """Detect vLLM through its version endpoint."""

        provider = cls(inference_server_url, modelname, api_key)
        try:
            with provider._session() as client:
                response = client.get(
                    f"{provider.inference_server_url}/version",
                    timeout=LLM_REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
        except (requests.RequestException, ValueError):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
            return None
        return provider

    def token_count(self, text: str) -> int:
        count, _ = self._tokenize(text)
        return count

    def context_length(self) -> int:
        if self._context_length is None:
            self._tokenize("")
        assert self._context_length is not None
        return self._context_length

    def embedding_length(self) -> int:
        if self._embedding_length is None:
            self.embed("test")
        assert self._embedding_length is not None
        return self._embedding_length

    def embed(self, text: str) -> tuple[float, ...]:
        payload = self._post_json(
            "/v1/embeddings", {"model": self.modelname, "input": text}
        )
        try:
            embedding = payload["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                "Embedding response did not contain data[0].embedding"
            ) from error
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("Embedding response did not contain a non-empty vector")
        vector = tuple(float(value) for value in embedding)
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding response contained non-finite vector values")
        if self._embedding_length is not None and self._embedding_length != len(vector):
            raise ValueError("Embedding response changed vector length")
        self._embedding_length = len(vector)
        return vector

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        return session

    def _tokenize(self, text: str) -> tuple[int, int]:
        payload = self._post_json(
            "/tokenize", {"model": self.modelname, "prompt": text}
        )
        count = payload.get("count")
        context_length = payload.get("max_model_len")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or not isinstance(context_length, int)
            or isinstance(context_length, bool)
            or context_length < 1
        ):
            raise ValueError(
                "Tokenize response did not contain valid count and max_model_len"
            )
        self._context_length = context_length
        return count, context_length

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        with self._session() as client:
            response = client.post(
                f"{self.inference_server_url}{path}",
                json=body,
                timeout=LLM_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Inference server response was not a JSON object")
        return payload


def _vllm_base_url(inference_server_url: str) -> str:
    base_url = inference_server_url.rstrip("/")
    return base_url[:-3] if base_url.endswith("/v1") else base_url
