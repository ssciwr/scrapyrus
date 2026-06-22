import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import ImageScraperBase


logger = logging.getLogger("scrapyrus.images.scrapers.ucl")


class UCLScraper(ImageScraperBase):
    """Download Petrie Museum images referenced by legacy UCL catalogue URLs."""

    LEGACY_HOST = "petriecat.museums.ucl.ac.uk"
    LEGACY_PATH = "/dispatcher.aspx"
    COLLECTIONS_HOST = "collections.ucl.ac.uk"
    SEARCH_URL = "https://collections.ucl.ac.uk/search/expert"
    RECORD_PATH_PATTERN = re.compile(r"^/Details/collect/\d+/?$", re.IGNORECASE)
    IMAGE_PATH = "/AxiellWebApi/wwwopac.ashx"
    ACCESSION_PATTERN = re.compile(
        r"\baccession_number\s*=\s*(['\"])"
        r"UC(?P<identifier>\d+)[A-Z0-9 ._-]*\1",
        re.IGNORECASE,
    )
    REQUEST_TIMEOUT = 30

    @classmethod
    def _legacy_accession_number(cls, url: str) -> str:
        searches = parse_qs(urlparse(url).query).get("search", [])
        for search in searches:
            match = cls.ACCESSION_PATTERN.search(search)
            if match is not None:
                return f"UC{match.group('identifier')}"
        raise ValueError(f"UCL URL has no supported accession number: {url}")

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        query = parse_qs(parsed_url.query)
        if not (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname == self.LEGACY_HOST
            and parsed_url.path.lower() == self.LEGACY_PATH
            and any(value.lower() == "search" for value in query.get("action", []))
            and any(
                value.lower() == "choiceuclpc" for value in query.get("database", [])
            )
        ):
            return False

        try:
            self._legacy_accession_number(url)
        except ValueError:
            return False
        return True

    @staticmethod
    def _search_data(accession_number: str) -> dict[str, str]:
        return {
            "SourceName": "collect",
            "Fields[0].SearchInField": "False",
            "Fields[0].FieldName": "Field_object_number_Detail",
            "Fields[0].CompareOperator": "Equal",
            "Fields[0].Value": f"LDUCE-{accession_number}",
            "Fields[0].BindableUseTruncation": "false",
            "Fields[0].LogicalConnective": "And",
            "Filters[0].Name": "Search_FieldOnlyImages",
            "Filters[0].Show": "True",
            "Filters[0].Value": "false",
            "RecordSort.FieldName": "Search_SortAccNo",
            "RecordSort.Direction": "Ascending",
            "RecordLimit.PageSize": "15",
        }

    @classmethod
    def _record_url(cls, html: str, page_url: str, accession_number: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        record_urls = []
        for link in soup.find_all("a", href=True):
            record_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(record_url)
            if (
                parsed_url.scheme == "https"
                and parsed_url.hostname == cls.COLLECTIONS_HOST
                and cls.RECORD_PATH_PATTERN.fullmatch(parsed_url.path) is not None
                and record_url not in record_urls
            ):
                record_urls.append(record_url)

        if len(record_urls) != 1:
            raise ValueError(
                f"UCL search for LDUCE-{accession_number} returned "
                f"{len(record_urls)} records"
            )
        return record_urls[0]

    @classmethod
    def _image_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        image_urls = []
        for link in soup.find_all("a", href=True):
            image_url = urljoin(page_url, link["href"])
            parsed_url = urlparse(image_url)
            query = parse_qs(parsed_url.query)
            if (
                parsed_url.scheme == "https"
                and parsed_url.hostname == cls.COLLECTIONS_HOST
                and parsed_url.path.lower() == cls.IMAGE_PATH.lower()
                and query.get("command") == ["getcontent"]
                and query.get("server") == ["images"]
                and any(query.get("value", []))
                and image_url not in image_urls
            ):
                image_urls.append(image_url)
        return image_urls

    @staticmethod
    def _filename(image_url: str) -> str:
        image_paths = parse_qs(urlparse(image_url).query).get("value", [])
        if not image_paths:
            raise ValueError(f"UCL image URL has no source path: {image_url}")
        filename = Path(image_paths[0].replace("\\", "/")).name
        if not filename:
            raise ValueError(f"UCL image URL has no filename: {image_url}")
        return filename

    def download(self, url: str, target: Path) -> None:
        legacy_accession_number = self._legacy_accession_number(url)
        accession_number = f"LDUCE-{legacy_accession_number}"
        logger.info("Searching UCL Collections for %s", accession_number)

        with requests.Session() as session:
            results_response = session.post(
                self.SEARCH_URL,
                data=self._search_data(legacy_accession_number),
                timeout=self.REQUEST_TIMEOUT,
            )
            results_response.raise_for_status()
            results_url = results_response.url or self.SEARCH_URL
            record_url = self._record_url(
                results_response.text,
                results_url,
                legacy_accession_number,
            )

            logger.info("Fetching UCL Collections record: %s", record_url)
            record_response = session.get(record_url, timeout=self.REQUEST_TIMEOUT)
            record_response.raise_for_status()
            final_record_url = record_response.url or record_url
            image_urls = self._image_urls(record_response.text, final_record_url)
            if not image_urls:
                raise ValueError(f"UCL record has no downloadable images: {record_url}")
            logger.info(
                "UCL Collections record contains %d image(s): %s",
                len(image_urls),
                final_record_url,
            )

            for image_url in image_urls:
                filename = self._filename(image_url)
                logger.debug("Downloading UCL image to %s: %s", filename, image_url)
                with session.get(
                    image_url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True,
                ) as image_response:
                    image_response.raise_for_status()
                    with (target / filename).open("wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=64 * 1024):
                            image_file.write(chunk)

        logger.info("Completed UCL Collections record: %s", accession_number)
