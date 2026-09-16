"""Provider selection and effective LangChain embedding configuration."""

import sys
from types import SimpleNamespace

import pytest

from scrapyrus.embeddings.clients import (
    build_embedding_client,
    effective_provider_options,
    infer_embedding_provider,
)
from scrapyrus.embeddings.specification import EmbeddingSpecification


@pytest.mark.parametrize(
    "url,provider",
    [
        ("https://api.openai.com/v1", "openai"),
        ("https://API.VOYAGEAI.COM./v1", "voyageai"),
        ("https://api.mistral.ai", "mistralai"),
        ("https://api.openai.com.example.org", "vllm"),
        ("http://localhost:8000/v1", "vllm"),
    ],
)
def test_provider_inference_uses_exact_hostnames(url, provider):
    assert infer_embedding_provider(url) == provider


@pytest.mark.parametrize(
    "provider,module,class_name,expected",
    [
        (
            "openai",
            "langchain_openai",
            "OpenAIEmbeddings",
            {
                "model": "model",
                "api_key": "secret",
                "base_url": "https://server/v1",
                "check_embedding_ctx_length": False,
            },
        ),
        (
            "vllm",
            "langchain_openai",
            "OpenAIEmbeddings",
            {
                "model": "model",
                "api_key": "secret",
                "base_url": "https://server/v1",
                "check_embedding_ctx_length": False,
            },
        ),
        (
            "voyageai",
            "langchain_voyageai",
            "VoyageAIEmbeddings",
            {
                "model": "model",
                "api_key": "secret",
                "base_url": "https://server/v1",
                "truncation": True,
                "batch_size": 1000,
            },
        ),
        (
            "mistralai",
            "langchain_mistralai",
            "MistralAIEmbeddings",
            {"model": "model", "api_key": "secret", "endpoint": "https://server/v1"},
        ),
    ],
)
def test_factory_configures_standard_clients_without_network_probing(
    provider, module, class_name, expected, monkeypatch
):
    calls = []
    client = object()
    monkeypatch.setitem(
        sys.modules,
        module,
        SimpleNamespace(
            **{class_name: lambda **options: calls.append(options) or client}
        ),
    )
    assert (
        build_embedding_client(
            provider=provider,
            model_name="model",
            api_key="secret",
            inference_server_url="https://server/",
            provider_options={},
        )
        is client
    )
    assert calls == [expected]


def test_huggingface_separates_document_and_query_prompts(monkeypatch):
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        SimpleNamespace(
            HuggingFaceEmbeddings=lambda **options: calls.append(options) or object()
        ),
    )
    options = {
        "model_revision": "revision",
        "normalize_embeddings": True,
        "truncate_dim": 256,
        "document_prompt_name": "passage",
        "query_prompt_name": "query",
    }
    build_embedding_client(
        provider="huggingface",
        model_name="model",
        api_key="",
        inference_server_url=None,
        provider_options=options,
    )
    assert calls == [
        {
            "model_name": "model",
            "model_kwargs": {"revision": "revision"},
            "encode_kwargs": {
                "normalize_embeddings": True,
                "truncate_dim": 256,
                "prompt_name": "passage",
            },
            "query_encode_kwargs": {
                "normalize_embeddings": True,
                "truncate_dim": 256,
                "prompt_name": "query",
            },
        }
    ]
    assert options["query_prompt_name"] == "query"


@pytest.mark.parametrize(
    "provider,options",
    [
        ("unknown", {}),
        ("openai", {"api_key": "secret"}),
        ("vllm", {"base_url": "https://private"}),
        ("voyageai", {"query_input_type": "document"}),
        ("voyageai", {"document_input_type": "query"}),
        ("huggingface", {"model_kwargs": {"token": "secret"}}),
    ],
)
def test_unpublished_or_secret_provider_options_are_rejected(provider, options):
    with pytest.raises(ValueError):
        effective_provider_options(provider, options)


def test_voyage_specification_records_document_and_query_roles():
    spec = EmbeddingSpecification(model_name="voyage-3", provider="voyageai")
    assert spec.provider_options == {
        "truncation": True,
        "batch_size": 1000,
        "document_input_type": "document",
        "query_input_type": "query",
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"model_name": " "},
        {"provider": "unsupported"},
        {"embedding_size": True},
        {"embedding_size": 0},
        {"contract_version": 2},
        {"contract_version": True},
        {"provider_options": {"dimensions": 3}, "embedding_size": 2},
        {"endpoint_profile": "bad-profile"},
        {"api_key": "secret"},
    ],
)
def test_specification_rejects_invalid_contract_fields(fields):
    with pytest.raises(ValueError):
        EmbeddingSpecification.model_validate(
            {"model_name": "model", "provider": "openai", **fields}
        )


def test_vllm_requires_a_resolvable_endpoint_profile():
    with pytest.raises(ValueError, match="endpoint_profile"):
        EmbeddingSpecification(model_name="model", provider="vllm")


def test_real_voyage_integration_batches_and_uses_distinct_embedding_roles():
    calls = []
    client = build_embedding_client(
        provider="voyageai",
        model_name="voyage-3",
        api_key="test-key",
        inference_server_url="https://api.voyageai.com",
        provider_options={"batch_size": 2},
    )

    class SDK:
        def tokenize(self, texts, *, model):
            return [[1] for text in texts]

        def embed(self, texts, **options):
            calls.append((texts, options))
            return SimpleNamespace(embeddings=[[1.0, 0.0] for text in texts])

    client._client = SDK()
    assert client.embed_documents(["first", "second", "third"]) == [[1.0, 0.0]] * 3
    assert client.embed_query("question") == [1.0, 0.0]
    assert [texts for texts, _ in calls] == [
        ["first", "second"],
        ["third"],
        ["question"],
    ]
    assert [options["input_type"] for _, options in calls] == [
        "document",
        "document",
        "query",
    ]
    assert all(options["truncation"] is True for _, options in calls)


def test_real_huggingface_integration_preserves_separate_prompts(monkeypatch):
    import numpy as np

    calls = []

    class Model:
        def __init__(self, model_name, **options):
            calls.append((model_name, options))

        def encode(self, texts, **options):
            calls.append((texts, options))
            return np.array([[1.0, 0.0] for text in texts])

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    client = build_embedding_client(
        provider="huggingface",
        model_name="local-model",
        api_key="",
        inference_server_url=None,
        provider_options={
            "model_revision": "revision",
            "normalize_embeddings": True,
            "document_prompt_name": "passage",
            "query_prompt_name": "query",
        },
    )
    assert client.embed_documents(["source"]) == [[1.0, 0.0]]
    assert client.embed_query("question") == [1.0, 0.0]
    assert calls[0] == ("local-model", {"cache_folder": None, "revision": "revision"})
    assert calls[1][1]["prompt_name"] == "passage"
    assert calls[2][1]["prompt_name"] == "query"
    assert (
        calls[1][1]["normalize_embeddings"]
        is calls[2][1]["normalize_embeddings"]
        is True
    )
