from pathlib import Path

from scrapyrus.images import (
    REPORT_CATEGORIES,
    REPORT_COLORS,
    REPORT_WIDTH,
    ImageScraperBase,
    RateLimitedMixin,
    _normalized_widths,
    _read_broken_image_entries,
    image_log_file,
    scrape_images,
)
from scrapyrus.scrapers.doi import DOIScraper
from scrapyrus.scrapers.oxford import OxfordScraper


def write_metadata(path: Path, urls: list[str]) -> None:
    graphics = "".join(f'<graphic url="{url}" />' for url in urls)
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        f"<text><body><div><p><figure>{graphics}</figure></p></div></body></text>"
        "</TEI>",
        encoding="utf-8",
    )


def test_read_broken_image_entries_ignores_blank_and_comment_lines(tmp_path):
    broken = tmp_path / "broken.txt"
    broken.write_text(
        "\n"
        "# Entries below are known to be broken\n"
        "42: https://images.example/recto\n"
        "   \n"
        "#43: https://images.example/commented-out\n"
        "44: https://images.example/verso\n",
        encoding="utf-8",
    )

    assert _read_broken_image_entries(broken) == {
        "42: https://images.example/recto",
        "44: https://images.example/verso",
    }


def test_normalized_widths_keep_every_nonzero_category_visible():
    widths = _normalized_widths([10_000, 1, 0, 1, 1], width=10)

    assert widths == [7, 1, 0, 1, 1]
    assert sum(widths) == 10


def test_image_scraper_subclasses_register_in_definition_order(monkeypatch):
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FirstScraper(ImageScraperBase):
        pass

    class SecondScraper(ImageScraperBase):
        pass

    assert ImageScraperBase.registered_scrapers() == (FirstScraper, SecondScraper)


def test_rate_limited_mixin_marks_scraper_unavailable():
    class Scraper(RateLimitedMixin, ImageScraperBase, register=False):
        pass

    scraper = Scraper()

    assert scraper.available()
    scraper.mark_rate_limited()
    assert not scraper.available()
    assert Scraper().available()


def test_rate_limited_mixin_paces_requests(monkeypatch):
    class Scraper(RateLimitedMixin, ImageScraperBase, register=False):
        pass

    monotonic_times = iter([10.0, 10.25, 11.0])
    sleep_calls = []
    monkeypatch.setattr(
        "scrapyrus.images.time.monotonic", lambda: next(monotonic_times)
    )
    monkeypatch.setattr("scrapyrus.images.time.sleep", sleep_calls.append)
    scraper = Scraper()

    scraper.wait_for_request_slot()
    scraper.wait_for_request_slot()

    assert sleep_calls == [0.75]


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
    unavailable = Path("unavailable.txt")
    scrape_images(
        output,
        todo,
        error,
        unavailable,
        idp_data=tmp_path / "idp.data",
    )

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
    assert unavailable.read_text(encoding="utf-8") == ""
    assert not (output / "todo.txt").exists()


def test_scrape_images_resolves_doi_and_restarts_responsibility_chain(
    tmp_path, monkeypatch
):
    source_url = "https://doi.org/10.1234/example"
    resolved_url = "https://known.example/recto"
    metadata = tmp_path / "42.xml"
    write_metadata(metadata, [source_url])
    events = []

    def triples():
        events.append("iterating")
        yield "42", metadata, None, None
        events.append("iteration complete")

    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: triples(),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    downloaded_urls = []

    class DestinationScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url.startswith("https://known.example/")

        def download(self, url: str, target: Path) -> None:
            events.append("download")
            downloaded_urls.append(url)
            (target / "image").write_text(url, encoding="utf-8")

    monkeypatch.setattr(
        ImageScraperBase,
        "_scrapers",
        [DOIScraper, DestinationScraper],
    )

    class FakeResponse:
        url = resolved_url

        def raise_for_status(self) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            pass

    def resolve_doi(url, **kwargs):
        events.append("resolve DOI")
        return FakeResponse()

    monkeypatch.setattr("scrapyrus.scrapers.doi.requests.get", resolve_doi)

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"
    unavailable = tmp_path / "unavailable.txt"
    scrape_images(output, todo, error, unavailable)

    assert downloaded_urls == [resolved_url]
    assert events == ["iterating", "iteration complete", "resolve DOI", "download"]
    assert (output / "42" / "image").read_text(encoding="utf-8") == resolved_url
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_routes_resolved_oxford_doi_to_oxford_scraper(
    tmp_path, monkeypatch
):
    source_url = "https://doi.org/10.25446/oxford.21180640"
    resolved_url = (
        "https://portal.sds.ox.ac.uk/articles/online_resource/"
        "P_Oxy_LXXIV_4991_Census_Declaration/21180640"
    )
    metadata = tmp_path / "128296.xml"
    write_metadata(metadata, [source_url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("128296", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [DOIScraper, OxfordScraper])

    class FakeDOIResponse:
        url = resolved_url

        def raise_for_status(self) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            pass

    monkeypatch.setattr(
        "scrapyrus.scrapers.doi.requests.get",
        lambda url, **kwargs: FakeDOIResponse(),
    )
    downloaded_urls = []

    def download(scraper, url, target):
        downloaded_urls.append(url)
        (target / "image.jpg").write_bytes(b"image")

    monkeypatch.setattr(OxfordScraper, "download", download)

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"
    scrape_images(
        output,
        todo,
        error,
        tmp_path / "unavailable.txt",
    )

    assert downloaded_urls == [resolved_url]
    assert (output / "128296" / "image.jpg").read_bytes() == b"image"
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_writes_unsupported_resolved_doi_url_to_todo(
    tmp_path, monkeypatch
):
    source_url = "https://doi.org/10.1234/example"
    resolved_url = "https://unsupported.example/record/42"
    metadata = tmp_path / "42.xml"
    write_metadata(metadata, [source_url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [DOIScraper])

    class FakeResponse:
        url = resolved_url

        def raise_for_status(self) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            pass

    monkeypatch.setattr(
        "scrapyrus.scrapers.doi.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )

    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"
    scrape_images(
        tmp_path / "images",
        todo,
        error,
        tmp_path / "unavailable.txt",
    )

    assert todo.read_text(encoding="utf-8") == f"42: {resolved_url}\n"
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_writes_failed_resolved_doi_url_to_error(tmp_path, monkeypatch):
    source_url = "https://doi.org/10.1234/example"
    resolved_url = "https://failing.example/record/42"
    metadata = tmp_path / "42.xml"
    write_metadata(metadata, [source_url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FailingScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url.startswith("https://failing.example/")

        def download(self, url: str, target: Path) -> None:
            raise RuntimeError("download failed")

    monkeypatch.setattr(ImageScraperBase, "_scrapers", [DOIScraper, FailingScraper])

    class FakeResponse:
        url = resolved_url

        def raise_for_status(self) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            pass

    monkeypatch.setattr(
        "scrapyrus.scrapers.doi.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )

    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"
    scrape_images(
        tmp_path / "images",
        todo,
        error,
        tmp_path / "unavailable.txt",
    )

    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == f"42: {resolved_url}\n"


def test_scrape_images_reports_url_resolution_cycles_as_errors(
    tmp_path,
    monkeypatch,
):
    first_url = "https://first.example/record/42"
    second_url = "https://second.example/record/42"
    metadata = tmp_path / "42.xml"
    write_metadata(metadata, [first_url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FirstResolver(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url == first_url

        def resolve(self, url: str) -> str:
            return second_url

    class SecondResolver(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url == second_url

        def resolve(self, url: str) -> str:
            return first_url

    error = tmp_path / "error.txt"
    scrape_images(
        tmp_path / "images",
        tmp_path / "todo.txt",
        error,
        tmp_path / "unavailable.txt",
    )

    assert error.read_text(encoding="utf-8") == f"42: {first_url}\n"


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
    unavailable = tmp_path / "unavailable.txt"
    unavailable.write_text("stale entry\n", encoding="utf-8")

    scrape_images(output, todo, error, unavailable)

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
    assert unavailable.read_text(encoding="utf-8") == ""


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
            (target / url.rpartition("/")[2]).write_text(url, encoding="utf-8")

    scrape_images(
        tmp_path / "images",
        tmp_path / "todo.txt",
        tmp_path / "error.txt",
        tmp_path / "unavailable.txt",
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
    unavailable = tmp_path / "unavailable.txt"

    scrape_images(output, todo, error, unavailable)

    assert downloads == []
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""
    assert unavailable.read_text(encoding="utf-8") == ""


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
    unavailable = tmp_path / "unavailable.txt"

    scrape_images(output, todo, error, unavailable)

    assert events == [("responsible", url), ("available", None)]
    assert not (output / "42").exists()
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""
    assert unavailable.read_text(encoding="utf-8") == f"42: {url}\n"


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

    class RateLimitedScraper(RateLimitedMixin, ImageScraperBase):
        def responsible(self, url: str) -> bool:
            events.append(("responsible", url))
            return True

        def download(self, url: str, target: Path) -> None:
            events.append(("download", url))
            (target / "image").write_text(url, encoding="utf-8")
            self.mark_rate_limited()

    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"
    unavailable = tmp_path / "unavailable.txt"
    scrape_images(tmp_path / "images", todo, error, unavailable)

    assert events == [
        ("responsible", urls[0]),
        ("responsible", urls[1]),
        ("download", urls[0]),
    ]
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""
    assert unavailable.read_text(encoding="utf-8") == f"42: {urls[1]}\n"


def test_scrape_images_writes_download_failures_to_error_file(
    tmp_path,
    monkeypatch,
    capsys,
):
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
    unavailable = tmp_path / "unavailable.txt"
    log = tmp_path / "images.log"

    with image_log_file(log, "ERROR"):
        scrape_images(output, todo, error, unavailable)

    assert not (output / "42").exists()
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == f"42: {url}\n"
    assert unavailable.read_text(encoding="utf-8") == ""
    log_text = log.read_text(encoding="utf-8")
    assert f"Image download failed for TM 42 with FailingScraper: {url}" in log_text
    assert "RuntimeError: download failed" in log_text
    captured = capsys.readouterr()
    assert "RuntimeError: download failed" not in captured.out + captured.err


def test_scrape_images_reports_downloads_without_images_as_errors(
    tmp_path,
    monkeypatch,
):
    metadata = tmp_path / "42.xml"
    url = "https://images.example/recto"
    write_metadata(metadata, [url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class EmptyScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, url: str, target: Path) -> None:
            pass

    output = tmp_path / "images"
    error = tmp_path / "error.txt"
    log = tmp_path / "images.log"

    with image_log_file(log, "ERROR"):
        scrape_images(
            output,
            tmp_path / "todo.txt",
            error,
            tmp_path / "unavailable.txt",
        )

    assert not (output / "42").exists()
    assert error.read_text(encoding="utf-8") == f"42: {url}\n"
    assert "EmptyScraper.download did not write any images" in log.read_text(
        encoding="utf-8"
    )


def test_scrape_images_skips_known_broken_urls_and_overwrites_error_file(
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

    broken = tmp_path / "broken.txt"
    broken.write_text(f"42: {skipped_url}", encoding="utf-8")
    error = tmp_path / "error.txt"
    error.write_text("stale error\n", encoding="utf-8")

    scrape_images(
        tmp_path / "images",
        tmp_path / "todo.txt",
        error,
        tmp_path / "unavailable.txt",
        broken_filename=broken,
    )

    assert attempted_urls == [skipped_url, failing_url]
    assert broken.read_text(encoding="utf-8") == f"42: {skipped_url}"
    assert error.read_text(encoding="utf-8") == f"42: {failing_url}\n"


def test_scrape_images_prints_normalized_stacked_outcome_chart(
    tmp_path, monkeypatch, capsys
):
    metadata_paths = []
    for tm_id, urls in (
        ("existing", ["https://images.example/recto", "https://images.example/verso"]),
        ("downloaded", ["https://images.example/success"]),
        ("unsupported", ["https://unsupported.example/image"]),
        ("unavailable", ["https://unavailable.example/image"]),
        ("failed", ["https://images.example/failure"]),
        ("broken", ["https://images.example/broken"]),
    ):
        metadata = tmp_path / f"{tm_id}.xml"
        write_metadata(metadata, urls)
        metadata_paths.append((tm_id, metadata, None, None))

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
            (target / "image").write_text(url, encoding="utf-8")

    output = tmp_path / "images"
    (output / "existing").mkdir(parents=True)
    broken = tmp_path / "broken.txt"
    broken.write_text(
        "broken: https://images.example/broken\n",
        encoding="utf-8",
    )

    unavailable = tmp_path / "unavailable.txt"
    scrape_images(
        output,
        tmp_path / "todo.txt",
        tmp_path / "error.txt",
        unavailable,
        broken_filename=broken,
    )

    output_lines = capsys.readouterr().out.splitlines()
    legend, _, scraper_row, unavailable_row = output_lines

    for category, color in zip(REPORT_CATEGORIES, REPORT_COLORS):
        assert f"\033[{color}m▇ {category} \033[0m" in legend

    assert scraper_row.count("▇") == REPORT_WIDTH
    assert scraper_row.endswith(" 5")
    for color, segment_width in zip(REPORT_COLORS, [20, 10, 0, 10, 10]):
        if segment_width:
            assert f"\033[{color}m{'▇' * segment_width}\033[0m" in scraper_row

    assert unavailable_row.count("▇") == REPORT_WIDTH
    assert unavailable_row.endswith(" 1")
    assert f"\033[{REPORT_COLORS[2]}m{'▇' * REPORT_WIDTH}\033[0m" in unavailable_row
    assert unavailable.read_text(encoding="utf-8") == (
        "unavailable: https://unavailable.example/image\n"
    )
