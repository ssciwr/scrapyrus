import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.louvre")


class LouvreScraper(ImageScraperBase):
    """Download full-resolution images from Louvre collection records."""

    HOST = "collections.louvre.fr"
    RECORD_PATH_PATTERN = re.compile(r"^/(?:[a-z]{2}/)?ark:/53355/cl\d+/?$")
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @staticmethod
    def _json_url(url: str) -> str:
        parsed_url = urlparse(url)
        return urlunparse(
            parsed_url._replace(
                path=parsed_url.path.rstrip("/") + ".json",
                query="",
                fragment="",
            )
        )

    @staticmethod
    def _image_urls(record: object) -> list[str]:
        if not isinstance(record, dict):
            raise ValueError("Louvre JSON record must be an object")

        images = record.get("image")
        if images is None:
            return []
        if not isinstance(images, list):
            raise ValueError("Louvre JSON image section must be a list")

        image_urls = []
        for image in images:
            if not isinstance(image, dict):
                continue
            image_url = image.get("urlImage")
            if isinstance(image_url, str) and image_url:
                image_urls.append(image_url)
        return list(dict.fromkeys(image_urls))

    def download(self, url: str, target: Path) -> None:
        json_url = self._json_url(url)
        logger.info("Fetching Louvre JSON record: %s", json_url)

        with requests.Session() as session:
            record_response = session.get(json_url, timeout=self.REQUEST_TIMEOUT)
            record_response.raise_for_status()
            image_urls = self._image_urls(record_response.json())
            logger.info("Louvre record contains %d image(s): %s", len(image_urls), url)

            for image_url in image_urls:
                parsed_image_url = urlparse(image_url)
                if parsed_image_url.scheme not in {"http", "https"}:
                    raise ValueError(f"Unsupported Louvre image URL: {image_url}")
                filename = Path(unquote(parsed_image_url.path)).name
                if not filename:
                    raise ValueError(f"Louvre image URL has no filename: {image_url}")

                logger.debug("Downloading Louvre image to %s: %s", filename, image_url)
                with session.get(
                    image_url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True,
                ) as image_response:
                    image_response.raise_for_status()
                    with (target / filename).open("wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=64 * 1024):
                            image_file.write(chunk)

        logger.info("Completed Louvre record: %s", url)
