import pytest

from scrapyrus.scrapers.doi import DOIScraper


class FakeResponse:
    def __init__(self, url: str):
        self.url = url
        self.closed = False

    def raise_for_status(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.closed = True


def test_doi_scraper_responsibility():
    scraper = DOIScraper()

    assert scraper.responsible("https://doi.org/10.1234/example")
    assert scraper.responsible("https://doi.org")
    assert not scraper.responsible("http://doi.org/10.1234/example")
    assert not scraper.responsible("https://www.doi.org/10.1234/example")
    assert not scraper.responsible("https://doi.org.example/10.1234/example")


def test_doi_scraper_resolves_redirect_without_downloading_response_body(monkeypatch):
    source_url = "https://doi.org/10.1234/example"
    destination_url = "https://images.example/record/42"
    response = FakeResponse(destination_url)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr("scrapyrus.scrapers.doi.requests.get", fake_get)

    assert DOIScraper().resolve(source_url) == destination_url
    assert calls == [
        (
            source_url,
            {
                "allow_redirects": True,
                "stream": True,
                "timeout": DOIScraper.REQUEST_TIMEOUT,
            },
        )
    ]
    assert response.closed


def test_doi_scraper_rejects_url_that_does_not_redirect(monkeypatch):
    source_url = "https://doi.org/10.1234/example"
    monkeypatch.setattr(
        "scrapyrus.scrapers.doi.requests.get",
        lambda url, **kwargs: FakeResponse(source_url),
    )

    with pytest.raises(RuntimeError, match="DOI URL did not redirect"):
        DOIScraper().resolve(source_url)
