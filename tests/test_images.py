from pathlib import Path

from scrapyrus.images import BerlPapScraper, ImageScraperBase, scrape_images


def write_metadata(path: Path, urls: list[str]) -> None:
    graphics = "".join(f'<graphic url="{url}" />' for url in urls)
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        f"<text><body><div><p><figure>{graphics}</figure></p></div></body></text>"
        "</TEI>",
        encoding="utf-8",
    )


def test_image_scraper_subclasses_register_in_definition_order(monkeypatch):
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FirstScraper(ImageScraperBase):
        pass

    class SecondScraper(ImageScraperBase):
        pass

    assert ImageScraperBase.registered_scrapers() == (FirstScraper, SecondScraper)


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

    monkeypatch.setattr("scrapyrus.images.requests.get", fake_get)

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
        "scrapyrus.images.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )

    BerlPapScraper("https://berlpap.smb.museum/00313/").download(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_scrape_images_uses_responsibility_chain_and_writes_todo(tmp_path, monkeypatch):
    metadata_without_image = tmp_path / "1.xml"
    write_metadata(metadata_without_image, [])
    known_metadata = tmp_path / "2.xml"
    write_metadata(known_metadata, ["https://known.example/recto"])
    unknown_metadata = tmp_path / "3.xml"
    write_metadata(unknown_metadata, ["https://unknown.example/verso"])

    triples = [
        ("1", metadata_without_image, None, None),
        ("2", known_metadata, None, None),
        ("3", unknown_metadata, None, None),
    ]
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples", lambda idp_data: iter(triples)
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    checked_urls = []

    class KnownScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            checked_urls.append(url)
            return url.startswith("https://known.example/")

        def download(self, target: Path) -> None:
            (target / "image").write_text(self.url, encoding="utf-8")

    output = tmp_path / "images"
    monkeypatch.chdir(tmp_path)
    todo = Path("todo.txt")
    error = Path("error.txt")
    scrape_images(output, todo, error, idp_data=tmp_path / "idp.data")

    assert (output / "2" / "image").read_text(encoding="utf-8") == (
        "https://known.example/recto"
    )
    assert not (output / "1").exists()
    assert not (output / "3").exists()
    assert checked_urls == [
        "https://known.example/recto",
        "https://unknown.example/verso",
    ]
    assert todo.read_text(encoding="utf-8") == "3: https://unknown.example/verso\n"
    assert error.read_text(encoding="utf-8") == ""
    assert not (output / "todo.txt").exists()


def test_scrape_images_passes_papyrus_directory_for_multiple_images(
    tmp_path, monkeypatch
):
    metadata = tmp_path / "42.xml"
    write_metadata(
        metadata,
        ["https://images.example/recto", "https://images.example/verso"],
    )
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    downloaded = []

    class Scraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, target: Path) -> None:
            downloaded.append((self.url, target))
            filename = self.url.rpartition("/")[2]
            (target / filename).write_text(self.url, encoding="utf-8")

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert downloaded == [
        ("https://images.example/recto", output / "42"),
        ("https://images.example/verso", output / "42"),
    ]
    assert (output / "42" / "recto").read_text(encoding="utf-8") == (
        "https://images.example/recto"
    )
    assert (output / "42" / "verso").read_text(encoding="utf-8") == (
        "https://images.example/verso"
    )
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_skips_existing_papyrus_directory(tmp_path, monkeypatch):
    metadata = tmp_path / "42.xml"
    write_metadata(metadata, ["https://images.example/recto"])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    downloads = []

    class Scraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, target: Path) -> None:
            downloads.append(target)

    output = tmp_path / "images"
    (output / "42").mkdir(parents=True)
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert downloads == []
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_writes_download_failures_to_error_file(tmp_path, monkeypatch):
    metadata = tmp_path / "42.xml"
    url = "https://images.example/recto"
    write_metadata(metadata, [url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FailingScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, target: Path) -> None:
            raise RuntimeError("download failed")

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == f"42: {url}\n"
