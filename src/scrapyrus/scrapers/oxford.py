import logging
import re
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

from scrapyrus.images import ImageScraperBase, RateLimitedMixin


logger = logging.getLogger("scrapyrus.images.scrapers.oxford")


class OxfordScraper(RateLimitedMixin, ImageScraperBase):
    """Download images attached to Oxford research repository records."""

    HOST = "portal.sds.ox.ac.uk"
    ARTICLE_PATH_PATTERN = re.compile(
        r"^/articles/online_resource/[^/]+/(\d+)(?:/\d+)?/?$"
    )
    FILE_IDENTIFIER_PATTERN = re.compile(r"^\d+$")
    API_URL_ROOT = "https://api.figshare.com/v2/articles/"
    DOWNLOAD_URL_ROOT = "https://portal.sds.ox.ac.uk/ndownloader/files/"
    REQUEST_TIMEOUT = 30

    @classmethod
    def _article_identifier(cls, url: str) -> str:
        parsed_url = urlparse(url)
        match = cls.ARTICLE_PATH_PATTERN.fullmatch(parsed_url.path)
        if match is None:
            raise ValueError(f"Unsupported Oxford repository URL: {url}")
        return match.group(1)

    @classmethod
    def _file_identifier(cls, url: str) -> str | None:
        parsed_url = urlparse(url)
        query = parse_qs(parsed_url.query, keep_blank_values=True)
        if "file" not in query:
            return None

        file_identifiers = query["file"]
        if (
            len(file_identifiers) != 1
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
            self._article_identifier(url)
            self._file_identifier(url)
        except ValueError:
            return False
        return True

    @classmethod
    def _image_url(cls, url: str) -> str:
        cls._article_identifier(url)
        file_identifier = cls._file_identifier(url)
        if file_identifier is None:
            raise ValueError(f"Oxford repository URL has no file identifier: {url}")
        return cls.DOWNLOAD_URL_ROOT + file_identifier

    @classmethod
    def _file_identifiers(cls, record: object) -> list[str]:
        if not isinstance(record, dict):
            raise ValueError("Oxford repository API record must be an object")

        files = record.get("files")
        if not isinstance(files, list):
            raise ValueError("Oxford repository API files section must be a list")

        identifiers = []
        for file in files:
            if not isinstance(file, dict):
                continue
            identifier = file.get("id")
            mimetype = file.get("mimetype")
            if (
                not isinstance(identifier, int)
                or isinstance(identifier, bool)
                or identifier < 0
                or not isinstance(mimetype, str)
                or not mimetype.startswith("image/")
            ):
                continue
            identifiers.append(str(identifier))
        return list(dict.fromkeys(identifiers))

    def _image_urls(self, url: str, session: requests.Session) -> list[str]:
        article_identifier = self._article_identifier(url)
        file_identifier = self._file_identifier(url)
        if file_identifier is not None:
            return [self.DOWNLOAD_URL_ROOT + file_identifier]

        api_url = self.API_URL_ROOT + article_identifier
        logger.info("Fetching Oxford repository API record: %s", api_url)
        self.wait_for_request_slot()
        response = session.get(api_url, timeout=self.REQUEST_TIMEOUT)
        response.raise_for_status()
        return [
            self.DOWNLOAD_URL_ROOT + identifier
            for identifier in self._file_identifiers(response.json())
        ]

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
        try:
            with requests.Session() as session:
                image_urls = self._image_urls(url, session)
                logger.info(
                    "Oxford repository record contains %d image(s): %s",
                    len(image_urls),
                    url,
                )
                for image_url in image_urls:
                    logger.info("Downloading Oxford repository image: %s", image_url)
                    with session.get(
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
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code in {403, 429}:
                self.mark_rate_limited()
                logger.warning(
                    "Oxford rate limit triggered by HTTP %d for %s (response URL: %s)",
                    error.response.status_code,
                    url,
                    error.response.url or url,
                )
            raise
