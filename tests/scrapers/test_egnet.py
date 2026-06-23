import pytest

from scrapyrus.scrapers.egnet import EgnetScraper


PAGE_URL = "https://www.ifao.egnet.net/bases/publications/fifao81/?id=331_553_2IR"
IMAGE_URL = (
    "https://www.ifao.egnet.net/bases/publications/fifao81/"
    "docs/vignettes/331_553_2IR.jpg"
)
FIFAO67_OFFSET_URL = "http://www.ifao.egnet.net/bases/publications/fifao67/?os=331"
FIFAO67_IMAGE_URL = (
    "https://www.ifao.egnet.net/bases/publications/fifao67/docs/vignettes/325.jpg"
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
    assert scraper.responsible(FIFAO67_OFFSET_URL)
    assert scraper.responsible(
        "https://www.ifao.egnet.net/bases/publications/fifao67/?id=001"
    )
    assert not scraper.responsible(
        "https://www.ifao.egnet.net/bases/publications/fifao67/?os=record"
    )
    assert not scraper.responsible(
        "https://www.ifao.egnet.net/bases/publications/fifao81/?os=1"
    )
    assert not scraper.responsible(
        "https://www.ifao.egnet.net.example/bases/publications/fifao81/?id=331_553_2IR"
    )


def test_egnet_scraper_translates_record_url_to_image_url():
    assert EgnetScraper._image_url(PAGE_URL + "#image") == IMAGE_URL
    assert EgnetScraper._image_url(
        "https://www.ifao.egnet.net/bases/publications/fifao67/?id=001"
    ) == (
        "https://www.ifao.egnet.net/bases/publications/fifao67/docs/vignettes/001.jpg"
    )


def test_egnet_scraper_finds_fifao67_offset_vignette():
    html = """
        <img src="/unrelated.jpg" />
        <img src="https://example.com/docs/vignettes/other.jpg" />
        <img src="docs/vignettes/325.jpg" />
    """

    assert (
        EgnetScraper._offset_image_url(
            html,
            "https://www.ifao.egnet.net/bases/publications/fifao67/?os=331",
        )
        == FIFAO67_IMAGE_URL
    )


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


def test_egnet_scraper_resolves_offset_and_downloads_image(tmp_path, monkeypatch):
    class FakeResponse:
        def __init__(self, *, url, text="", chunks=()):
            self.url = url
            self.text = text
            self.chunks = chunks

        def raise_for_status(self):
            pass

        def iter_content(self, *, chunk_size):
            assert chunk_size == 64 * 1024
            return iter(self.chunks)

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            pass

    page_url = FIFAO67_OFFSET_URL.replace("http://", "https://")
    responses = {
        FIFAO67_OFFSET_URL: FakeResponse(
            url=page_url,
            text='<img src="docs/vignettes/325.jpg" />',
        ),
        FIFAO67_IMAGE_URL: FakeResponse(
            url=FIFAO67_IMAGE_URL,
            chunks=(b"fifao 67 ", b"image"),
        ),
    }
    requests_made = []

    def fake_get(url, **kwargs):
        requests_made.append((url, kwargs))
        return responses[url]

    monkeypatch.setattr("scrapyrus.scrapers.egnet.requests.get", fake_get)

    EgnetScraper().download(FIFAO67_OFFSET_URL, tmp_path)

    assert (tmp_path / "325.jpg").read_bytes() == b"fifao 67 image"
    assert requests_made == [
        (FIFAO67_OFFSET_URL, {"timeout": 30}),
        (FIFAO67_IMAGE_URL, {"timeout": 30, "stream": True}),
    ]
