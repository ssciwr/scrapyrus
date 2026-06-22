from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


class BerlPapScraper(ImageScraperBase):
    """Download full-resolution images from the Berliner Papyrusdatenbank."""

    HOST = "berlpap.smb.museum"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return parsed_url.scheme in {"http", "https"} and parsed_url.netloc == self.HOST

    def _image_urls(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find(
            "b",
            string=lambda text: text is not None and text.strip() == "Digitalisate",
        )
        if heading is None:
            return []

        table = heading.find_parent("table")
        if table is None:
            return []

        image_urls = []
        seen_urls = set()
        for link in table.find_all("a", href=True):
            image_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(image_url)
            if not (
                parsed_url.scheme == "https"
                and parsed_url.netloc == self.HOST
                and parsed_url.path.startswith("/Original/")
            ):
                continue
            if image_url not in seen_urls:
                seen_urls.add(image_url)
                image_urls.append(image_url)
        return image_urls

    def download(self, url: str, target: Path) -> None:
        page_response = requests.get(url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()

        for image_url in self._image_urls(page_response.text, url):
            filename = Path(unquote(urlparse(image_url).path)).name
            if not filename:
                continue
            with requests.get(
                image_url,
                timeout=self.REQUEST_TIMEOUT,
                stream=True,
            ) as image_response:
                image_response.raise_for_status()
                with (target / filename).open("wb") as image_file:
                    for chunk in image_response.iter_content(chunk_size=64 * 1024):
                        image_file.write(chunk)
