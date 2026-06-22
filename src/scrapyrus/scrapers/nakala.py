import logging
import mimetypes
import re
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.nakala")


class NakalaScraper(ImageScraperBase):
    """Download images exposed directly by the Nakala IIIF API."""

    HOST = "api.nakala.fr"
    IMAGE_PATH_PATTERN = re.compile(
        r"^/iiif/10\.34847/nkl\.[^/]+/[0-9a-f]{40}/?$",
        re.IGNORECASE,
    )
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.IMAGE_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @staticmethod
    def _content_disposition_filename(response: requests.Response) -> str | None:
        header = response.headers.get("Content-Disposition")
        if not header:
            return None

        message = Message()
        message["Content-Disposition"] = header
        filename = message.get_filename()
        if not filename:
            return None
        return Path(unquote(filename.replace("\\", "/"))).name or None

    @classmethod
    def _filename(cls, url: str, response: requests.Response) -> str:
        filename = cls._content_disposition_filename(response)
        if filename is not None:
            return filename

        identifier = Path(unquote(urlparse(url).path.rstrip("/"))).name
        if not identifier:
            raise ValueError(f"Nakala image URL has no identifier: {url}")

        content_type = response.headers.get("Content-Type", "").partition(";")[0]
        suffix = mimetypes.guess_extension(content_type) or ".jpg"
        return identifier + suffix

    def download(self, url: str, target: Path) -> None:
        logger.info("Downloading Nakala image: %s", url)
        with requests.get(
            url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            filename = self._filename(url, response)
            logger.debug("Writing Nakala image to %s: %s", filename, url)
            with (target / filename).open("wb") as image_file:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)
        logger.info("Completed Nakala image: %s", url)
