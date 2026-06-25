import re
from urllib.parse import urlparse

import requests

from scrapyrus.scrapers.iiif import IIIFImageScraper


class BodleianScraper(IIIFImageScraper):
    """Download IIIF images from Bodleian Digital Library object pages."""

    HOST = "digital.bodleian.ox.ac.uk"
    SOURCE_PATH_PATTERN = re.compile(
        r"^/objects/"
        r"(?P<object_id>"
        r"[0-9a-fA-F]{8}-"
        r"[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{12}"
        r")/?$"
    )
    MANIFEST_ROOT = "https://iiif.bodleian.ox.ac.uk/iiif/manifest/"

    @classmethod
    def _object_identifier(cls, url: str) -> str | None:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            return None
        if parsed_url.hostname != cls.HOST:
            return None

        match = cls.SOURCE_PATH_PATTERN.fullmatch(parsed_url.path)
        return match.group("object_id") if match is not None else None

    def responsible(self, url: str) -> bool:
        return self._object_identifier(url) is not None

    def manifest_urls(self, url: str, session: requests.Session) -> list[str]:
        identifier = self._object_identifier(url)
        if identifier is None:
            raise ValueError(f"Unsupported Bodleian URL: {url}")
        return [f"{self.MANIFEST_ROOT}{identifier}.json"]
