import pytest

from scrapyrus.scrapers.met_museum import MetMuseumScraper


class FakeResponse:
    def __init__(self, *, url="", text="", chunks=()):
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


def test_met_museum_scraper_responsibility():
    scraper = MetMuseumScraper()

    assert scraper.responsible("https://www.metmuseum.org/art/collection/search/474971")
    assert scraper.responsible(
        "http://www.metmuseum.org/de/art/collection/search/474971/"
    )
    assert not scraper.responsible(
        "https://www.metmuseum.org/art/collection/search?q=papyrus"
    )
    assert not scraper.responsible(
        "https://www.metmuseum.org/art/collection/search/474971/images"
    )
    assert not scraper.responsible(
        "https://www.metmuseum.org.example/art/collection/search/474971"
    )


def test_met_museum_scraper_extracts_original_image_urls_from_next_data():
    html = r"""
        <img src="https://collectionapi.metmuseum.org/api/collection/v1/iiif/
                  474971/964863/main-image">
        <script>unrelated script</script>
        <script>
          self.__next_f.push([1,
            "originalImageUrl\":\"https://images.metmuseum.org/CRDImages/md/original/front.jpg\",
             \"originalImageUrl\":\"https://images.metmuseum.org/CRDImages/md/original/back.jpg\",
             \"originalImageUrl\":\"https://images.metmuseum.org/CRDImages/md/original/front.jpg\",
             \"originalImageUrl\":\"https://example.com/not-a-met-image.jpg\""
          ])
        </script>
    """

    assert MetMuseumScraper._image_urls(html) == [
        "https://images.metmuseum.org/CRDImages/md/original/front.jpg",
        "https://images.metmuseum.org/CRDImages/md/original/back.jpg",
    ]


def test_met_museum_scraper_also_accepts_unescaped_json():
    html = """
        <script type="application/json">
          {"originalImageUrl":
           "https://images.metmuseum.org/CRDImages/md/original/image.jpg"}
        </script>
    """

    assert MetMuseumScraper._image_urls(html) == [
        "https://images.metmuseum.org/CRDImages/md/original/image.jpg"
    ]


def test_met_museum_scraper_downloads_all_original_images(tmp_path, monkeypatch):
    source_url = "https://www.metmuseum.org/art/collection/search/474971"
    final_record_url = source_url + "?canonical=1"
    first_image_url = (
        "https://images.metmuseum.org/CRDImages/md/original/front%20image.jpg"
    )
    second_image_url = (
        "https://images.metmuseum.org/CRDImages/md/original/back-image.tif"
    )
    record_html = (
        '<script type="application/json">'
        f'{{"originalImageUrl":"{first_image_url}"}},'
        f'{{"originalImageUrl":"{second_image_url}"}}'
        "</script>"
    )
    responses = {
        source_url: FakeResponse(url=final_record_url, text=record_html),
        first_image_url: FakeResponse(chunks=(b"front ", b"image")),
        second_image_url: FakeResponse(chunks=(b"back image",)),
    }
    session = FakeSession(responses)
    monkeypatch.setattr(
        "scrapyrus.scrapers.met_museum.requests.Session",
        lambda: session,
    )

    MetMuseumScraper().download(source_url, tmp_path)

    assert (tmp_path / "front image.jpg").read_bytes() == b"front image"
    assert (tmp_path / "back-image.tif").read_bytes() == b"back image"
    assert session.requests == [
        (source_url, {"timeout": 30}),
        (first_image_url, {"timeout": 30, "stream": True}),
        (second_image_url, {"timeout": 30, "stream": True}),
    ]


def test_met_museum_scraper_rejects_record_without_downloadable_images(
    tmp_path,
    monkeypatch,
):
    source_url = "https://www.metmuseum.org/art/collection/search/474971"
    session = FakeSession(
        {source_url: FakeResponse(url=source_url, text="<html></html>")}
    )
    monkeypatch.setattr(
        "scrapyrus.scrapers.met_museum.requests.Session",
        lambda: session,
    )

    with pytest.raises(ValueError, match="has no downloadable images"):
        MetMuseumScraper().download(source_url, tmp_path)
