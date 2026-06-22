import logging
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.cairo_museum")


class CairoMuseumScraper(ImageScraperBase):
    """Download 300 dpi images from Cairo Museum photographic archive records."""

    HOST = "ipap.csad.ox.ac.uk"
    RECORD_PATH = "/4DLink4/4DACTION/IPAPwebquery"
    DOWNLOAD_LABEL = "300 dpi image (b/w)"
    IMAGE_SUFFIXES = frozenset(
        {".bmp", ".gif", ".jp2", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
    )
    REQUEST_TIMEOUT = 30

    @classmethod
    def _is_image_url(cls, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == cls.HOST
            and Path(parsed_url.path).suffix.lower() in cls.IMAGE_SUFFIXES
        )

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and (
                parsed_url.path.rstrip("/") == self.RECORD_PATH
                or self._is_image_url(url)
            )
        )

    @classmethod
    def _image_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        image_urls = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            label = link.get_text(" ", strip=True)
            if label.casefold() != cls.DOWNLOAD_LABEL.casefold():
                continue

            image_url = urljoin(page_url, link["href"])
            if not cls._is_image_url(image_url) or image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            image_urls.append(image_url)

        return image_urls

    @staticmethod
    def _filename(image_url: str) -> str:
        filename = Path(unquote(urlparse(image_url).path)).name
        if not filename:
            raise ValueError(f"Cairo Museum image URL has no filename: {image_url}")
        return filename

    def _download_image(
        self,
        session: requests.Session,
        image_url: str,
        target: Path,
    ) -> None:
        filename = self._filename(image_url)
        logger.debug("Downloading Cairo Museum image to %s: %s", filename, image_url)
        with session.get(
            image_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as image_response:
            image_response.raise_for_status()
            with (target / filename).open("wb") as image_file:
                for chunk in image_response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)

    def download(self, url: str, target: Path) -> None:
        with requests.Session() as session:
            if self._is_image_url(url):
                self._download_image(session, url, target)
                logger.info("Downloaded direct Cairo Museum image: %s", url)
                return

            logger.info("Fetching Cairo Museum record: %s", url)
            page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
            page_response.raise_for_status()
            page_url = page_response.url or url
            image_urls = self._image_urls(page_response.text, page_url)
            logger.info(
                "Cairo Museum record contains %d 300 dpi image(s): %s",
                len(image_urls),
                page_url,
            )

            for image_url in image_urls:
                self._download_image(session, image_url, target)

        logger.info("Completed Cairo Museum record: %s", url)
