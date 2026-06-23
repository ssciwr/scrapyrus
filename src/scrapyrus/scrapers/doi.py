import logging
from urllib.parse import urlparse

import requests

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.doi")


class DOIScraper(ImageScraperBase):
    """Resolve DOI URLs and return their destination to the scraper chain."""

    HOST = "doi.org"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return parsed_url.scheme == "https" and parsed_url.hostname == self.HOST

    def resolve(self, url: str) -> str:
        logger.info("Resolving DOI URL: %s", url)
        with requests.get(
            url,
            allow_redirects=True,
            stream=True,
            timeout=self.REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            resolved_url = response.url

        if resolved_url == url:
            raise RuntimeError(f"DOI URL did not redirect: {url}")

        logger.info("Resolved DOI URL %s to %s", url, resolved_url)
        return resolved_url
