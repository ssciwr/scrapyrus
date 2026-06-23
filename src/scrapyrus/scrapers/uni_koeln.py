import logging
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase, RateLimitedMixin


logger = logging.getLogger("scrapyrus.images.scrapers.uni_koeln")


class UniKoelnScraper(RateLimitedMixin, ImageScraperBase):
    """Download images linked by legacy University of Cologne papyrus pages."""

    HOST = "www.uni-koeln.de"
    RECORD_PATH = "/phil-fak/ifa/NRWakademie/papyrologie/"
    REQUEST_TIMEOUT = 30
    IMAGE_SUFFIXES = frozenset(
        {".bmp", ".gif", ".jp2", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
    )

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and parsed_url.path.startswith(self.RECORD_PATH)
            and parsed_url.path.lower().endswith((".htm", ".html"))
        )

    @classmethod
    def _image_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        marker = soup.find(
            string=lambda text: text is not None and text.strip() == "Abbildung:"
        )
        if marker is None:
            return []

        image_urls = []
        seen_urls = set()
        for link in marker.find_all_next("a", href=True):
            image_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(image_url)
            suffix = Path(unquote(parsed_url.path)).suffix.lower()
            if parsed_url.scheme not in {"http", "https"}:
                continue
            if suffix not in cls.IMAGE_SUFFIXES:
                continue
            if image_url not in seen_urls:
                seen_urls.add(image_url)
                image_urls.append(image_url)
        return image_urls

    def download(self, url: str, target: Path) -> None:
        logger.info("Fetching Uni Koeln papyrus record: %s", url)
        try:
            with requests.Session() as session:
                page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
                page_response.raise_for_status()
                page_url = page_response.url or url
                image_urls = self._image_urls(page_response.text, page_url)
                logger.info(
                    "Uni Koeln record contains %d image(s): %s",
                    len(image_urls),
                    page_url,
                )

                for image_url in image_urls:
                    filename = Path(unquote(urlparse(image_url).path)).name
                    if not filename:
                        raise ValueError(
                            f"Uni Koeln image URL has no filename: {image_url}"
                        )

                    logger.debug(
                        "Downloading Uni Koeln image to %s: %s", filename, image_url
                    )
                    with session.get(
                        image_url,
                        timeout=self.REQUEST_TIMEOUT,
                        stream=True,
                    ) as image_response:
                        image_response.raise_for_status()
                        with (target / filename).open("wb") as image_file:
                            for chunk in image_response.iter_content(
                                chunk_size=64 * 1024
                            ):
                                image_file.write(chunk)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 429:
                self.mark_rate_limited()
                logger.warning(
                    "Uni Koeln rate limit triggered by HTTP 429 for %s "
                    "(response URL: %s)",
                    url,
                    error.response.url or url,
                )
            raise

        logger.info("Completed Uni Koeln papyrus record: %s", url)
