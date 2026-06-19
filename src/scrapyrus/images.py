from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from xml.etree import ElementTree

from tqdm import tqdm

from scrapyrus.hgv import iterate_hgv_triples


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
GRAPHIC_PATH = "./tei:text/tei:body/tei:div/tei:p/tei:figure/tei:graphic"


class ImageScraperBase:
    """Base class for image scrapers selected by source URL.

    Subclasses are registered in definition order. A scraper instance retains
    the URL it was created for so its :meth:`download` implementation only
    needs the requested target path.
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

    def __init__(self, url: str) -> None:
        self.url = url

    @classmethod
    def registered_scrapers(cls) -> tuple[type[ImageScraperBase], ...]:
        """Return registered scraper classes in responsibility-chain order."""

        return tuple(cls._scrapers)

    def responsible(self, url: str) -> bool:
        """Return whether this scraper can handle *url*."""

        raise NotImplementedError

    def download(self, target: Path) -> None:
        """Download the image for this scraper's URL into *target*."""

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
    form to *error_filename*. Existing HGV directories are left untouched.
    A summary of scraped, skipped, and failed image references is printed after
    processing.
    """

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)
    error_path = Path(error_filename)
    scraped_count = 0
    existing_count = 0
    no_scraper_count = 0
    error_count = 0
    downloads: list[_ImageDownload] = []

    with (
        todo_path.open("w", encoding="utf-8") as todo_file,
        error_path.open("w", encoding="utf-8") as error_file,
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

                for scraper_type in ImageScraperBase.registered_scrapers():
                    scraper = scraper_type(url)
                    if scraper.responsible(url):
                        downloads.append(
                            _ImageDownload(hgv_id, url, papyrus_target, scraper)
                        )
                        break
                else:
                    no_scraper_count += 1
                    todo_file.write(f"{hgv_id}: {url}\n")

        for download in tqdm(
            downloads,
            total=len(downloads),
            unit="image",
            desc="Downloading images",
        ):
            download.target.mkdir(parents=True, exist_ok=True)
            try:
                download.scraper.download(download.target)
            except Exception:
                try:
                    download.target.rmdir()
                except OSError:
                    pass
                error_count += 1
                error_file.write(f"{download.hgv_id}: {download.url}\n")
            else:
                scraped_count += 1

    print(
        f"Images scraped: {scraped_count}; "
        f"skipped because they exist: {existing_count}; "
        f"skipped because no scraper was available: {no_scraper_count}; "
        f"errors: {error_count}"
    )


# Import built-in scrapers after defining the base class so subclasses register.
from scrapyrus import scrapers as _scrapers  # noqa: E402, F401
