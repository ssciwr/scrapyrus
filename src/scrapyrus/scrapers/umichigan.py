import re
from urllib.parse import urlparse

import requests

from scrapyrus.scrapers.iiif import IIIFImageScraper


class UMichiganScraper(IIIFImageScraper):
    """Download IIIF images from University of Michigan APIS records."""

    HOST = "quod.lib.umich.edu"
    SOURCE_PATH_PATTERN = re.compile(r"^/a/apis/x-(\d+)/?$")
    MANIFEST_ROOT = "https://quod.lib.umich.edu/cgi/i/image/api/manifest/apis:"

    @classmethod
    def _record_identifier(cls, url: str) -> str | None:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            return None
        if parsed_url.hostname != cls.HOST:
            return None

        match = cls.SOURCE_PATH_PATTERN.fullmatch(parsed_url.path)
        return match.group(1) if match is not None else None

    def responsible(self, url: str) -> bool:
        return self._record_identifier(url) is not None

    def manifest_urls(self, url: str, session: requests.Session) -> list[str]:
        identifier = self._record_identifier(url)
        if identifier is None:
            raise ValueError(f"Unsupported University of Michigan APIS URL: {url}")
        return [self.MANIFEST_ROOT + identifier]
