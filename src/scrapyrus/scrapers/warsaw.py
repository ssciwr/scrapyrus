import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.warsaw")


class WarsawScraper(ImageScraperBase):
    """Download images from University of Warsaw papyrus record URLs."""

    HOST = "www.papyrology.uw.edu.pl"
    RECORD_PATH_PATTERN = re.compile(r"^/papyri/[^/]+\.htm$")
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and not parsed_url.params
            and self.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _image_url(cls, record_url: str) -> str:
        parsed_url = urlparse(record_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or parsed_url.hostname != cls.HOST
            or parsed_url.params
            or cls.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is None
        ):
            raise ValueError(f"Unexpected Warsaw papyrus record URL: {record_url}")

        return urlunparse(
            (
                "https",
                cls.HOST,
                parsed_url.path.removesuffix(".htm") + ".jpg",
                "",
                "",
                "",
            )
        )

    def download(self, url: str, target: Path) -> None:
        image_url = self._image_url(url)
        filename = Path(unquote(urlparse(image_url).path)).name
        logger.info("Downloading Warsaw papyrus image: %s", image_url)
        with requests.get(
            image_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as image_response:
            image_response.raise_for_status()
            with (target / filename).open("wb") as image_file:
                for chunk in image_response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)
        logger.info("Completed Warsaw papyrus record: %s", url)
