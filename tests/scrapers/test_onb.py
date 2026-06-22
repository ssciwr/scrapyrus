import pytest
import requests

from scrapyrus.images import image_log_file
from scrapyrus.scrapers.iiif import IIIFImageScraper
from scrapyrus.scrapers.onb import ONBScraper


class FakeIIIFResponse:
    def __init__(self, url, *, text="", json_data=None):
        self.url = url
        self.text = text
        self.json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self.json_data


class FakeIIIFSession:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses[url]


def test_onb_scraper_responsibility():
    scraper = ONBScraper()

    assert scraper.responsible("http://data.onb.ac.at/rec/RZ00071734")
    assert scraper.responsible("https://data.onb.ac.at/rep/131A98B7")
    assert scraper.responsible("https://onb.digital/result/131A98B7")
    assert scraper.responsible("https://viewer.onb.ac.at/131A98B7")
    assert scraper.responsible(
        "https://search.onb.ac.at/primo-explore/fulldisplay?docid=record"
    )
    assert scraper.responsible(
        "https://api.onb.ac.at/iiif/presentation/v3/manifest/131A98B7"
    )
    assert not scraper.responsible("https://data.onb.ac.at/unrelated/RZ00071734")
    assert not scraper.responsible("https://data.onb.ac.at.example/rec/RZ00071734")


@pytest.mark.parametrize(
    ("status_code", "expected_available"),
    [(429, False), (500, True)],
)
def test_onb_scraper_becomes_unavailable_after_rate_limit(
    status_code,
    expected_available,
    tmp_path,
    monkeypatch,
):
    response = requests.Response()
    response.status_code = status_code

    def fail_download(self, url, target):
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(IIIFImageScraper, "download", fail_download)
    scraper = ONBScraper()
    log = tmp_path / "images.log"

    with (
        image_log_file(log, "WARNING"),
        pytest.raises(requests.HTTPError),
    ):
        scraper.download("https://viewer.onb.ac.at/131A98B7", tmp_path)

    assert scraper.available() is expected_available
    log_text = log.read_text(encoding="utf-8")
    if status_code == 429:
        assert "ONB rate limit triggered by HTTP 429" in log_text
        assert "https://viewer.onb.ac.at/131A98B7" in log_text
    else:
        assert log_text == ""


def test_onb_scraper_follows_equivalent_page_links_with_beautiful_soup():
    record_url = "http://data.onb.ac.at/rec/RZ00071734"
    primo_url = "https://search.onb.ac.at/primo-explore/fulldisplay?docid=record"
    representation_url = "http://data.onb.ac.at/rep/131A98B7"
    result_url = "https://onb.digital/result/131A98B7"
    digitalisat_url = "https://digital.onb.ac.at/rep/access/open/131A98B7"
    manifest_url = "https://api.onb.ac.at/iiif/presentation/v3/manifest/131A98B7"
    responses = {
        record_url: FakeIIIFResponse(
            primo_url,
            text=f"""
                <a href="https://example.com/not-it">Volldigitalisat preview</a>
                <a href="{representation_url}"><span>Volldigitalisat</span></a>
            """,
        ),
        representation_url: FakeIIIFResponse(
            result_url,
            text=f"""
                <a id="Digitalisat" href="{digitalisat_url}">
                    Zum Digitalisat
                </a>
            """,
        ),
    }
    session = FakeIIIFSession(responses)

    assert ONBScraper().manifest_urls(record_url, session) == [manifest_url]
    assert session.requests == [
        (record_url, {"timeout": 30}),
        (representation_url, {"timeout": 30}),
    ]


def test_onb_scraper_uses_primo_api_when_record_html_is_javascript_shell():
    record_url = "http://data.onb.ac.at/rec/RZ00071734"
    primo_url = (
        "https://search.onb.ac.at/primo-explore/fulldisplay"
        "?docid=ONB_alma21473259130003338&context=L&vid=ONB&lang=de_DE"
        "&search_scope=ONB_gesamtbestand&adaptor=Local%20Search%20Engine"
    )
    guest_url = (
        "https://search.onb.ac.at/primo_library/libweb/webservices/rest/v1/guestJwt/ONB"
    )
    pnx_url = (
        "https://search.onb.ac.at/primo_library/libweb/webservices/rest/"
        "primo-explore/v1/pnxs/L/ONB_alma21473259130003338"
    )
    representation_url = "http://data.onb.ac.at/rep/131A98B7"
    result_url = "https://onb.digital/result/131A98B7"
    digitalisat_url = "https://digital.onb.ac.at/rep/access/open/131A98B7"
    manifest_url = "https://api.onb.ac.at/iiif/presentation/v3/manifest/131A98B7"
    responses = {
        record_url: FakeIIIFResponse(primo_url, text="<primo-explore></primo-explore>"),
        guest_url: FakeIIIFResponse(guest_url, json_data="guest-token"),
        pnx_url: FakeIIIFResponse(
            pnx_url,
            json_data={
                "delivery": {
                    "link": [
                        {
                            "displayLabel": "Volldigitalisat",
                            "linkURL": representation_url,
                        }
                    ]
                }
            },
        ),
        representation_url: FakeIIIFResponse(
            result_url,
            text=f'<a id="Digitalisat" href="{digitalisat_url}">link</a>',
        ),
    }
    session = FakeIIIFSession(responses)

    assert ONBScraper().manifest_urls(record_url, session) == [manifest_url]
    assert session.requests == [
        (record_url, {"timeout": 30}),
        (
            guest_url,
            {
                "params": {
                    "isGuest": "true",
                    "lang": "de_DE",
                    "targetUrl": (
                        "https%3A%2F%2Fsearch.onb.ac.at%2Fprimo-explore%2F"
                        "fulldisplay%3Fdocid%3DONB_alma21473259130003338%26"
                        "context%3DL%26vid%3DONB%26lang%3Dde_DE%26search_scope%"
                        "3DONB_gesamtbestand%26adaptor%3DLocal%2520Search%2520Engine"
                    ),
                    "viewId": "ONB",
                },
                "timeout": 30,
            },
        ),
        (
            pnx_url,
            {
                "params": {
                    "vid": "ONB",
                    "lang": "de_DE",
                    "search_scope": "ONB_gesamtbestand",
                    "adaptor": "Local Search Engine",
                },
                "headers": {"Authorization": "Bearer guest-token"},
                "timeout": 30,
            },
        ),
        (representation_url, {"timeout": 30}),
    ]
