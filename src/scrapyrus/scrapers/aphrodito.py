import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.aphrodito")


class AphroditoScraper(ImageScraperBase):
    """Download images from the Aphrodito papyrus database."""

    HOST = "bipab.aphrodito.info"
    PAGE_PATH_PATTERN = re.compile(r"^/pages_html/(?P<identifier>[^/]+)\.html$")
    IMAGE_DIRECTORY = "/images/grandes_images"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.PAGE_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _image_url(cls, url: str) -> str:
        parsed_url = urlparse(url)
        match = cls.PAGE_PATH_PATTERN.fullmatch(parsed_url.path)
        if match is None:
            raise ValueError(f"Unsupported Aphrodito record URL: {url}")

        identifier = match.group("identifier")
        return urlunparse(
            parsed_url._replace(
                path=f"{cls.IMAGE_DIRECTORY}/{identifier}.jpg",
                query="",
                fragment="",
            )
        )

    def download(self, url: str, target: Path) -> None:
        image_url = self._image_url(url)
        filename = Path(unquote(urlparse(image_url).path)).name
        if not filename:
            raise ValueError(f"Aphrodito image URL has no filename: {image_url}")

        logger.info("Downloading Aphrodito image: %s", image_url)
        with requests.get(
            image_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            with (target / filename).open("wb") as image_file:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)
        logger.info("Completed Aphrodito image: %s", image_url)
