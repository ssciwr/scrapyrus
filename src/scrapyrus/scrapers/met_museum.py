import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase, RateLimitedMixin


logger = logging.getLogger("scrapyrus.images.scrapers.met_museum")


class MetMuseumScraper(RateLimitedMixin, ImageScraperBase):
    """Download original images from Metropolitan Museum object records."""

    HOST = "www.metmuseum.org"
    IMAGE_HOST = "images.metmuseum.org"
    RECORD_PATH_PATTERN = re.compile(
        r"^/(?:[a-z]{2}/)?art/collection/search/\d+/?$",
        re.IGNORECASE,
    )
    ORIGINAL_IMAGE_URL_PATTERN = re.compile(
        r'originalImageUrl\\?"\s*:\s*\\?"(?P<url>[^"\\]+)'
    )
    REQUEST_TIMEOUT = 30
    REQUEST_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _image_urls(cls, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        image_urls = []
        for script in soup.find_all("script", string=cls.ORIGINAL_IMAGE_URL_PATTERN):
            script_text = script.string or script.get_text()
            for match in cls.ORIGINAL_IMAGE_URL_PATTERN.finditer(script_text):
                image_url = match.group("url")
                parsed_url = urlparse(image_url)
                if (
                    parsed_url.scheme == "https"
                    and parsed_url.hostname == cls.IMAGE_HOST
                    and image_url not in image_urls
                ):
                    image_urls.append(image_url)
        return image_urls

    @staticmethod
    def _filename(image_url: str) -> str:
        filename = Path(unquote(urlparse(image_url).path)).name
        if not filename:
            raise ValueError(f"Met Museum image URL has no filename: {image_url}")
        return filename

    def download(self, url: str, target: Path) -> None:
        logger.info("Fetching Met Museum object record: %s", url)

        try:
            with requests.Session() as session:
                session.headers.update(self.REQUEST_HEADERS)
                record_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
                record_response.raise_for_status()
                record_url = record_response.url or url
                image_urls = self._image_urls(record_response.text)
                if not image_urls:
                    raise ValueError(
                        f"Met Museum record has no downloadable images: {record_url}"
                    )
                logger.info(
                    "Met Museum record contains %d image(s): %s",
                    len(image_urls),
                    record_url,
                )

                for image_url in image_urls:
                    filename = self._filename(image_url)
                    logger.debug(
                        "Downloading Met Museum image to %s: %s",
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
                    "Met Museum rate limit triggered by HTTP 429 for %s "
                    "(response URL: %s)",
                    url,
                    error.response.url or url,
                )
            raise

        logger.info("Completed Met Museum record: %s", url)
