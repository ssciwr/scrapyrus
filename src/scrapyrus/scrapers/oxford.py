import logging
import re
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.oxford")


class OxfordScraper(ImageScraperBase):
    """Download images attached to Oxford research repository records."""

    HOST = "portal.sds.ox.ac.uk"
    ARTICLE_PATH_PATTERN = re.compile(
        r"^/articles/online_resource/[^/]+/\d+(?:/\d+)?/?$"
    )
    FILE_IDENTIFIER_PATTERN = re.compile(r"^\d+$")
    DOWNLOAD_URL_ROOT = "https://portal.sds.ox.ac.uk/ndownloader/files/"
    REQUEST_TIMEOUT = 30

    @classmethod
    def _file_identifier(cls, url: str) -> str:
        parsed_url = urlparse(url)
        file_identifiers = parse_qs(parsed_url.query).get("file", [])
        if (
            cls.ARTICLE_PATH_PATTERN.fullmatch(parsed_url.path) is None
            or len(file_identifiers) != 1
            or cls.FILE_IDENTIFIER_PATTERN.fullmatch(file_identifiers[0]) is None
        ):
            raise ValueError(f"Unsupported Oxford repository URL: {url}")
        return file_identifiers[0]

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        if not (
            parsed_url.scheme in {"http", "https"} and parsed_url.hostname == self.HOST
        ):
            return False

        try:
            self._file_identifier(url)
        except ValueError:
            return False
        return True

    @classmethod
    def _image_url(cls, url: str) -> str:
        return cls.DOWNLOAD_URL_ROOT + cls._file_identifier(url)

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
    def _filename(cls, response: requests.Response, image_url: str) -> str:
        filename = cls._content_disposition_filename(response)
        if filename is not None:
            return filename

        response_url = response.url or image_url
        filename = Path(unquote(urlparse(response_url).path)).name
        if not filename:
            raise ValueError(f"Oxford image response has no filename: {response_url}")
        return filename

    def download(self, url: str, target: Path) -> None:
        image_url = self._image_url(url)

        logger.info("Downloading Oxford repository image: %s", image_url)
        with requests.get(
            image_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            filename = self._filename(response, image_url)
            with (target / filename).open("wb") as image_file:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)
        logger.info("Completed Oxford repository image: %s", image_url)
