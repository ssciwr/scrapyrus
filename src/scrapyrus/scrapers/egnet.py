import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.egnet")


class EgnetScraper(ImageScraperBase):
    """Download vignette images from IFAO Egnet publication records."""

    HOST = "www.ifao.egnet.net"
    FIFAO67_RECORD_PATH = "/bases/publications/fifao67/"
    FIFAO81_RECORD_PATH = "/bases/publications/fifao81/"
    RECORD_PATHS = frozenset({FIFAO67_RECORD_PATH, FIFAO81_RECORD_PATH})
    IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
    OFFSET_PATTERN = re.compile(r"^[0-9]+$")
    REQUEST_TIMEOUT = 30

    @classmethod
    def _record_path(cls, url: str) -> str:
        parsed_url = urlparse(url)
        record_path = parsed_url.path.rstrip("/") + "/"
        if record_path not in cls.RECORD_PATHS:
            raise ValueError(f"Unsupported Egnet record URL: {url}")
        return record_path

    @classmethod
    def _identifier(cls, url: str) -> str:
        cls._record_path(url)
        parsed_url = urlparse(url)
        identifiers = parse_qs(parsed_url.query).get("id", [])
        if (
            len(identifiers) != 1
            or cls.IDENTIFIER_PATTERN.fullmatch(identifiers[0]) is None
        ):
            raise ValueError(f"Unsupported Egnet record URL: {url}")
        return identifiers[0]

    @classmethod
    def _offset(cls, url: str) -> str:
        if cls._record_path(url) != cls.FIFAO67_RECORD_PATH:
            raise ValueError(f"Unsupported Egnet record URL: {url}")

        query = parse_qs(urlparse(url).query)
        offsets = query.get("os", [])
        if (
            query.get("id")
            or len(offsets) != 1
            or cls.OFFSET_PATTERN.fullmatch(offsets[0]) is None
        ):
            raise ValueError(f"Unsupported Egnet record URL: {url}")
        return offsets[0]

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        if not (
            parsed_url.scheme in {"http", "https"} and parsed_url.hostname == self.HOST
        ):
            return False

        for record_reference in (self._identifier, self._offset):
            try:
                record_reference(url)
            except ValueError:
                continue
            return True
        return False

    @classmethod
    def _image_url(cls, url: str) -> str:
        parsed_url = urlparse(url)
        record_path = cls._record_path(url)
        identifier = cls._identifier(url)
        return urlunparse(
            parsed_url._replace(
                path=f"{record_path}docs/vignettes/{identifier}.jpg",
                query="",
                fragment="",
            )
        )

    @classmethod
    def _offset_image_url(cls, html: str, page_url: str) -> str:
        expected_directory = f"{cls.FIFAO67_RECORD_PATH}docs/vignettes"
        soup = BeautifulSoup(html, "html.parser")

        for image in soup.find_all("img", src=True):
            source = image.get("src")
            if not isinstance(source, str):
                continue

            image_url = urlparse(urljoin(page_url, source.strip()))
            image_path = Path(image_url.path)
            if (
                image_url.scheme not in {"http", "https"}
                or image_url.hostname != cls.HOST
                or image_path.parent.as_posix() != expected_directory
                or image_path.suffix.lower() != ".jpg"
                or cls.IDENTIFIER_PATTERN.fullmatch(image_path.stem) is None
            ):
                continue
            return urlunparse(image_url._replace(fragment=""))

        raise ValueError(f"FIFAO 67 record page has no vignette image: {page_url}")

    def download(self, url: str, target: Path) -> None:
        try:
            image_url = self._image_url(url)
        except ValueError:
            self._offset(url)
            logger.info("Fetching Egnet FIFAO 67 record: %s", url)
            page_response = requests.get(url, timeout=self.REQUEST_TIMEOUT)
            page_response.raise_for_status()
            page_url = page_response.url or url
            image_url = self._offset_image_url(page_response.text, page_url)

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
