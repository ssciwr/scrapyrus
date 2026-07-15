import requests

import pytest

from scrapyrus.transcriptions.llms import (
    LLM_REQUEST_TIMEOUT,
    LLMProviderBase,
    MistralProvider,
    OPENAI_EMBEDDING_CONTEXT_LENGTH,
    OpenAIProvider,
    VLLMProvider,
    initialize_llm_provider,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, *, gets=(), posts=()):
        self.headers = {}
        self.gets = list(gets)
        self.responses = list(posts)
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, *, timeout):
        self.requests.append(("GET", url, None, timeout))
        return self.gets.pop(0)

    def post(self, url, *, json, timeout):
        self.requests.append(("POST", url, json, timeout))
        return self.responses.pop(0)


def test_provider_subclasses_register_in_definition_order(monkeypatch):
    monkeypatch.setattr(LLMProviderBase, "_providers", [])

    class FirstProvider(LLMProviderBase):
        pass

    class SecondProvider(LLMProviderBase):
        pass

    class UnregisteredProvider(LLMProviderBase, register=False):
        pass

    assert LLMProviderBase.registered_providers() == (FirstProvider, SecondProvider)
    assert UnregisteredProvider not in LLMProviderBase.registered_providers()


def test_initialize_llm_provider_uses_chain_of_responsibility(monkeypatch):
    calls = []
    expected = object()

    class FirstProvider(LLMProviderBase, register=False):
        @classmethod
        def initialize(cls, url, model, api_key):
            calls.append((cls, url, model, api_key))
            return None

    class SecondProvider(LLMProviderBase, register=False):
        @classmethod
        def initialize(cls, url, model, api_key):
            calls.append((cls, url, model, api_key))
            return expected

    monkeypatch.setattr(LLMProviderBase, "_providers", [FirstProvider, SecondProvider])

    assert initialize_llm_provider("https://server", "model", "key") is expected
    assert [call[0] for call in calls] == [FirstProvider, SecondProvider]


def test_initialize_llm_provider_rejects_unknown_server(monkeypatch):
    class Provider(LLMProviderBase, register=False):
        @classmethod
        def initialize(cls, url, model, api_key):
            return None

    monkeypatch.setattr(LLMProviderBase, "_providers", [Provider])

    with pytest.raises(ValueError, match="No registered LLM provider"):
        initialize_llm_provider("https://unknown", "model", "key")


def test_mistral_initialize_detects_api_hostname_and_normalizes_url():
    provider = MistralProvider.initialize(
        "https://api.mistral.ai", "mistral-embed", "secret"
    )

    assert isinstance(provider, MistralProvider)
    assert provider.inference_server_url == "https://api.mistral.ai/v1"
    assert provider.modelname == "mistral-embed"
    assert provider.api_key == "secret"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/mistral.ai",
        "https://api.mistral.ai.example.com/v1",
        "not-a-url",
    ],
)
def test_mistral_initialize_declines_other_hostnames(url):
    assert MistralProvider.initialize(url, "model", "key") is None


def test_mistral_token_count_uses_embedding_usage(monkeypatch):
    client = FakeClient(
        posts=[
            FakeResponse(
                {
                    "data": [{"embedding": [0.25, -0.5, 1]}],
                    "usage": {"prompt_tokens": 3},
                }
            )
        ]
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = MistralProvider("https://api.mistral.ai/v1/", "mistral-embed", "secret")

    assert provider.token_count("some text") == 3
    assert client.headers["Authorization"] == "Bearer secret"
    assert client.requests == [
        (
            "POST",
            "https://api.mistral.ai/v1/embeddings",
            {"model": "mistral-embed", "input": "some text"},
            LLM_REQUEST_TIMEOUT,
        )
    ]


def test_mistral_context_length_uses_model_endpoint_and_is_cached(monkeypatch):
    client = FakeClient(gets=[FakeResponse({"max_context_length": 32768})])
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = MistralProvider(
        "https://api.mistral.ai/v1", "mistral embed/model", "key"
    )

    assert provider.context_length() == 32768
    assert provider.context_length() == 32768
    assert client.requests == [
        (
            "GET",
            "https://api.mistral.ai/v1/models/mistral%20embed%2Fmodel",
            None,
            LLM_REQUEST_TIMEOUT,
        )
    ]


def test_mistral_embedding_methods_use_embedding_endpoint(monkeypatch):
    client = FakeClient(
        posts=[
            FakeResponse(
                {
                    "data": [{"embedding": [0.25, -0.5, 1]}],
                    "usage": {"prompt_tokens": 1},
                }
            )
        ]
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = MistralProvider("https://api.mistral.ai/v1", "mistral-embed", "key")

    assert provider.embed("document") == (0.25, -0.5, 1.0)
    assert provider.embedding_length() == 3
    assert len(client.requests) == 1


def test_openai_initialize_detects_api_hostname_and_normalizes_url():
    provider = OpenAIProvider.initialize(
        "https://api.openai.com", "text-embedding-3-small", "secret"
    )

    assert isinstance(provider, OpenAIProvider)
    assert provider.inference_server_url == "https://api.openai.com/v1"
    assert provider.modelname == "text-embedding-3-small"
    assert provider.api_key == "secret"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/openai.com",
        "https://api.openai.com.example.com/v1",
        "not-a-url",
    ],
)
def test_openai_initialize_declines_other_hostnames(url):
    assert OpenAIProvider.initialize(url, "model", "key") is None


def test_openai_token_count_uses_embedding_usage(monkeypatch):
    client = FakeClient(
        posts=[
            FakeResponse(
                {
                    "data": [{"embedding": [0.25, -0.5, 1]}],
                    "usage": {"prompt_tokens": 3, "total_tokens": 3},
                }
            )
        ]
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = OpenAIProvider(
        "https://api.openai.com/v1/", "text-embedding-3-small", "secret"
    )

    assert provider.token_count("some text") == 3
    assert client.headers["Authorization"] == "Bearer secret"
    assert client.requests == [
        (
            "POST",
            "https://api.openai.com/v1/embeddings",
            {"model": "text-embedding-3-small", "input": "some text"},
            LLM_REQUEST_TIMEOUT,
        )
    ]


def test_openai_context_length_uses_embedding_api_limit():
    provider = OpenAIProvider(
        "https://api.openai.com/v1", "text-embedding-3-small", "key"
    )

    assert provider.context_length() == OPENAI_EMBEDDING_CONTEXT_LENGTH


def test_openai_embedding_methods_use_embedding_endpoint(monkeypatch):
    client = FakeClient(
        posts=[
            FakeResponse(
                {
                    "data": [{"embedding": [0.25, -0.5, 1]}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
            )
        ]
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = OpenAIProvider(
        "https://api.openai.com/v1", "text-embedding-3-small", "key"
    )

    assert provider.embed("document") == (0.25, -0.5, 1.0)
    assert provider.embedding_length() == 3
    assert len(client.requests) == 1


def test_vllm_initialize_detects_server_and_normalizes_v1_url(monkeypatch):
    client = FakeClient(gets=[FakeResponse({"version": "0.10.0"})])
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )

    provider = VLLMProvider.initialize("https://server/v1/", "model", "secret")

    assert isinstance(provider, VLLMProvider)
    assert provider.inference_server_url == "https://server"
    assert client.headers["Authorization"] == "Bearer secret"
    assert client.requests == [
        ("GET", "https://server/version", None, LLM_REQUEST_TIMEOUT)
    ]


def test_vllm_initialize_declines_non_vllm_server(monkeypatch):
    client = FakeClient(gets=[FakeResponse({"detail": "not found"}, status_code=404)])
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )

    assert VLLMProvider.initialize("https://server", "model", "key") is None


def test_vllm_token_and_context_lengths_use_tokenize_endpoint(monkeypatch):
    client = FakeClient(
        posts=[
            FakeResponse({"count": 3, "max_model_len": 8192}),
        ]
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = VLLMProvider("https://server", "model", "key")

    assert provider.token_count("some text") == 3
    assert provider.context_length() == 8192
    assert [request[2] for request in client.requests] == [
        {"model": "model", "prompt": "some text"}
    ]


def test_vllm_embedding_methods_use_openai_endpoint(monkeypatch):
    client = FakeClient(
        posts=[
            FakeResponse({"data": [{"embedding": [0.25, -0.5, 1]}]}),
        ]
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.llms.requests.Session", lambda: client
    )
    provider = VLLMProvider("https://server/v1", "model", "key")

    assert provider.embed("document") == (0.25, -0.5, 1.0)
    assert provider.embedding_length() == 3
    assert client.requests[0] == (
        "POST",
        "https://server/v1/embeddings",
        {"model": "model", "input": "document"},
        LLM_REQUEST_TIMEOUT,
    )
    assert len(client.requests) == 1
