import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.egnet")


class EgnetScraper(ImageScraperBase):
    """Download vignette images from IFAO Egnet publication records."""

    HOST = "www.ifao.egnet.net"
    RECORD_PATH = "/bases/publications/fifao81/"
    IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
    REQUEST_TIMEOUT = 30

    @classmethod
    def _identifier(cls, url: str) -> str:
        parsed_url = urlparse(url)
        identifiers = parse_qs(parsed_url.query).get("id", [])
        if (
            parsed_url.path.rstrip("/") != cls.RECORD_PATH.rstrip("/")
            or len(identifiers) != 1
            or cls.IDENTIFIER_PATTERN.fullmatch(identifiers[0]) is None
        ):
            raise ValueError(f"Unsupported Egnet record URL: {url}")
        return identifiers[0]

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        if not (
            parsed_url.scheme in {"http", "https"} and parsed_url.hostname == self.HOST
        ):
            return False

        try:
            self._identifier(url)
        except ValueError:
            return False
        return True

    @classmethod
    def _image_url(cls, url: str) -> str:
        parsed_url = urlparse(url)
        identifier = cls._identifier(url)
        return urlunparse(
            parsed_url._replace(
                path=f"{cls.RECORD_PATH}docs/vignettes/{identifier}.jpg",
                query="",
                fragment="",
            )
        )

    def download(self, url: str, target: Path) -> None:
        image_url = self._image_url(url)
        filename = Path(urlparse(image_url).path).name

        logger.info("Downloading Egnet image: %s", image_url)
        with requests.get(
            image_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            with (target / filename).open("wb") as image_file:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)
        logger.info("Completed Egnet image: %s", image_url)
