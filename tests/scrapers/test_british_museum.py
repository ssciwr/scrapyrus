import pytest
import requests

from scrapyrus.scrapers.british_museum import BritishMuseumScraper


class FakeResponse:
    def __init__(self, *, url="", text="", headers=None, chunks=()):
        self.url = url
        self.text = text
        self.headers = {} if headers is None else headers
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


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses[url]

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        pass


def test_british_museum_scraper_responsibility():
    scraper = BritishMuseumScraper()

    assert scraper.responsible(
        "https://www.britishmuseum.org/collection/object/Y_EA55761"
    )
    assert scraper.responsible(
        "http://www.britishmuseum.org/collection/object/H_1980-0303-2/"
    )
    assert not scraper.responsible(
        "https://www.britishmuseum.org/collection/image/1367765001"
    )
    assert not scraper.responsible(
        "https://www.britishmuseum.org/research/collection_online/"
        "collection_object_details.aspx?objectId=121302&partId=1"
    )
    assert not scraper.responsible(
        "https://www.britishmuseum.org.example/collection/object/Y_EA55761"
    )


def test_british_museum_scraper_extracts_image_pages_from_fallback_markup():
    page_url = "https://www.britishmuseum.org/collection/object/Y_EA55761"
    html = """
        <div class="object-detail__image">
          <a href="/collection/image/1367765001"><img src="first.jpg"></a>
          <a href="https://www.britishmuseum.org/collection/image/413397001">
            <img src="second.jpg">
          </a>
          <a href="/collection/image/1367765001">duplicate</a>
          <a href="https://example.com/collection/image/123">external</a>
        </div>
        <a href="/collection/image/999">unrelated image</a>
    """

    assert BritishMuseumScraper._image_page_urls(html, page_url) == [
        "https://www.britishmuseum.org/collection/image/1367765001",
        "https://www.britishmuseum.org/collection/image/413397001",
    ]


def test_british_museum_scraper_extracts_nested_download_link():
    image_page_url = "https://www.britishmuseum.org/collection/image/1367765001"
    html = """
        <a href="/licensing">Download licensing information</a>
        <a class="button" href="/api/_image-download?id=1367765001">
          <span>Download this image</span>
        </a>
    """

    assert BritishMuseumScraper._download_url(html, image_page_url) == (
        "https://www.britishmuseum.org/api/_image-download?id=1367765001"
    )


def test_british_museum_scraper_downloads_all_images(tmp_path, monkeypatch):
    source_url = "https://www.britishmuseum.org/collection/object/Y_EA55761"
    first_page_url = "https://www.britishmuseum.org/collection/image/1367765001"
    second_page_url = "https://www.britishmuseum.org/collection/image/413397001"
    first_download_url = (
        "https://www.britishmuseum.org/api/_image-download?id=1367765001"
    )
    second_download_url = (
        "https://www.britishmuseum.org/api/_image-download?id=413397001"
    )
    first_media_url = "https://media.britishmuseum.org/images/first-image.jpg"
    second_media_url = "https://media.britishmuseum.org/images/second-image.jpg"
    responses = {
        source_url: FakeResponse(
            url=source_url,
            text=(
                '<div class="object-detail__image">'
                f'<a href="{first_page_url}">first</a>'
                f'<a href="{second_page_url}">second</a>'
                "</div>"
            ),
        ),
        first_page_url: FakeResponse(
            url=first_page_url,
            text=f'<a href="{first_download_url}">Download this image</a>',
        ),
        second_page_url: FakeResponse(
            url=second_page_url,
            text=f'<a href="{second_download_url}">Download this image</a>',
        ),
        first_download_url: FakeResponse(
            url=first_media_url,
            chunks=(b"first ", b"image"),
        ),
        second_download_url: FakeResponse(
            url=second_media_url,
            headers={"Content-Disposition": 'attachment; filename="EA 55761 back.jpg"'},
            chunks=(b"second image",),
        ),
    }
    session = FakeSession(responses)
    monkeypatch.setattr(
        "scrapyrus.scrapers.british_museum.requests.Session",
        lambda: session,
    )

    BritishMuseumScraper().download(source_url, tmp_path)

    assert (tmp_path / "first-image.jpg").read_bytes() == b"first image"
    assert (tmp_path / "EA 55761 back.jpg").read_bytes() == b"second image"
    assert session.requests == [
        (source_url, {"timeout": 30}),
        (first_page_url, {"timeout": 30}),
        (first_download_url, {"timeout": 30, "stream": True}),
        (second_page_url, {"timeout": 30}),
        (second_download_url, {"timeout": 30, "stream": True}),
    ]


@pytest.mark.parametrize(
    ("status_code", "expected_available"),
    [(403, False), (429, True), (500, True)],
)
def test_british_museum_scraper_becomes_unavailable_after_forbidden_response(
    status_code,
    expected_available,
    tmp_path,
    monkeypatch,
):
    source_url = "https://www.britishmuseum.org/collection/object/Y_EA55761"
    response = requests.Response()
    response.status_code = status_code
    response.url = source_url
    session = FakeSession({source_url: response})
    monkeypatch.setattr(
        "scrapyrus.scrapers.british_museum.requests.Session",
        lambda: session,
    )
    scraper = BritishMuseumScraper()

    with pytest.raises(requests.HTTPError):
        scraper.download(source_url, tmp_path)

    assert scraper.available() is expected_available
