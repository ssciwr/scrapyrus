import logging
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.aphrodito")


class AphroditoScraper(ImageScraperBase):
    """Download images from the Aphrodito papyrus database."""

    HOST = "bipab.aphrodito.info"
    PAGE_PATH_PATTERN = re.compile(r"^/pages_html/(?P<identifier>[^/]+)\.html$")
    IMAGE_LINK_LABEL = "grande image"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.PAGE_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _image_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        image_urls = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            label = " ".join(link.get_text(" ", strip=True).split()).casefold()
            href = link.get("href")
            if label != cls.IMAGE_LINK_LABEL or not isinstance(href, str):
                continue

            image_url = urljoin(page_url, href.strip())
            parsed_url = urlparse(image_url)
            if (
                parsed_url.scheme not in {"http", "https"}
                or parsed_url.hostname != cls.HOST
                or image_url in seen_urls
            ):
                continue

            seen_urls.add(image_url)
            image_urls.append(image_url)

        return image_urls

    def download(self, url: str, target: Path) -> None:
        logger.info("Fetching Aphrodito record: %s", url)
        with requests.Session() as session:
            page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
            page_response.raise_for_status()
            page_url = page_response.url or url
            image_urls = self._image_urls(page_response.text, page_url)
            logger.info(
                "Aphrodito record contains %d image(s): %s",
                len(image_urls),
                page_url,
            )

            for image_url in image_urls:
                filename = Path(unquote(urlparse(image_url).path)).name
                if not filename:
                    raise ValueError(
                        f"Aphrodito image URL has no filename: {image_url}"
                    )

                logger.debug(
                    "Downloading Aphrodito image to %s: %s", filename, image_url
                )
                with session.get(
                    image_url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True,
                ) as image_response:
                    image_response.raise_for_status()
                    with (target / filename).open("wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=64 * 1024):
                            image_file.write(chunk)

        logger.info("Completed Aphrodito record: %s", url)
