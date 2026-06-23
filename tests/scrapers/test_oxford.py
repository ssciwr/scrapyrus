import pytest

from scrapyrus.scrapers.oxford import OxfordScraper


PAGE_URL = (
    "https://portal.sds.ox.ac.uk/articles/online_resource/"
    "P_Oxy_LXXII_4896_Loan_of_Money/21180334?file=37555639"
)
IMAGE_URL = "https://portal.sds.ox.ac.uk/ndownloader/files/37555639"


def test_oxford_scraper_responsibility():
    scraper = OxfordScraper()

    assert scraper.responsible(PAGE_URL)
    assert scraper.responsible(
        "http://portal.sds.ox.ac.uk/articles/online_resource/record/21180334/1/"
        "?download=1&file=37555639"
    )
    assert not scraper.responsible(
        "https://portal.sds.ox.ac.uk/articles/online_resource/record/21180334"
    )
    assert not scraper.responsible(
        "https://portal.sds.ox.ac.uk/articles/online_resource/record/21180334"
        "?file=not-a-number"
    )
    assert not scraper.responsible(
        "https://portal.sds.ox.ac.uk/articles/online_resource/record/21180334"
        "?file=37555639&file=37555640"
    )
    assert not scraper.responsible(
        "https://portal.sds.ox.ac.uk.example/articles/online_resource/record/"
        "21180334?file=37555639"
    )


def test_oxford_scraper_translates_record_url_to_image_url():
    assert OxfordScraper._image_url(PAGE_URL + "#preview") == IMAGE_URL


def test_oxford_scraper_rejects_unsupported_record_url():
    with pytest.raises(ValueError, match="Unsupported Oxford repository URL"):
        OxfordScraper._image_url(
            "https://portal.sds.ox.ac.uk/articles/online_resource/record/21180334"
            "?file=../image"
        )


def test_oxford_scraper_downloads_translated_image(tmp_path, monkeypatch):
    class FakeResponse:
        url = "https://storage.example/37555639/image.jpg"
        headers = {
            "Content-Disposition": (
                'attachment; filename="POxy.v0072.n4896.a.01.hires.jpg"'
            )
        }

        def raise_for_status(self):
            pass

        def iter_content(self, *, chunk_size):
            assert chunk_size == 64 * 1024
            return iter((b"oxford ", b"image"))

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            pass

    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("scrapyrus.scrapers.oxford.requests.get", fake_get)

    OxfordScraper().download(PAGE_URL, tmp_path)

    assert (
        tmp_path / "POxy.v0072.n4896.a.01.hires.jpg"
    ).read_bytes() == b"oxford image"
    assert requests == [(IMAGE_URL, {"timeout": 30, "stream": True})]


def test_oxford_scraper_uses_redirect_filename_as_fallback(tmp_path, monkeypatch):
    class FakeResponse:
        url = "https://storage.example/37555639/POxy%20image.jpg"
        headers = {}

        def raise_for_status(self):
            pass

        def iter_content(self, *, chunk_size):
            return iter((b"image",))

        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            pass

    monkeypatch.setattr(
        "scrapyrus.scrapers.oxford.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )

    OxfordScraper().download(PAGE_URL, tmp_path)

    assert (tmp_path / "POxy image.jpg").read_bytes() == b"image"
