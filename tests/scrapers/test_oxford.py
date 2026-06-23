import pytest
import requests

from scrapyrus.scrapers.oxford import OxfordScraper


PAGE_URL = (
    "https://portal.sds.ox.ac.uk/articles/online_resource/"
    "P_Oxy_LXXII_4896_Loan_of_Money/21180334?file=37555639"
)
CANONICAL_PAGE_URL = PAGE_URL.partition("?")[0]
IMAGE_URL = "https://portal.sds.ox.ac.uk/ndownloader/files/37555639"
API_URL = "https://api.figshare.com/v2/articles/21180334"


class FakeResponse:
    def __init__(self, *, url="", headers=None, json_data=None, chunks=()):
        self.url = url
        self.headers = {} if headers is None else headers
        self.json_data = json_data
        self.chunks = chunks

    def raise_for_status(self):
        pass

    def json(self):
        return self.json_data

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


def test_oxford_scraper_responsibility():
    scraper = OxfordScraper()

    assert scraper.responsible(PAGE_URL)
    assert scraper.responsible(CANONICAL_PAGE_URL)
    assert scraper.responsible(
        "http://portal.sds.ox.ac.uk/articles/online_resource/record/21180334/1/"
        "?download=1&file=37555639"
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
    response = FakeResponse(
        url="https://storage.example/37555639/image.jpg",
        headers={
            "Content-Disposition": (
                'attachment; filename="POxy.v0072.n4896.a.01.hires.jpg"'
            )
        },
        chunks=(b"oxford ", b"image"),
    )
    session = FakeSession({IMAGE_URL: response})
    monkeypatch.setattr("scrapyrus.scrapers.oxford.requests.Session", lambda: session)

    OxfordScraper().download(PAGE_URL, tmp_path)

    assert (
        tmp_path / "POxy.v0072.n4896.a.01.hires.jpg"
    ).read_bytes() == b"oxford image"
    assert session.requests == [(IMAGE_URL, {"timeout": 30, "stream": True})]


def test_oxford_scraper_fetches_all_images_for_canonical_article_url(
    tmp_path, monkeypatch
):
    first_image_url = "https://portal.sds.ox.ac.uk/ndownloader/files/37555639"
    second_image_url = "https://portal.sds.ox.ac.uk/ndownloader/files/37555640"
    session = FakeSession(
        {
            API_URL: FakeResponse(
                json_data={
                    "files": [
                        {"id": 37555639, "mimetype": "image/jpeg"},
                        {"id": 37555640, "mimetype": "image/jpeg"},
                        {"id": 37555641, "mimetype": "application/pdf"},
                    ]
                }
            ),
            first_image_url: FakeResponse(
                url="https://storage.example/first.jpg",
                chunks=(b"first",),
            ),
            second_image_url: FakeResponse(
                url="https://storage.example/second.jpg",
                chunks=(b"second",),
            ),
        }
    )
    monkeypatch.setattr("scrapyrus.scrapers.oxford.requests.Session", lambda: session)
    scraper = OxfordScraper()
    wait_calls = []
    monkeypatch.setattr(scraper, "wait_for_request_slot", lambda: wait_calls.append(1))

    scraper.download(CANONICAL_PAGE_URL, tmp_path)

    assert (tmp_path / "first.jpg").read_bytes() == b"first"
    assert (tmp_path / "second.jpg").read_bytes() == b"second"
    assert wait_calls == [1]
    assert session.requests == [
        (API_URL, {"timeout": 30}),
        (first_image_url, {"timeout": 30, "stream": True}),
        (second_image_url, {"timeout": 30, "stream": True}),
    ]


def test_oxford_scraper_uses_redirect_filename_as_fallback(tmp_path, monkeypatch):
    response = FakeResponse(
        url="https://storage.example/37555639/POxy%20image.jpg",
        chunks=(b"image",),
    )
    session = FakeSession({IMAGE_URL: response})
    monkeypatch.setattr(
        "scrapyrus.scrapers.oxford.requests.Session",
        lambda: session,
    )

    OxfordScraper().download(PAGE_URL, tmp_path)

    assert (tmp_path / "POxy image.jpg").read_bytes() == b"image"


@pytest.mark.parametrize(
    ("status_code", "expected_available"),
    [(403, False), (429, False), (500, True)],
)
def test_oxford_scraper_becomes_unavailable_after_rate_limit(
    status_code,
    expected_available,
    tmp_path,
    monkeypatch,
):
    response = requests.Response()
    response.status_code = status_code
    response.url = API_URL
    session = FakeSession({API_URL: response})
    monkeypatch.setattr("scrapyrus.scrapers.oxford.requests.Session", lambda: session)
    scraper = OxfordScraper()

    with pytest.raises(requests.HTTPError):
        scraper.download(CANONICAL_PAGE_URL, tmp_path)

    assert scraper.available() is expected_available
