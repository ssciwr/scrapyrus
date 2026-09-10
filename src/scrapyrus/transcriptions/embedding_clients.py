"""Allowlisted LangChain embedding clients shared by ingestion and querying."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from itertools import batched
import logging
import time
from typing import Any, TypeVar, cast
from urllib.parse import urlparse

from langchain_core.embeddings import Embeddings


SUPPORTED_EMBEDDING_PROVIDERS = frozenset(
    {"openai", "vllm", "voyageai", "mistralai", "huggingface"}
)
VOYAGEAI_EMBEDDING_BATCH_SIZE = 64
VOYAGEAI_RATE_LIMIT_MAX_RETRIES = 7
VOYAGEAI_RATE_LIMIT_MAX_DELAY_SECONDS = 16


logger = logging.getLogger(__name__)


_BatchItem = TypeVar("_BatchItem")
_EmbeddingResult = TypeVar("_EmbeddingResult")


def embedding_request_batches(
    items: Iterable[_BatchItem], provider: str
) -> Iterator[tuple[_BatchItem, ...]]:
    """Group VoyageAI inputs into regular requests, preserving other behavior."""

    batch_size = VOYAGEAI_EMBEDDING_BATCH_SIZE if provider == "voyageai" else 1
    return batched(items, batch_size)


def embed_documents_with_backoff(
    client: Embeddings, texts: list[str], provider: str
) -> list[list[float]]:
    """Embed documents, retrying VoyageAI rate limits with exponential backoff."""

    return _call_with_rate_limit_backoff(
        lambda: client.embed_documents(texts), provider
    )


def embed_query_with_backoff(
    client: Embeddings, text: str, provider: str
) -> list[float]:
    """Embed a query, retrying VoyageAI rate limits with exponential backoff."""

    return _call_with_rate_limit_backoff(lambda: client.embed_query(text), provider)


def _call_with_rate_limit_backoff(
    operation: Callable[[], _EmbeddingResult], provider: str
) -> _EmbeddingResult:
    if provider != "voyageai":
        return operation()

    from voyageai.error import RateLimitError

    retries = 0
    while True:
        try:
            return operation()
        except RateLimitError:
            if retries >= VOYAGEAI_RATE_LIMIT_MAX_RETRIES:
                raise
            delay = min(2**retries, VOYAGEAI_RATE_LIMIT_MAX_DELAY_SECONDS)
            retries += 1
            logger.warning(
                "VoyageAI rate limit reached; retrying in %d seconds (%d/%d)",
                delay,
                retries,
                VOYAGEAI_RATE_LIMIT_MAX_RETRIES,
            )
            time.sleep(delay)


def infer_embedding_provider(inference_server_url: str) -> str:
    """Infer a hosted provider, treating other endpoints as explicit vLLM."""

    hostname = (urlparse(inference_server_url).hostname or "").rstrip(".").lower()
    return {
        "api.openai.com": "openai",
        "api.voyageai.com": "voyageai",
        "api.mistral.ai": "mistralai",
    }.get(hostname, "vllm")


def effective_provider_options(
    provider: str, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Validate and fill compatibility-affecting provider defaults."""

    supplied = dict(options or {})
    allowed = {
        "openai": {"dimensions", "check_embedding_ctx_length"},
        "vllm": {"dimensions", "check_embedding_ctx_length"},
        "voyageai": {
            "output_dimension",
            "truncation",
            "batch_size",
            "document_input_type",
            "query_input_type",
        },
        "mistralai": set(),
        "huggingface": {
            "model_revision",
            "normalize_embeddings",
            "truncate_dim",
            "document_prompt_name",
            "query_prompt_name",
        },
    }
    if provider not in allowed:
        raise ValueError(f"Unsupported embedding provider {provider!r}")
    unknown = set(supplied) - allowed[provider]
    if unknown:
        raise ValueError(
            f"Unsupported {provider!r} embedding options: {sorted(unknown)}"
        )
    if provider in {"openai", "vllm"}:
        supplied.setdefault("check_embedding_ctx_length", False)
    elif provider == "voyageai":
        supplied.setdefault("truncation", True)
        supplied.setdefault("batch_size", VOYAGEAI_EMBEDDING_BATCH_SIZE)
        supplied.setdefault("document_input_type", "document")
        supplied.setdefault("query_input_type", "query")
        if supplied["document_input_type"] != "document":
            raise ValueError("VoyageAI document_input_type must be 'document'")
        if supplied["query_input_type"] != "query":
            raise ValueError("VoyageAI query_input_type must be 'query'")
    elif provider == "huggingface":
        supplied.setdefault("normalize_embeddings", False)
    return supplied


def build_embedding_client(
    *,
    provider: str,
    model_name: str,
    api_key: str,
    inference_server_url: str | None,
    provider_options: Mapping[str, Any],
) -> Embeddings:
    """Return a standard LangChain Embeddings implementation."""

    options = effective_provider_options(provider, provider_options)
    if provider in {"openai", "vllm"}:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model_name,
            api_key=cast(Any, api_key or "EMPTY"),
            base_url=inference_server_url,
            **options,
        )
    if provider == "voyageai":
        from langchain_voyageai import VoyageAIEmbeddings

        options.pop("document_input_type")
        options.pop("query_input_type")
        return VoyageAIEmbeddings(
            model=model_name,
            api_key=cast(Any, api_key),
            base_url=inference_server_url,
            **options,
        )
    if provider == "mistralai":
        from langchain_mistralai import MistralAIEmbeddings

        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            **options,
        }
        if inference_server_url:
            kwargs["endpoint"] = inference_server_url
        return MistralAIEmbeddings(**kwargs)
    if provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings

        revision = options.pop("model_revision", None)
        normalize = options.pop("normalize_embeddings")
        truncate_dim = options.pop("truncate_dim", None)
        document_prompt = options.pop("document_prompt_name", None)
        query_prompt = options.pop("query_prompt_name", None)
        encode_kwargs = {"normalize_embeddings": normalize}
        query_encode_kwargs = {"normalize_embeddings": normalize}
        if truncate_dim is not None:
            encode_kwargs["truncate_dim"] = truncate_dim
            query_encode_kwargs["truncate_dim"] = truncate_dim
        if document_prompt is not None:
            encode_kwargs["prompt_name"] = document_prompt
        if query_prompt is not None:
            query_encode_kwargs["prompt_name"] = query_prompt
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={} if revision is None else {"revision": revision},
            encode_kwargs=encode_kwargs,
            query_encode_kwargs=query_encode_kwargs,
        )
    raise ValueError(f"Unsupported embedding provider {provider!r}")
