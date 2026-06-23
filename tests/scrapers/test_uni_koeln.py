import pytest
import requests

from scrapyrus.scrapers.uni_koeln import UniKoelnScraper


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


def test_uni_koeln_scraper_responsibility():
    scraper = UniKoelnScraper()

    assert scraper.responsible(
        "http://www.uni-koeln.de/phil-fak/ifa/NRWakademie/"
        "papyrologie/PPetaus/petaus_020.html"
    )
    assert scraper.responsible(
        "https://www.uni-koeln.de/phil-fak/ifa/NRWakademie/papyrologie/Karte/I_050.htm"
    )
    assert not scraper.responsible(
        "https://www.uni-koeln.de/phil-fak/ifa/NRWakademie/papyrologie/"
    )
    assert not scraper.responsible(
        "https://www.uni-koeln.de.example/phil-fak/ifa/NRWakademie/"
        "papyrologie/PPetaus/petaus_020.html"
    )
    assert not scraper.responsible("https://papyri.uni-koeln.de/stueck/tm109909")


def test_uni_koeln_scraper_downloads_links_after_abbildung_marker(
    tmp_path, monkeypatch
):
    source_url = (
        "http://www.uni-koeln.de/phil-fak/ifa/NRWakademie/papyrologie/Karte/I_050.html"
    )
    page_url = source_url.replace("http://", "https://")
    recto_url = (
        "https://www.uni-koeln.de/phil-fak/ifa/NRWakademie/"
        "papyrologie/PKoeln/PK5908r.jpg"
    )
    verso_url = (
        "https://www.uni-koeln.de/phil-fak/ifa/NRWakademie/"
        "papyrologie/Karte/bilder/PK5908v%20large.JPG"
    )
    html = """
        <a href="navigation.gif">navigation</a>
        <p>Abbildung:</p>
        <dd><a href="/phil-fak/ifa/NRWakademie/papyrologie/PKoeln/PK5908r.jpg">
            recto
        </a></dd>
        <dd><a href="bilder/PK5908v%20large.JPG">verso</a></dd>
        <dd><a href="bilder/PK5908v%20large.JPG">duplicate verso</a></dd>
        <a href="frames/fr050.html">Text und Abbildung</a>
    """
    responses = {
        source_url: FakeResponse(page_url, text=html),
        recto_url: FakeResponse(recto_url, chunks=(b"recto ", b"image")),
        verso_url: FakeResponse(verso_url, chunks=(b"verso image",)),
    }
    session = FakeSession(responses)
    monkeypatch.setattr(
        "scrapyrus.scrapers.uni_koeln.requests.Session", lambda: session
    )

    UniKoelnScraper().download(source_url, tmp_path)

    assert (tmp_path / "PK5908r.jpg").read_bytes() == b"recto image"
    assert (tmp_path / "PK5908v large.JPG").read_bytes() == b"verso image"
    assert not (tmp_path / "navigation.gif").exists()
    assert session.requests == [
        (source_url, {"timeout": 30}),
        (recto_url, {"timeout": 30, "stream": True}),
        (verso_url, {"timeout": 30, "stream": True}),
    ]


def test_uni_koeln_scraper_handles_page_without_abbildung(tmp_path, monkeypatch):
    page_url = (
        "https://www.uni-koeln.de/phil-fak/ifa/NRWakademie/"
        "papyrologie/bubastos/01PBub01.html"
    )
    session = FakeSession(
        {page_url: FakeResponse(page_url, text="<a href='navigation.gif'>next</a>")}
    )
    monkeypatch.setattr(
        "scrapyrus.scrapers.uni_koeln.requests.Session", lambda: session
    )

    UniKoelnScraper().download(page_url, tmp_path)

    assert list(tmp_path.iterdir()) == []
    assert session.requests == [(page_url, {"timeout": 30})]


@pytest.mark.parametrize(
    ("status_code", "expected_available"),
    [(429, False), (500, True)],
)
def test_uni_koeln_scraper_becomes_unavailable_after_rate_limit(
    status_code,
    expected_available,
    tmp_path,
    monkeypatch,
):
    page_url = (
        "https://www.uni-koeln.de/phil-fak/ifa/NRWakademie/"
        "papyrologie/bubastos/01PBub01.html"
    )
    response = requests.Response()
    response.status_code = status_code
    response.url = page_url
    session = FakeSession({page_url: response})
    monkeypatch.setattr(
        "scrapyrus.scrapers.uni_koeln.requests.Session", lambda: session
    )
    scraper = UniKoelnScraper()

    with pytest.raises(requests.HTTPError):
        scraper.download(page_url, tmp_path)

    assert scraper.available() is expected_available
