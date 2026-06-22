from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from xml.etree import ElementTree

from tqdm import tqdm

from scrapyrus.hgv import iterate_hgv_triples


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
GRAPHIC_PATH = "./tei:text/tei:body/tei:div/tei:p/tei:figure/tei:graphic"


class RateLimitedMixin:
    """Track whether an image scraper encountered a rate limit."""

    _rate_limited = False

    def mark_rate_limited(self) -> None:
        """Make this scraper unavailable for the remainder of the run."""

        self._rate_limited = True

    def available(self) -> bool:
        """Return whether this scraper has not encountered a rate limit."""

        return not self._rate_limited


class ImageScraperBase:
    """Base class for image scrapers selected by source URL.

    Subclasses are registered in definition order. :func:`scrape_images`
    creates one instance of each registered subclass for the duration of a
    run, allowing scraper implementations to retain state between downloads.
    """

    _scrapers: ClassVar[list[type[ImageScraperBase]]] = []

    def __init_subclass__(
        cls,
        *,
        register: bool = True,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if register:
            ImageScraperBase._scrapers.append(cls)

    @classmethod
    def registered_scrapers(cls) -> tuple[type[ImageScraperBase], ...]:
        """Return registered scraper classes in responsibility-chain order."""

        return tuple(cls._scrapers)

    def responsible(self, url: str) -> bool:
        """Return whether this scraper can handle *url*."""

        raise NotImplementedError

    def available(self) -> bool:
        """Return whether this scraper is currently able to download images."""

        return True

    def download(self, url: str, target: Path) -> None:
        """Download images referenced by *url* into *target*."""

        raise NotImplementedError


@dataclass(frozen=True)
class _ImageDownload:
    hgv_id: str
    url: str
    target: Path
    scraper: ImageScraperBase


def scrape_images(
    target: Path,
    todo_filename: str | Path,
    error_filename: str | Path,
    *,
    idp_data: str | Path = Path("idp.data"),
) -> None:
    """Download images referenced by all HGV metadata records.

    Each HGV record is downloaded into its own directory below *target*.
    Unknown image sources are written to *todo_filename*, one per line in
    ``HGV_ID: URL`` form. Sources whose download fails are written in the same
    form to *error_filename*. Sources already listed there are not retried.
    Temporarily unavailable sources are skipped without being written to
    either file. Existing HGV directories are left untouched. A summary of
    scraped, skipped, and failed image references is printed after processing.
    """

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)
    error_path = Path(error_filename)
    existing_error_text = (
        error_path.read_text(encoding="utf-8") if error_path.exists() else ""
    )
    existing_errors = set(existing_error_text.splitlines())
    error_separator = (
        "\n"
        if existing_error_text and not existing_error_text.endswith(("\n", "\r"))
        else ""
    )
    scraped_count = 0
    existing_count = 0
    no_responsible_scraper_count = 0
    unavailable_scraper_count = 0
    error_count = 0
    downloads: list[_ImageDownload] = []
    scrapers = tuple(
        scraper_type() for scraper_type in ImageScraperBase.registered_scrapers()
    )

    with (
        todo_path.open("w", encoding="utf-8") as todo_file,
        error_path.open("a", encoding="utf-8") as error_file,
    ):
        for hgv_id, metadata, _, _ in iterate_hgv_triples(idp_data):
            root = ElementTree.parse(metadata).getroot()
            graphics = root.findall(
                GRAPHIC_PATH,
                namespaces={"tei": TEI_NAMESPACE},
            )
            papyrus_target = target / hgv_id
            if graphics and papyrus_target.exists():
                existing_count += len(graphics)
                continue

            for graphic in graphics:
                url = graphic.get("url")
                if not url:
                    continue
                error_entry = f"{hgv_id}: {url}"
                if error_entry in existing_errors:
                    continue

                for scraper in scrapers:
                    if scraper.responsible(url):
                        downloads.append(
                            _ImageDownload(hgv_id, url, papyrus_target, scraper)
                        )
                        break
                else:
                    no_responsible_scraper_count += 1
                    todo_file.write(f"{hgv_id}: {url}\n")

        for download in tqdm(
            downloads,
            total=len(downloads),
            unit="image",
            desc="Downloading images",
        ):
            if not download.scraper.available():
                unavailable_scraper_count += 1
                continue
            download.target.mkdir(parents=True, exist_ok=True)
            try:
                download.scraper.download(download.url, download.target)
            except Exception:
                try:
                    download.target.rmdir()
                except OSError:
                    pass
                error_count += 1
                error_file.write(
                    f"{error_separator}{download.hgv_id}: {download.url}\n"
                )
                error_separator = ""
            else:
                scraped_count += 1

    print(
        f"Images scraped: {scraped_count}; "
        f"skipped because they exist: {existing_count}; "
        "skipped because no scraper was responsible: "
        f"{no_responsible_scraper_count}; "
        "skipped because the responsible scraper was unavailable: "
        f"{unavailable_scraper_count}; "
        f"errors: {error_count}"
    )


# Import built-in scrapers after defining the base class so subclasses register.
from scrapyrus import scrapers as _scrapers  # noqa: E402, F401
