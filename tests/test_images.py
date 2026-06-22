from pathlib import Path

from scrapyrus.images import ImageScraperBase, scrape_images


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

        def download(self, url: str, target: Path) -> None:
            (target / "image").write_text(url, encoding="utf-8")

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

        def download(self, url: str, target: Path) -> None:
            downloaded.append((url, target))
            filename = url.rpartition("/")[2]
            (target / filename).write_text(url, encoding="utf-8")

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


def test_scrape_images_reuses_each_scraper_instance_for_the_full_run(
    tmp_path, monkeypatch
):
    metadata = tmp_path / "42.xml"
    urls = ["https://images.example/recto", "https://images.example/verso"]
    write_metadata(metadata, urls)
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    events = []
    instances = []
    progress = {}

    def fake_tqdm(iterable, *, total, unit, desc):
        progress.update(total=total, unit=unit, desc=desc)
        return iterable

    monkeypatch.setattr("scrapyrus.images.tqdm", fake_tqdm)

    class StatefulScraper(ImageScraperBase):
        def __init__(self):
            self.responsible_urls = []
            self.downloaded_urls = []
            instances.append(self)

        def responsible(self, url: str) -> bool:
            self.responsible_urls.append(url)
            events.append(("responsible", url))
            return True

        def download(self, url: str, target: Path) -> None:
            assert self.responsible_urls == urls
            self.downloaded_urls.append(url)
            events.append(("download", url))

    scrape_images(
        tmp_path / "images",
        tmp_path / "todo.txt",
        tmp_path / "error.txt",
    )

    assert events == [
        ("responsible", urls[0]),
        ("responsible", urls[1]),
        ("download", urls[0]),
        ("download", urls[1]),
    ]
    assert len(instances) == 1
    assert instances[0].downloaded_urls == urls
    assert progress == {
        "total": 2,
        "unit": "image",
        "desc": "Downloading images",
    }


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

        def download(self, url: str, target: Path) -> None:
            downloads.append(target)

    output = tmp_path / "images"
    (output / "42").mkdir(parents=True)
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert downloads == []
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_skips_unavailable_responsible_scraper(tmp_path, monkeypatch):
    metadata = tmp_path / "42.xml"
    url = "https://images.example/recto"
    write_metadata(metadata, [url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    events = []

    class UnavailableScraper(ImageScraperBase):
        def responsible(self, candidate_url: str) -> bool:
            events.append(("responsible", candidate_url))
            return True

        def available(self) -> bool:
            events.append(("available", None))
            return False

        def download(self, url: str, target: Path) -> None:
            raise AssertionError("unavailable scraper must not download")

    class FallbackScraper(ImageScraperBase):
        def responsible(self, candidate_url: str) -> bool:
            raise AssertionError("responsibility must not fall through")

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert events == [("responsible", url), ("available", None)]
    assert not (output / "42").exists()
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_rechecks_stateful_scraper_availability_before_each_download(
    tmp_path, monkeypatch
):
    metadata = tmp_path / "42.xml"
    urls = ["https://images.example/recto", "https://images.example/verso"]
    write_metadata(metadata, urls)
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    events = []

    class RateLimitedScraper(ImageScraperBase):
        def __init__(self):
            self.is_available = True

        def responsible(self, url: str) -> bool:
            events.append(("responsible", url))
            return True

        def available(self) -> bool:
            events.append(("available", self.is_available))
            return self.is_available

        def download(self, url: str, target: Path) -> None:
            events.append(("download", url))
            self.is_available = False

    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"
    scrape_images(tmp_path / "images", todo, error)

    assert events == [
        ("responsible", urls[0]),
        ("responsible", urls[1]),
        ("available", True),
        ("download", urls[0]),
        ("available", False),
    ]
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

        def download(self, url: str, target: Path) -> None:
            raise RuntimeError("download failed")

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert not (output / "42").exists()
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == f"42: {url}\n"


def test_scrape_images_skips_and_preserves_existing_error_entries(
    tmp_path, monkeypatch
):
    metadata = tmp_path / "42.xml"
    skipped_url = "https://images.example/skipped"
    failing_url = "https://images.example/failing"
    write_metadata(metadata, [skipped_url, failing_url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    attempted_urls = []

    class FailingScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            attempted_urls.append(url)
            return True

        def download(self, url: str, target: Path) -> None:
            raise RuntimeError("download failed")

    error = tmp_path / "error.txt"
    error.write_text(f"42: {skipped_url}", encoding="utf-8")

    scrape_images(tmp_path / "images", tmp_path / "todo.txt", error)

    assert attempted_urls == [failing_url]
    assert error.read_text(encoding="utf-8") == (
        f"42: {skipped_url}\n42: {failing_url}\n"
    )


def test_scrape_images_prints_outcome_counts(tmp_path, monkeypatch, capsys):
    metadata_paths = []
    for hgv_id, urls in (
        ("existing", ["https://images.example/recto", "https://images.example/verso"]),
        ("scraped", ["https://images.example/success"]),
        ("unsupported", ["https://unsupported.example/image"]),
        ("unavailable", ["https://unavailable.example/image"]),
        ("failed", ["https://images.example/failure"]),
    ):
        metadata = tmp_path / f"{hgv_id}.xml"
        write_metadata(metadata, urls)
        metadata_paths.append((hgv_id, metadata, None, None))

    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter(metadata_paths),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class UnavailableScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url.startswith("https://unavailable.example/")

        def available(self) -> bool:
            return False

    class Scraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url.startswith("https://images.example/")

        def download(self, url: str, target: Path) -> None:
            if url.endswith("/failure"):
                raise RuntimeError("download failed")

    output = tmp_path / "images"
    (output / "existing").mkdir(parents=True)

    scrape_images(output, tmp_path / "todo.txt", tmp_path / "error.txt")

    assert capsys.readouterr().out == (
        "Images scraped: 1; skipped because they exist: 2; "
        "skipped because no scraper was responsible: 1; "
        "skipped because the responsible scraper was unavailable: 1; "
        "errors: 1\n"
    )
