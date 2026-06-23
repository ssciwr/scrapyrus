import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.scrapers.iiif import IIIFImageScraper


class UBHDScraper(IIIFImageScraper):
    """Download IIIF images from Heidelberg University Library records."""

    HOST = "digi.ub.uni-heidelberg.de"
    SOURCE_PATH_PATTERN = re.compile(r"^/diglit/[^/]+/?$")
    MANIFEST_SELECTORS = (
        'a[href*="/diglit/iiif3/"][href$="/manifest"]',
        'a[href*="/diglit/iiif/"][href$="/manifest"]',
    )

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.HOST
            and self.SOURCE_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _manifest_url(cls, html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for selector in cls.MANIFEST_SELECTORS:
            link = soup.select_one(selector)
            if link is not None:
                href = link.get("href")
                if isinstance(href, str) and href:
                    return urljoin(page_url, href)
        raise ValueError("UB Heidelberg page has no IIIF manifest link")

    def manifest_urls(self, url: str, session: requests.Session) -> list[str]:
        page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()
        page_url = page_response.url or url
        return [self._manifest_url(page_response.text, page_url)]
