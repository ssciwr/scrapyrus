import pytest

from scrapyrus.scrapers.egnet import EgnetScraper


PAGE_URL = "https://www.ifao.egnet.net/bases/publications/fifao81/?id=331_553_2IR"
IMAGE_URL = (
    "https://www.ifao.egnet.net/bases/publications/fifao81/"
    "docs/vignettes/331_553_2IR.jpg"
)


def test_egnet_scraper_responsibility():
    scraper = EgnetScraper()

    assert scraper.responsible(PAGE_URL)
    assert scraper.responsible(
        "http://www.ifao.egnet.net/bases/publications/fifao81?id=153_282-597conc"
    )
    assert not scraper.responsible(
        "https://www.ifao.egnet.net/bases/publications/fifao81/"
    )
    assert not scraper.responsible(
        "https://www.ifao.egnet.net/bases/publications/fifao67/?os=331"
    )
    assert not scraper.responsible(
        "https://www.ifao.egnet.net.example/bases/publications/fifao81/?id=331_553_2IR"
    )


def test_egnet_scraper_translates_record_url_to_image_url():
    assert EgnetScraper._image_url(PAGE_URL + "#image") == IMAGE_URL


def test_egnet_scraper_rejects_unsupported_record_url():
    with pytest.raises(ValueError, match="Unsupported Egnet record URL"):
        EgnetScraper._image_url(
            "https://www.ifao.egnet.net/bases/publications/fifao81/?id=../image"
        )


def test_egnet_scraper_downloads_translated_image(tmp_path, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, *, chunk_size):
            assert chunk_size == 64 * 1024
            return iter((b"egnet ", b"image"))

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            pass

    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("scrapyrus.scrapers.egnet.requests.get", fake_get)

    EgnetScraper().download(PAGE_URL, tmp_path)

    assert (tmp_path / "331_553_2IR.jpg").read_bytes() == b"egnet image"
    assert requests == [(IMAGE_URL, {"timeout": 30, "stream": True})]
