import re
from urllib.parse import urlparse

import requests

from scrapyrus.scrapers.iiif import IIIFImageScraper


class YaleScraper(IIIFImageScraper):
    """Download IIIF images exposed by Yale Digital Collections pages."""

    HANDLE_HOST = "hdl.handle.net"
    HANDLE_PATH_PATTERN = re.compile(r"^/10079/digcoll/\d+/?$")
    CATALOG_HOST = "collections.library.yale.edu"
    CATALOG_PATH_PATTERN = re.compile(r"^/catalog/(?P<catalog_id>\d+)/?$")

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            return False
        return (
            parsed_url.hostname == self.HANDLE_HOST
            and self.HANDLE_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        ) or (
            parsed_url.hostname == self.CATALOG_HOST
            and self.CATALOG_PATH_PATTERN.fullmatch(parsed_url.path) is not None
        )

    @classmethod
    def _manifest_url(cls, catalog_url: str) -> str:
        parsed_url = urlparse(catalog_url)
        catalog_match = cls.CATALOG_PATH_PATTERN.fullmatch(parsed_url.path)
        if parsed_url.hostname != cls.CATALOG_HOST or catalog_match is None:
            raise ValueError(
                f"Yale URL did not resolve to a catalog record: {catalog_url}"
            )
        return parsed_url._replace(
            path=f"/manifests/{catalog_match.group('catalog_id')}",
            params="",
            query="",
            fragment="",
        ).geturl()

    def manifest_urls(self, url: str, session: requests.Session) -> list[str]:
        if urlparse(url).hostname == self.CATALOG_HOST:
            return [self._manifest_url(url)]

        page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()
        page_url = page_response.url or url
        return [self._manifest_url(page_url)]
