from scrapyrus.scrapers.berlpap import BerlPapScraper


def test_berlpap_scraper_responsibility():
    scraper = BerlPapScraper("https://berlpap.smb.museum/00312/")

    assert scraper.responsible("https://berlpap.smb.museum/00312/")
    assert scraper.responsible("http://berlpap.smb.museum/00312/")
    assert not scraper.responsible("https://berlpap.smb.museum.example/00312/")
    assert not scraper.responsible("https://example.com/00312/")


def test_berlpap_scraper_downloads_deduplicated_original_images(tmp_path, monkeypatch):
    page_url = "https://berlpap.smb.museum/00312/"
    recto_url = "https://berlpap.smb.museum/Original/P_25014_R_4_001.jpg"
    verso_url = "https://berlpap.smb.museum/Original/P_25014_V_4_001.jpg"
    html = f"""
        <table><tr><td><img src="/unrelated.jpg" /></td></tr></table>
        <table>
            <tr><td><b>Digitalisate</b>:</td></tr>
            <tr><td><a href="{recto_url}">521 dpi</a></td></tr>
            <tr><td><a href="{recto_url}">preview</a></td></tr>
            <tr><td><a href="/Original/P_25014_V_4_001.jpg">516 dpi</a></td></tr>
            <tr><td><a href="https://dfg-viewer.de/example">DFG</a></td></tr>
        </table>
    """

    class FakeResponse:
        def __init__(self, *, text="", chunks=()):
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

    responses = {
        page_url: FakeResponse(text=html),
        recto_url: FakeResponse(chunks=(b"recto ", b"image")),
        verso_url: FakeResponse(chunks=(b"verso image",)),
    }
    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return responses[url]

    monkeypatch.setattr("scrapyrus.scrapers.berlpap.requests.get", fake_get)

    BerlPapScraper(page_url).download(tmp_path)

    assert (tmp_path / "P_25014_R_4_001.jpg").read_bytes() == b"recto image"
    assert (tmp_path / "P_25014_V_4_001.jpg").read_bytes() == b"verso image"
    assert requests == [
        (page_url, {"timeout": 30}),
        (recto_url, {"timeout": 30, "stream": True}),
        (verso_url, {"timeout": 30, "stream": True}),
    ]


def test_berlpap_scraper_handles_page_without_digitalisate(tmp_path, monkeypatch):
    class FakeResponse:
        text = "<html><body>No images</body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "scrapyrus.scrapers.berlpap.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )

    BerlPapScraper("https://berlpap.smb.museum/00313/").download(tmp_path)

    assert list(tmp_path.iterdir()) == []
