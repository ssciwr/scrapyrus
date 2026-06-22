import pytest

from scrapyrus.scrapers.aphrodito import AphroditoScraper


def test_aphrodito_scraper_responsibility():
    scraper = AphroditoScraper()

    assert scraper.responsible(
        "https://bipab.aphrodito.info/pages_html/P_Lond_V_1662.html"
    )
    assert scraper.responsible(
        "http://bipab.aphrodito.info/pages_html/P_Lond_V_1662.html"
    )
    assert not scraper.responsible(
        "https://bipab.aphrodito.info/images/grandes_images/P_Lond_V_1662.jpg"
    )
    assert not scraper.responsible(
        "https://bipab.aphrodito.info.example/pages_html/P_Lond_V_1662.html"
    )
    assert not scraper.responsible(
        "https://bipab.aphrodito.info/pages_html/nested/P_Lond_V_1662.html"
    )


def test_aphrodito_scraper_translates_record_url_to_image_url():
    assert AphroditoScraper._image_url(
        "https://bipab.aphrodito.info/pages_html/P_Lond_V_1662.html?view=full#image"
    ) == ("https://bipab.aphrodito.info/images/grandes_images/P_Lond_V_1662.jpg")


def test_aphrodito_scraper_rejects_unsupported_record_url():
    with pytest.raises(ValueError, match="Unsupported Aphrodito record URL"):
        AphroditoScraper._image_url(
            "https://bipab.aphrodito.info/pages_html/P_Lond_V_1662.htm"
        )


def test_aphrodito_scraper_downloads_translated_image(tmp_path, monkeypatch):
    page_url = "https://bipab.aphrodito.info/pages_html/P_Lond_V_1662.html"
    image_url = "https://bipab.aphrodito.info/images/grandes_images/P_Lond_V_1662.jpg"

    class FakeResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, *, chunk_size):
            assert chunk_size == 64 * 1024
            return iter((b"aphrodito ", b"image"))

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            pass

    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("scrapyrus.scrapers.aphrodito.requests.get", fake_get)

    AphroditoScraper().download(page_url, tmp_path)

    assert (tmp_path / "P_Lond_V_1662.jpg").read_bytes() == b"aphrodito image"
    assert requests == [(image_url, {"timeout": 30, "stream": True})]
