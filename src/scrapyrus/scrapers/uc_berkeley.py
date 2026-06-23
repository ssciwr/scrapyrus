import json
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase, RateLimitedMixin


logger = logging.getLogger("scrapyrus.images.scrapers.uc_berkeley")


class UCBerkeleyScraper(RateLimitedMixin, ImageScraperBase):
    """Download image files exposed by UC Berkeley digital records."""

    HOST = "digicoll.lib.berkeley.edu"
    RECORD_PATH_PATTERN = re.compile(r"^/record/\d+/?$")
    REQUEST_TIMEOUT = 30
    IMAGE_SUFFIXES = frozenset(
        {".bmp", ".gif", ".jp2", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
    )

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _image_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        schema = soup.select_one(
            'script#detailed-schema-org[type="application/ld+json"]'
        )
        if schema is None:
            return []

        record = json.loads(schema.string or schema.get_text())
        if not isinstance(record, dict):
            raise ValueError("UC Berkeley record JSON-LD must be an object")

        content_urls = record.get("contentUrl", [])
        if isinstance(content_urls, str):
            content_urls = [content_urls]
        if not isinstance(content_urls, list):
            raise ValueError("UC Berkeley record contentUrl must be a list or string")

        image_urls = []
        seen_urls = set()
        for content_url in content_urls:
            if not isinstance(content_url, str) or not content_url:
                continue
            image_url = urljoin(page_url, content_url)
            parsed_url = urlparse(image_url)
            suffix = Path(unquote(parsed_url.path)).suffix.lower()
            if parsed_url.scheme not in {"http", "https"}:
                continue
            if parsed_url.hostname != cls.HOST:
                continue
            if suffix not in cls.IMAGE_SUFFIXES:
                continue
            if image_url not in seen_urls:
                seen_urls.add(image_url)
                image_urls.append(image_url)
        return image_urls

    def download(self, url: str, target: Path) -> None:
        logger.info("Fetching UC Berkeley record: %s", url)
        try:
            with requests.Session() as session:
                page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
                page_response.raise_for_status()
                page_url = page_response.url or url
                image_urls = self._image_urls(page_response.text, page_url)
                logger.info(
                    "UC Berkeley record contains %d image(s): %s",
                    len(image_urls),
                    page_url,
                )

                for image_url in image_urls:
                    filename = Path(unquote(urlparse(image_url).path)).name
                    if not filename:
                        raise ValueError(
                            f"UC Berkeley image URL has no filename: {image_url}"
                        )

                    logger.debug(
                        "Downloading UC Berkeley image to %s: %s",
                        filename,
                        image_url,
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
                    "UC Berkeley rate limit triggered by HTTP 429 for %s "
                    "(response URL: %s)",
                    url,
                    error.response.url or url,
                )
            raise

        logger.info("Completed UC Berkeley record: %s", url)
