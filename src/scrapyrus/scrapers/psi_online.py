import logging
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.psi_online")


class PSIOnlineScraper(ImageScraperBase):
    """Download original images linked by PSI Online document records."""

    HOSTS = frozenset({"psi-online.it", "www.psi-online.it"})
    DOCUMENT_PATH_PREFIX = "/documents/"
    DOWNLOAD_PATH = "/documents/download"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname in self.HOSTS
            and parsed_url.path.startswith(self.DOCUMENT_PATH_PREFIX)
            and parsed_url.path != self.DOWNLOAD_PATH
            and parsed_url.path != self.DOCUMENT_PATH_PREFIX
        )

    @classmethod
    def _download_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        download_urls = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            download_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(download_url)
            filenames = parse_qs(parsed_url.query).get("filen", [])
            if (
                parsed_url.scheme not in {"http", "https"}
                or parsed_url.hostname not in cls.HOSTS
                or parsed_url.path != cls.DOWNLOAD_PATH
                or not any(filenames)
                or download_url in seen_urls
            ):
                continue
            seen_urls.add(download_url)
            download_urls.append(download_url)

        return download_urls

    @staticmethod
    def _filename(download_url: str) -> str:
        filenames = parse_qs(urlparse(download_url).query).get("filen", [])
        if not filenames:
            raise ValueError(f"PSI Online download URL has no filename: {download_url}")

        filename = Path(filenames[0].replace("\\", "/")).name
        if not filename:
            raise ValueError(f"PSI Online download URL has no filename: {download_url}")
        return filename

    def download(self, url: str, target: Path) -> None:
        logger.info("Fetching PSI Online document record: %s", url)
        with requests.Session() as session:
            page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
            page_response.raise_for_status()
            page_url = page_response.url or url
            download_urls = self._download_urls(page_response.text, page_url)
            logger.info(
                "PSI Online record contains %d image(s): %s",
                len(download_urls),
                page_url,
            )

            for download_url in download_urls:
                filename = self._filename(download_url)
                logger.debug(
                    "Downloading PSI Online image to %s: %s",
                    filename,
                    download_url,
                )
                with session.get(
                    download_url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True,
                ) as image_response:
                    image_response.raise_for_status()
                    with (target / filename).open("wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=64 * 1024):
                            image_file.write(chunk)

        logger.info("Completed PSI Online record: %s", url)
