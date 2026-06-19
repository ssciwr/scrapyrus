from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from xml.etree import ElementTree

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

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
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


def scrape_images(
    target: Path,
    todo_filename: str | Path,
    *,
    idp_data: str | Path = Path("idp.data"),
) -> None:
    """Download images referenced by all HGV metadata records.

    Each HGV record is downloaded into its own directory below *target*.
    Unknown image sources are written to *todo_filename*, one per line in
    ``HGV_ID: URL`` form. Existing HGV directories are left untouched.
    """

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)

    with todo_path.open("w", encoding="utf-8") as todo_file:
        for hgv_id, metadata, _, _ in iterate_hgv_triples(idp_data):
            root = ElementTree.parse(metadata).getroot()
            graphics = root.findall(
                GRAPHIC_PATH,
                namespaces={"tei": TEI_NAMESPACE},
            )
            papyrus_target = target / hgv_id
            if graphics and papyrus_target.exists():
                continue

            for graphic in graphics:
                url = graphic.get("url")
                if not url:
                    continue

                for scraper_type in ImageScraperBase.registered_scrapers():
                    scraper = scraper_type(url)
                    if scraper.responsible(url):
                        papyrus_target.mkdir(parents=True, exist_ok=True)
                        scraper.download(papyrus_target)
                        break
                else:
                    todo_file.write(f"{hgv_id}: {url}\n")
