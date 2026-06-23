import pytest

from scrapyrus.scrapers.iiif import IIIFImageScraper
from scrapyrus.scrapers.yale import YaleScraper


class FakeResponse:
    def __init__(self, url):
        self.url = url
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


def test_yale_scraper_responsibility():
    scraper = YaleScraper()

    assert scraper.responsible("https://hdl.handle.net/10079/digcoll/2757720")
    assert scraper.responsible("http://hdl.handle.net/10079/digcoll/2756792/")
    assert scraper.responsible("https://hdl.handle.net/10079/digcoll/2757720?show=full")
    assert scraper.responsible("https://collections.library.yale.edu/catalog/33173093")
    assert not scraper.responsible("https://hdl.handle.net/10079/fa/beinecke.papyrus")
    assert not scraper.responsible("https://hdl.handle.net/10079/digcoll/not-a-number")
    assert not scraper.responsible(
        "https://hdl.handle.net.example/10079/digcoll/2757720"
    )
    assert not scraper.responsible(
        "https://collections.library.yale.edu/catalog/33173093/citation"
    )


def test_yale_scraper_reuses_iiif_image_scraper():
    assert issubclass(YaleScraper, IIIFImageScraper)


def test_yale_scraper_derives_manifest_from_redirected_catalog_url():
    source_url = "https://hdl.handle.net/10079/digcoll/2757037"
    page_url = "https://collections.library.yale.edu/catalog/33165804"
    response = FakeResponse(page_url)
    session = FakeSession(response)

    assert YaleScraper().manifest_urls(source_url, session) == [
        "https://collections.library.yale.edu/manifests/33165804"
    ]
    assert session.requests == [(source_url, {"timeout": 30})]
    assert response.status_checked


def test_yale_scraper_derives_manifest_without_fetching_catalog_url():
    source_url = "https://collections.library.yale.edu/catalog/33173093?show=full"
    session = FakeSession(FakeResponse(source_url))

    assert YaleScraper().manifest_urls(source_url, session) == [
        "https://collections.library.yale.edu/manifests/33173093"
    ]
    assert session.requests == []


def test_yale_scraper_requires_handle_to_redirect_to_catalog_record():
    session = FakeSession(
        FakeResponse("https://collections.library.yale.edu/search?q=papyrus")
    )

    with pytest.raises(ValueError, match="did not resolve to a catalog record"):
        YaleScraper().manifest_urls(
            "https://hdl.handle.net/10079/digcoll/2757720",
            session,
        )
