from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

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


class BerlPapScraper(ImageScraperBase):
    """Download full-resolution images from the Berliner Papyrusdatenbank."""

    HOST = "berlpap.smb.museum"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return parsed_url.scheme in {"http", "https"} and parsed_url.netloc == self.HOST

    def _image_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find(
            "b",
            string=lambda text: text is not None and text.strip() == "Digitalisate",
        )
        if heading is None:
            return []

        table = heading.find_parent("table")
        if table is None:
            return []

        image_urls = []
        seen_urls = set()
        for link in table.find_all("a", href=True):
            image_url = urljoin(self.url, link["href"])
            parsed_url = urlparse(image_url)
            if not (
                parsed_url.scheme == "https"
                and parsed_url.netloc == self.HOST
                and parsed_url.path.startswith("/Original/")
            ):
                continue
            if image_url not in seen_urls:
                seen_urls.add(image_url)
                image_urls.append(image_url)
        return image_urls

    def download(self, target: Path) -> None:
        page_response = requests.get(self.url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()

        for image_url in self._image_urls(page_response.text):
            filename = Path(unquote(urlparse(image_url).path)).name
            if not filename:
                continue
            with requests.get(
                image_url,
                timeout=self.REQUEST_TIMEOUT,
                stream=True,
            ) as image_response:
                image_response.raise_for_status()
                with (target / filename).open("wb") as image_file:
                    for chunk in image_response.iter_content(chunk_size=64 * 1024):
                        image_file.write(chunk)


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
    """

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)
    error_path = Path(error_filename)

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
                continue

            for graphic in graphics:
                url = graphic.get("url")
                if not url:
                    continue

                for scraper_type in ImageScraperBase.registered_scrapers():
                    scraper = scraper_type(url)
                    if scraper.responsible(url):
                        papyrus_target.mkdir(parents=True, exist_ok=True)
                        try:
                            scraper.download(papyrus_target)
                        except Exception:
                            error_file.write(f"{hgv_id}: {url}\n")
                        break
                else:
                    todo_file.write(f"{hgv_id}: {url}\n")
