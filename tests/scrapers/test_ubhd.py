import pytest

from scrapyrus.scrapers.iiif import IIIFImageScraper
from scrapyrus.scrapers.ubhd import UBHDScraper


class FakeResponse:
    def __init__(self, url, *, text=""):
        self.url = url
        self.text = text
        self.status_checked = False

    def raise_for_status(self):
        self.status_checked = True


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.response


def test_ubhd_scraper_responsibility():
    scraper = UBHDScraper()

    assert scraper.responsible("https://digi.ub.uni-heidelberg.de/diglit/p_g_5019")
    assert scraper.responsible("http://digi.ub.uni-heidelberg.de/diglit/p_kopt_211/")
    assert scraper.responsible(
        "https://digi.ub.uni-heidelberg.de/diglit/p_g_23?ui_lang=eng"
    )
    assert not scraper.responsible(
        "https://digi.ub.uni-heidelberg.de/diglit/p_g_5019/0001"
    )
    assert not scraper.responsible(
        "https://digi.ub.uni-heidelberg.de/diglit/iiif3/p_g_5019/manifest"
    )
    assert not scraper.responsible(
        "https://digi.ub.uni-heidelberg.de.example/diglit/p_g_5019"
    )
    assert not scraper.responsible("ftp://digi.ub.uni-heidelberg.de/diglit/p_g_5019")


def test_ubhd_scraper_reuses_iiif_image_scraper():
    assert issubclass(UBHDScraper, IIIFImageScraper)


def test_ubhd_scraper_extracts_preferred_iiif_3_manifest_link():
    page_url = "https://digi.ub.uni-heidelberg.de/diglit/p_g_5019"
    html = """
        <p class="purlcont">
          Metadata: <a href="/diglit/p_g_5019/mets">METS</a>
          <br>
          IIIF Manifest:
          <a href="/diglit/iiif/p_g_5019/manifest">version 2.1</a>,
          <a href="/diglit/iiif3/p_g_5019/manifest">version 3.0</a>
        </p>
    """

    assert UBHDScraper._manifest_url(html, page_url) == (
        "https://digi.ub.uni-heidelberg.de/diglit/iiif3/p_g_5019/manifest"
    )


def test_ubhd_scraper_falls_back_to_iiif_2_manifest_link():
    page_url = "https://digi.ub.uni-heidelberg.de/diglit/p_g_5019"
    html = """
        <p class="purlcont">
          IIIF Manifest:
          <a href="https://digi.ub.uni-heidelberg.de/diglit/iiif/p_g_5019/manifest">
            version 2.1
          </a>
        </p>
    """

    assert UBHDScraper._manifest_url(html, page_url) == (
        "https://digi.ub.uni-heidelberg.de/diglit/iiif/p_g_5019/manifest"
    )


def test_ubhd_scraper_fetches_page_to_resolve_manifest():
    source_url = "http://digi.ub.uni-heidelberg.de/diglit/p_g_5019"
    page_url = "https://digi.ub.uni-heidelberg.de/diglit/p_g_5019"
    manifest_url = "https://digi.ub.uni-heidelberg.de/diglit/iiif3/p_g_5019/manifest"
    response = FakeResponse(
        page_url,
        text=f'<a href="{manifest_url}">version 3.0</a>',
    )
    session = FakeSession(response)

    assert UBHDScraper().manifest_urls(source_url, session) == [manifest_url]
    assert session.requests == [(source_url, {"timeout": 30})]
    assert response.status_checked


def test_ubhd_scraper_requires_manifest_link():
    with pytest.raises(ValueError, match="no IIIF manifest link"):
        UBHDScraper._manifest_url(
            '<a href="/diglit/p_g_5019/mets">METS</a>',
            "https://digi.ub.uni-heidelberg.de/diglit/p_g_5019",
        )
