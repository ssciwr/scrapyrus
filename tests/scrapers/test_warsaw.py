import pytest

from scrapyrus.scrapers.warsaw import WarsawScraper


def test_warsaw_scraper_responsibility():
    scraper = WarsawScraper()

    assert scraper.responsible(
        "https://www.papyrology.uw.edu.pl/papyri/pberlin11586.htm"
    )
    assert scraper.responsible(
        "http://www.papyrology.uw.edu.pl/papyri/pberlin11586.htm"
    )
    assert not scraper.responsible(
        "https://www.papyrology.uw.edu.pl/papyri/pberlin11586.jpg"
    )
    assert not scraper.responsible(
        "https://www.papyrology.uw.edu.pl/papyri/nested/pberlin11586.htm"
    )
    assert not scraper.responsible(
        "https://www.papyrology.uw.edu.pl.example/papyri/pberlin11586.htm"
    )


def test_warsaw_scraper_constructs_https_image_url():
    assert (
        WarsawScraper._image_url(
            "http://www.papyrology.uw.edu.pl/papyri/pberlin11586.htm?view=record#image"
        )
        == "https://www.papyrology.uw.edu.pl/papyri/pberlin11586.jpg"
    )

    with pytest.raises(ValueError, match="Unexpected Warsaw papyrus record URL"):
        WarsawScraper._image_url("https://example.com/papyri/pberlin11586.htm")
    with pytest.raises(ValueError, match="Unexpected Warsaw papyrus record URL"):
        WarsawScraper._image_url(
            "ftp://www.papyrology.uw.edu.pl/papyri/pberlin11586.htm"
        )


def test_warsaw_scraper_downloads_hardcoded_image_url(tmp_path, monkeypatch):
    record_url = "http://www.papyrology.uw.edu.pl/papyri/pberlin11586.htm"
    image_url = "https://www.papyrology.uw.edu.pl/papyri/pberlin11586.jpg"

    class FakeResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, *, chunk_size):
            assert chunk_size == 64 * 1024
            return iter((b"Warsaw ", b"papyrus"))

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            pass

    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("scrapyrus.scrapers.warsaw.requests.get", fake_get)

    WarsawScraper().download(record_url, tmp_path)

    assert (tmp_path / "pberlin11586.jpg").read_bytes() == b"Warsaw papyrus"
    assert requests == [
        (
            image_url,
            {"timeout": WarsawScraper.REQUEST_TIMEOUT, "stream": True},
        )
    ]
