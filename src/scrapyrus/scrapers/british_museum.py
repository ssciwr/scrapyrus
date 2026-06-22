import logging
import re
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.british_museum")


class BritishMuseumScraper(ImageScraperBase):
    """Download images offered for reuse by British Museum object records."""

    HOST = "www.britishmuseum.org"
    RECORD_PATH_PATTERN = re.compile(r"^/collection/object/[^/]+/?$")
    IMAGE_PATH_PATTERN = re.compile(r"^/collection/image/\d+/?$")
    DOWNLOAD_LABEL = "Download this image"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _image_page_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        image_page_urls = []
        seen_urls = set()
        links = soup.select(
            ".object-detail__image a[href], a.object-detail__footer-cta[href]"
        )
        for link in links:
            image_page_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(image_page_url)
            if (
                parsed_url.scheme not in {"http", "https"}
                or parsed_url.hostname != cls.HOST
                or cls.IMAGE_PATH_PATTERN.fullmatch(parsed_url.path) is None
                or image_page_url in seen_urls
            ):
                continue
            seen_urls.add(image_page_url)
            image_page_urls.append(image_page_url)
        return image_page_urls

    @classmethod
    def _download_url(cls, html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a", href=True):
            if link.get_text(" ", strip=True) != cls.DOWNLOAD_LABEL:
                continue
            download_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(download_url)
            if parsed_url.scheme in {"http", "https"}:
                return download_url
        raise ValueError("British Museum image page has no download link")

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
    def _filename(cls, response: requests.Response, download_url: str) -> str:
        filename = cls._content_disposition_filename(response)
        if filename is not None:
            return filename

        response_url = response.url or download_url
        filename = Path(unquote(urlparse(response_url).path)).name
        if not filename:
            raise ValueError(
                f"British Museum image response has no filename: {response_url}"
            )
        return filename

    def download(self, url: str, target: Path) -> None:
        logger.info("Fetching British Museum object record: %s", url)
        with requests.Session() as session:
            object_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
            object_response.raise_for_status()
            object_url = object_response.url or url
            image_page_urls = self._image_page_urls(object_response.text, object_url)
            logger.info(
                "British Museum record contains %d image(s): %s",
                len(image_page_urls),
                object_url,
            )

            for image_page_url in image_page_urls:
                image_page_response = session.get(
                    image_page_url,
                    timeout=self.REQUEST_TIMEOUT,
                )
                image_page_response.raise_for_status()
                final_image_page_url = image_page_response.url or image_page_url
                download_url = self._download_url(
                    image_page_response.text,
                    final_image_page_url,
                )

                logger.debug("Downloading British Museum image: %s", download_url)
                with session.get(
                    download_url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True,
                ) as image_response:
                    image_response.raise_for_status()
                    filename = self._filename(image_response, download_url)
                    with (target / filename).open("wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=64 * 1024):
                            image_file.write(chunk)

        logger.info("Completed British Museum record: %s", url)
