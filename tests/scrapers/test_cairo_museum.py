from scrapyrus.scrapers.cairo_museum import CairoMuseumScraper


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


def test_cairo_museum_scraper_responsibility():
    scraper = CairoMuseumScraper()

    assert scraper.responsible(
        "http://ipap.csad.ox.ac.uk/4DLink4/4DACTION/IPAPwebquery"
        "?vPub=P.Oxy.&vVol=16&vNum=1908"
    )
    assert scraper.responsible(
        "http://ipap.csad.ox.ac.uk/Enteuxeis-bw/300dpi/P.Enteux.34r.jpg"
    )
    assert scraper.responsible(
        "https://ipap.csad.ox.ac.uk/POxy-bw/72dpi/P.Oxy.XVI.1908.JPG"
    )
    assert not scraper.responsible(
        "http://ipap.csad.ox.ac.uk/4DLink4/4DACTION/help.html"
    )
    assert not scraper.responsible(
        "http://ipap.csad.ox.ac.uk.example/POxy-bw/300dpi/P.Oxy.XVI.1908.jpg"
    )
    assert not scraper.responsible(
        "ftp://ipap.csad.ox.ac.uk/POxy-bw/300dpi/P.Oxy.XVI.1908.jpg"
    )


def test_cairo_museum_scraper_extracts_300_dpi_image_links():
    page_url = (
        "http://ipap.csad.ox.ac.uk/4DLink4/4DACTION/IPAPwebquery"
        "?vPub=P.Oxy.&vVol=16&vNum=1908"
    )
    html = """
        <a href="/POxy-bw/72dpi/P.Oxy.XVI.1908.jpg">
          <img src="/POxy-bw/th/P.Oxy.XVI.1908.jpg">
        </a>
        <a href="/POxy-bw/150dpi/P.Oxy.XVI.1908.jpg">150 dpi image (b/w)</a>
        <a href="/POxy-bw/300dpi/P.Oxy.XVI.1908.jpg">
          300 dpi image (b/w)
        </a>
        <a href="/POxy-bw/300dpi/P.Oxy.XVI.1908.jpg">
          300 dpi image (b/w)
        </a>
        <a href="https://example.com/external.jpg">300 dpi image (b/w)</a>
        <a href="/not-an-image">300 dpi image (b/w)</a>
    """

    assert CairoMuseumScraper._image_urls(html, page_url) == [
        "http://ipap.csad.ox.ac.uk/POxy-bw/300dpi/P.Oxy.XVI.1908.jpg"
    ]


def test_cairo_museum_scraper_downloads_record_images(tmp_path, monkeypatch):
    source_url = (
        "http://ipap.csad.ox.ac.uk/4DLink4/4DACTION/IPAPwebquery"
        "?vPub=P.Oxy.&vVol=16&vNum=1908"
    )
    page_url = source_url.replace("http://", "https://")
    recto_url = "https://ipap.csad.ox.ac.uk/POxy-bw/300dpi/P.Oxy.XVI.1908.jpg"
    verso_url = "https://ipap.csad.ox.ac.uk/POxy-bw/300dpi/P.Oxy.XVI.1908%20v.jpg"
    html = f"""
        <a href="/POxy-bw/72dpi/P.Oxy.XVI.1908.jpg">72 dpi image (b/w)</a>
        <a href="{recto_url}">300 dpi image (b/w)</a>
        <a href="/POxy-bw/300dpi/P.Oxy.XVI.1908%20v.jpg">
          300 dpi image (b/w)
        </a>
    """
    responses = {
        source_url: FakeResponse(page_url, text=html),
        recto_url: FakeResponse(recto_url, chunks=(b"recto ", b"image")),
        verso_url: FakeResponse(verso_url, chunks=(b"verso image",)),
    }
    session = FakeSession(responses)
    monkeypatch.setattr(
        "scrapyrus.scrapers.cairo_museum.requests.Session", lambda: session
    )

    CairoMuseumScraper().download(source_url, tmp_path)

    assert (tmp_path / "P.Oxy.XVI.1908.jpg").read_bytes() == b"recto image"
    assert (tmp_path / "P.Oxy.XVI.1908 v.jpg").read_bytes() == b"verso image"
    assert session.requests == [
        (source_url, {"timeout": 30}),
        (recto_url, {"timeout": 30, "stream": True}),
        (verso_url, {"timeout": 30, "stream": True}),
    ]


def test_cairo_museum_scraper_downloads_direct_image(tmp_path, monkeypatch):
    image_url = "http://ipap.csad.ox.ac.uk/Enteuxeis-bw/300dpi/P.Enteux.34r.jpg"
    session = FakeSession(
        {image_url: FakeResponse(image_url, chunks=(b"direct ", b"image"))}
    )
    monkeypatch.setattr(
        "scrapyrus.scrapers.cairo_museum.requests.Session", lambda: session
    )

    CairoMuseumScraper().download(image_url, tmp_path)

    assert (tmp_path / "P.Enteux.34r.jpg").read_bytes() == b"direct image"
    assert session.requests == [(image_url, {"timeout": 30, "stream": True})]
