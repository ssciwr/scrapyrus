import json

import pytest
import requests

from scrapyrus.scrapers.uc_berkeley import UCBerkeleyScraper


class FakeResponse:
    def __init__(self, url, *, text="", chunks=()):
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


def test_uc_berkeley_scraper_responsibility():
    scraper = UCBerkeleyScraper()

    assert scraper.responsible("https://digicoll.lib.berkeley.edu/record/230934")
    assert scraper.responsible("http://digicoll.lib.berkeley.edu/record/230934/")
    assert scraper.responsible(
        "https://digicoll.lib.berkeley.edu/record/230934?v=uv#files"
    )
    assert not scraper.responsible("https://digicoll.lib.berkeley.edu/record/")
    assert not scraper.responsible(
        "https://digicoll.lib.berkeley.edu/record/230934/files/AP03149aA.jpg"
    )
    assert not scraper.responsible(
        "https://digicoll.lib.berkeley.edu.example/record/230934"
    )


def test_uc_berkeley_scraper_downloads_images_from_json_ld(tmp_path, monkeypatch):
    source_url = "https://digicoll.lib.berkeley.edu/record/230934"
    final_page_url = source_url + "?v=uv"
    first_image_url = source_url + "/files/AP03149aA.jpg"
    second_image_url = source_url + "/files/AP03150%20verso.JPG"
    schema = {
        "@type": "ImageObject",
        "contentUrl": [
            first_image_url,
            "/record/230934/files/AP03150%20verso.JPG",
            first_image_url,
            source_url + "/files/metadata.xml",
            "https://example.com/unrelated.jpg",
            None,
        ],
    }
    html = f"""
        <a href="/unrelated/navigation.jpg">unrelated image</a>
        <script type="application/ld+json">{{"contentUrl": ["wrong.jpg"]}}</script>
        <script id="detailed-schema-org" type="application/ld+json">
            {json.dumps(schema)}
        </script>
        <div id="record-files-collapse"></div>
    """
    responses = {
        source_url: FakeResponse(final_page_url, text=html),
        first_image_url: FakeResponse(first_image_url, chunks=(b"first ", b"image")),
        second_image_url: FakeResponse(second_image_url, chunks=(b"second image",)),
    }
    session = FakeSession(responses)
    monkeypatch.setattr(
        "scrapyrus.scrapers.uc_berkeley.requests.Session", lambda: session
    )

    UCBerkeleyScraper().download(source_url, tmp_path)

    assert (tmp_path / "AP03149aA.jpg").read_bytes() == b"first image"
    assert (tmp_path / "AP03150 verso.JPG").read_bytes() == b"second image"
    assert session.requests == [
        (source_url, {"timeout": 30}),
        (first_image_url, {"timeout": 30, "stream": True}),
        (second_image_url, {"timeout": 30, "stream": True}),
    ]


def test_uc_berkeley_scraper_handles_record_without_json_ld(tmp_path, monkeypatch):
    page_url = "https://digicoll.lib.berkeley.edu/record/230935"
    session = FakeSession(
        {
            page_url: FakeResponse(
                page_url, text="<div id='record-files-collapse'></div>"
            )
        }
    )
    monkeypatch.setattr(
        "scrapyrus.scrapers.uc_berkeley.requests.Session", lambda: session
    )

    UCBerkeleyScraper().download(page_url, tmp_path)

    assert list(tmp_path.iterdir()) == []
    assert session.requests == [(page_url, {"timeout": 30})]


@pytest.mark.parametrize(
    ("status_code", "expected_available"),
    [(429, False), (500, True)],
)
def test_uc_berkeley_scraper_becomes_unavailable_after_rate_limit(
    status_code,
    expected_available,
    tmp_path,
    monkeypatch,
):
    page_url = "https://digicoll.lib.berkeley.edu/record/230935"
    response = requests.Response()
    response.status_code = status_code
    response.url = page_url
    session = FakeSession({page_url: response})
    monkeypatch.setattr(
        "scrapyrus.scrapers.uc_berkeley.requests.Session", lambda: session
    )
    scraper = UCBerkeleyScraper()

    with pytest.raises(requests.HTTPError):
        scraper.download(page_url, tmp_path)

    assert scraper.available() is expected_available
