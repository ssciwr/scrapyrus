from scrapyrus.scrapers.psi_online import PSIOnlineScraper


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


def test_psi_online_scraper_responsibility():
    scraper = PSIOnlineScraper()

    assert scraper.responsible("https://psi-online.it/documents/psi-congrxvii-14")
    assert scraper.responsible("http://www.psi-online.it/documents/psi;4;439")
    assert not scraper.responsible(
        "https://psi-online.it/documents/download?filen=PSI_inv.15_r.jpg"
    )
    assert not scraper.responsible("https://psi-online.it/documents/")
    assert not scraper.responsible(
        "https://psi-online.it.example/documents/psi-congrxvii-14"
    )
    assert not scraper.responsible("https://psi-online.it/search")


def test_psi_online_scraper_extracts_download_links():
    page_url = "https://psi-online.it/documents/pflor;3;388"
    html = """
        <a href="/images/orig/P.Flor.388%20I-IVr.jpg">original preview</a>
        <a href="/documents/download?filen=P.Flor.388%20I-IVr.jpg">recto</a>
        <a href="https://psi-online.it/documents/download?filen=P.Flor.388%20I-IVv.jpg">
            verso
        </a>
        <a href="/documents/download?filen=P.Flor.388%20I-IVr.jpg">duplicate</a>
        <a href="https://example.com/documents/download?filen=external.jpg">
            external
        </a>
        <a href="/documents/download">missing filename</a>
    """

    assert PSIOnlineScraper._download_urls(html, page_url) == [
        "https://psi-online.it/documents/download?filen=P.Flor.388%20I-IVr.jpg",
        "https://psi-online.it/documents/download?filen=P.Flor.388%20I-IVv.jpg",
    ]


def test_psi_online_scraper_downloads_all_images(tmp_path, monkeypatch):
    source_url = "http://www.psi-online.it/documents/psi-congrxvii-14"
    page_url = "https://psi-online.it/documents/psi-congrxvii-14"
    recto_url = "https://psi-online.it/documents/download?filen=PSI_inv.15_r.jpg"
    verso_url = (
        "https://psi-online.it/documents/download?filen=PSI_inv.15_v%20large.jpg"
    )
    html = f"""
        <p>
          <a href="/images/orig/PSI_inv.15_r.jpg">thumbnail link</a>
          <a href="{recto_url}">PSI_inv.15_r.jpg</a>
        </p>
        <p><a href="{verso_url}">PSI_inv.15_v large.jpg</a></p>
    """
    responses = {
        source_url: FakeResponse(page_url, text=html),
        recto_url: FakeResponse(recto_url, chunks=(b"recto ", b"image")),
        verso_url: FakeResponse(verso_url, chunks=(b"verso image",)),
    }
    session = FakeSession(responses)
    monkeypatch.setattr(
        "scrapyrus.scrapers.psi_online.requests.Session",
        lambda: session,
    )

    PSIOnlineScraper().download(source_url, tmp_path)

    assert (tmp_path / "PSI_inv.15_r.jpg").read_bytes() == b"recto image"
    assert (tmp_path / "PSI_inv.15_v large.jpg").read_bytes() == b"verso image"
    assert session.requests == [
        (source_url, {"timeout": 30}),
        (recto_url, {"timeout": 30, "stream": True}),
        (verso_url, {"timeout": 30, "stream": True}),
    ]
