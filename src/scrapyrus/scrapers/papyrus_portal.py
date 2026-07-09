import json
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from saxonche import PySaxonProcessor

from scrapyrus.images import ImageScraperBase
from scrapyrus.saxon_xml import (
    attribute_value,
    direct_children,
    document_element,
    first_child,
    iter_elements,
    parse_xml_text,
)


logger = logging.getLogger("scrapyrus.images.scrapers.papyrus_portal")


METS_NAMESPACE = "http://www.loc.gov/METS/"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"


class PapyrusPortalScraper(ImageScraperBase):
    """Download original images linked by PapyrusPortal records and viewers."""

    HOSTS = frozenset(
        {
            "papyri.uni-leipzig.de",
            "papyrusportal.de",
            "www.papyrusportal.de",
        }
    )
    RECEIVE_PATH = "/receive"
    VIEWER_PATH = "/rsc/viewer"
    REQUEST_TIMEOUT = 30
    IMAGE_USES = ("MASTER", "IVIEW2")
    IMAGE_SUFFIXES = frozenset(
        {".bmp", ".gif", ".jp2", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
    )
    CONFIG_PATTERN = re.compile(r"\b(?:var\s+json|let\s+configuration)\s*=\s*")
    CANONICAL_HOST = "www.papyrusportal.de"

    @staticmethod
    def _path_starts_with(path: str, prefix: str) -> bool:
        return path == prefix or path.startswith(prefix + "/")

    @classmethod
    def _is_viewer_url(cls, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname in cls.HOSTS
            and cls._path_starts_with(parsed_url.path, cls.VIEWER_PATH)
        )

    @classmethod
    def _canonical_url(cls, url: str) -> str:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            return url
        if parsed_url.hostname not in cls.HOSTS:
            return url
        return parsed_url._replace(
            scheme="https",
            netloc=cls.CANONICAL_HOST,
        ).geturl()

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname in self.HOSTS
            and (
                self._path_starts_with(parsed_url.path, self.RECEIVE_PATH)
                or self._path_starts_with(parsed_url.path, self.VIEWER_PATH)
            )
        )

    @classmethod
    def _viewer_urls(cls, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        viewer_urls = []
        seen_urls = set()
        for link in soup.find_all("a", href=True):
            viewer_url = urljoin(page_url, link["href"])
            if cls._is_viewer_url(viewer_url) and viewer_url not in seen_urls:
                seen_urls.add(viewer_url)
                viewer_urls.append(viewer_url)
        return viewer_urls

    @classmethod
    def _viewer_properties(cls, html: str) -> dict[str, object]:
        decoder = json.JSONDecoder()
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text()
            for match in cls.CONFIG_PATTERN.finditer(script_text):
                json_text = script_text[match.end() :].lstrip()
                try:
                    configuration, _ = decoder.raw_decode(json_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(configuration, dict):
                    continue
                properties = configuration.get("properties")
                if isinstance(properties, dict):
                    return properties
        raise ValueError("MyCoRe viewer configuration not found")

    @classmethod
    def _mets_image_paths(cls, mets: bytes | str) -> list[str]:
        with PySaxonProcessor(license=False) as proc:
            root = document_element(parse_xml_text(proc, mets))
            return cls._mets_image_paths_from_root(root)

    @classmethod
    def _mets_image_paths_from_root(cls, root) -> list[str]:
        files_by_use: dict[str, list[tuple[str | None, str]]] = {
            use: [] for use in cls.IMAGE_USES
        }

        for file_group in iter_elements(root, f"{{{METS_NAMESPACE}}}fileGrp"):
            use = (attribute_value(file_group, "USE", "") or "").upper()
            if use not in files_by_use:
                continue
            file_elements = direct_children(file_group, f"{{{METS_NAMESPACE}}}file")
            for file_element in file_elements:
                location = first_child(file_element, f"{{{METS_NAMESPACE}}}FLocat")
                if location is None:
                    continue
                href = attribute_value(
                    location,
                    f"{{{XLINK_NAMESPACE}}}href",
                ) or attribute_value(location, "href")
                if not href:
                    continue
                mime_type = (
                    attribute_value(file_element, "MIMETYPE", "") or ""
                ).lower()
                suffix = Path(unquote(urlparse(href).path)).suffix.lower()
                if mime_type and not mime_type.startswith("image/"):
                    continue
                if not mime_type and suffix not in cls.IMAGE_SUFFIXES:
                    continue
                files_by_use[use].append((attribute_value(file_element, "ID"), href))

        selected_files: list[tuple[str | None, str]] = []
        for use in cls.IMAGE_USES:
            if files_by_use[use]:
                selected_files = files_by_use[use]
                break
        if not selected_files:
            return []

        paths_by_id = {
            file_id: href for file_id, href in selected_files if file_id is not None
        }
        ordered_paths = []
        seen_paths = set()
        physical_map = next(
            (
                struct_map
                for struct_map in iter_elements(
                    root,
                    f"{{{METS_NAMESPACE}}}structMap",
                )
                if (attribute_value(struct_map, "TYPE", "") or "").upper() == "PHYSICAL"
            ),
            None,
        )
        if physical_map is not None:
            for element in iter_elements(physical_map):
                if element.local_name not in {"fptr", "area"}:
                    continue
                for file_id in (attribute_value(element, "FILEID", "") or "").split():
                    href = paths_by_id.get(file_id)
                    if href and href not in seen_paths:
                        seen_paths.add(href)
                        ordered_paths.append(href)

        remaining_paths = [href for _, href in selected_files if href not in seen_paths]
        return ordered_paths + remaining_paths

    @staticmethod
    def _response_url(response: requests.Response, fallback: str) -> str:
        return response.url or fallback

    @staticmethod
    def _start_file(properties: dict[str, object]) -> str | None:
        file_path = properties.get("filePath")
        if not isinstance(file_path, str) or not file_path:
            return None
        file_path = file_path.lstrip("/")
        derivate = properties.get("derivate")
        if isinstance(derivate, str) and file_path.startswith(derivate + "/"):
            file_path = file_path[len(derivate) + 1 :]
        return file_path

    def _download_image(
        self,
        session: requests.Session,
        image_url: str,
        target: Path,
    ) -> None:
        parsed_url = urlparse(image_url)
        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported image URL: {image_url}")
        if parsed_url.hostname not in self.HOSTS:
            raise ValueError(f"Unexpected image host: {parsed_url.hostname}")

        filename = Path(unquote(parsed_url.path)).name
        if not filename:
            raise ValueError(f"Image URL has no filename: {image_url}")

        logger.debug("Downloading PapyrusPortal image to %s: %s", filename, image_url)
        with session.get(
            image_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
        ) as image_response:
            image_response.raise_for_status()
            with (target / filename).open("wb") as image_file:
                for chunk in image_response.iter_content(chunk_size=64 * 1024):
                    image_file.write(chunk)

    def _download_viewer(
        self,
        session: requests.Session,
        viewer_url: str,
        target: Path,
        *,
        viewer_response: requests.Response | None = None,
    ) -> None:
        if viewer_response is None:
            viewer_response = session.get(viewer_url, timeout=self.REQUEST_TIMEOUT)
            viewer_response.raise_for_status()

        final_viewer_url = self._response_url(viewer_response, viewer_url)
        properties = self._viewer_properties(viewer_response.text)
        derivate_url = properties.get("derivateURL")
        if not isinstance(derivate_url, str) or not derivate_url:
            raise ValueError("MyCoRe viewer has no derivateURL")
        derivate_url = urljoin(final_viewer_url, derivate_url)

        image_paths = []
        mets_url = properties.get("metsURL")
        if isinstance(mets_url, str) and mets_url:
            mets_response = session.get(
                urljoin(final_viewer_url, mets_url),
                timeout=self.REQUEST_TIMEOUT,
            )
            mets_response.raise_for_status()
            image_paths = self._mets_image_paths(mets_response.content)

        if not image_paths:
            start_file = self._start_file(properties)
            if start_file is not None:
                image_paths = [start_file]

        logger.info(
            "PapyrusPortal viewer contains %d image(s): %s",
            len(image_paths),
            final_viewer_url,
        )
        for image_path in image_paths:
            image_url = urljoin(derivate_url.rstrip("/") + "/", image_path.lstrip("/"))
            self._download_image(session, image_url, target)

    def download(self, url: str, target: Path) -> None:
        request_url = self._canonical_url(url)
        logger.info("Fetching PapyrusPortal record: %s", request_url)
        with requests.Session() as session:
            page_response = session.get(request_url, timeout=self.REQUEST_TIMEOUT)
            page_response.raise_for_status()
            final_url = self._response_url(page_response, request_url)

            if self._is_viewer_url(final_url):
                self._download_viewer(
                    session,
                    final_url,
                    target,
                    viewer_response=page_response,
                )
                logger.info("Completed PapyrusPortal viewer: %s", final_url)
                return

            viewer_urls = self._viewer_urls(page_response.text, final_url)
            logger.info(
                "PapyrusPortal record contains %d viewer(s): %s",
                len(viewer_urls),
                final_url,
            )
            for viewer_url in viewer_urls:
                self._download_viewer(session, viewer_url, target)
        logger.info("Completed PapyrusPortal record: %s", url)
