import pytest
from voyageai.error import RateLimitError

from scrapyrus.transcriptions.embedding_clients import (
    embed_documents_with_backoff,
    embed_query_with_backoff,
    effective_provider_options,
)


class RateLimitedProvider:
    def __init__(self, failures):
        self.failures = failures
        self.document_attempts = 0
        self.query_attempts = 0

    def embed_documents(self, texts):
        self.document_attempts += 1
        if self.document_attempts <= self.failures:
            raise RateLimitError("TPM limit reached")
        return [[0.25, 0.75] for _ in texts]

    def embed_query(self, text):
        self.query_attempts += 1
        if self.query_attempts <= self.failures:
            raise RateLimitError("TPM limit reached")
        return [0.25, 0.75]


def test_voyageai_uses_64_as_its_default_request_batch_size():
    options = effective_provider_options("voyageai")

    assert options["batch_size"] == 64


def test_voyageai_document_rate_limits_use_exponential_backoff(monkeypatch):
    provider = RateLimitedProvider(failures=3)
    sleep_calls = []
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embedding_clients.time.sleep", sleep_calls.append
    )

    result = embed_documents_with_backoff(provider, ["alpha", "beta"], "voyageai")

    assert result == [[0.25, 0.75], [0.25, 0.75]]
    assert provider.document_attempts == 4
    assert sleep_calls == [1, 2, 4]


def test_voyageai_query_rate_limits_use_exponential_backoff(monkeypatch):
    provider = RateLimitedProvider(failures=2)
    sleep_calls = []
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embedding_clients.time.sleep", sleep_calls.append
    )

    result = embed_query_with_backoff(provider, "alpha", "voyageai")

    assert result == [0.25, 0.75]
    assert provider.query_attempts == 3
    assert sleep_calls == [1, 2]


def test_voyageai_rate_limit_retries_are_bounded(monkeypatch):
    provider = RateLimitedProvider(failures=8)
    sleep_calls = []
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embedding_clients.time.sleep", sleep_calls.append
    )

    with pytest.raises(RateLimitError, match="TPM limit reached"):
        embed_documents_with_backoff(provider, ["alpha"], "voyageai")

    assert provider.document_attempts == 8
    assert sleep_calls == [1, 2, 4, 8, 16, 16, 16]


def test_other_providers_do_not_retry_voyageai_rate_limit_errors(monkeypatch):
    provider = RateLimitedProvider(failures=1)
    sleep_calls = []
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embedding_clients.time.sleep", sleep_calls.append
    )

    with pytest.raises(RateLimitError):
        embed_documents_with_backoff(provider, ["alpha"], "vllm")

    assert provider.document_attempts == 1
    assert sleep_calls == []
