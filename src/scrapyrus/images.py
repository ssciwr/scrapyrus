from __future__ import annotations

import json
import re
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from scrapyrus.hgv import iterate_hgv_triples


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
GRAPHIC_PATH = "./tei:text/tei:body/tei:div/tei:p/tei:figure/tei:graphic"
METS_NAMESPACE = "http://www.loc.gov/METS/"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"


class ImageScraperBase:
    """Base class for image scrapers selected by source URL.

    Subclasses are registered in definition order. A scraper instance retains
    the URL it was created for so its :meth:`download` implementation only
    needs the requested target path.
    """

    _scrapers: ClassVar[list[type[ImageScraperBase]]] = []

    def __init_subclass__(
        cls,
        *,
        register: bool = True,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if register:
            ImageScraperBase._scrapers.append(cls)

    def __init__(self, url: str) -> None:
        self.url = url

    @classmethod
    def registered_scrapers(cls) -> tuple[type[ImageScraperBase], ...]:
        """Return registered scraper classes in responsibility-chain order."""

        return tuple(cls._scrapers)

    def responsible(self, url: str) -> bool:
        """Return whether this scraper can handle *url*."""

        raise NotImplementedError

    def download(self, target: Path) -> None:
        """Download the image for this scraper's URL into *target*."""

        raise NotImplementedError


class IIIFImageScraper(ImageScraperBase, register=False):
    """Download canvas images from IIIF Presentation 2 and 3 manifests.

    Server-specific subclasses only need to decide which URLs they handle and
    turn a source URL into one or more manifest URLs.
    """

    REQUEST_TIMEOUT = 30
    IMAGE_SUFFIXES = frozenset(
        {
            ".bmp",
            ".gif",
            ".jp2",
            ".jpeg",
            ".jpg",
            ".png",
            ".tif",
            ".tiff",
            ".webp",
        }
    )

    def manifest_urls(self, session: requests.Session) -> list[str]:
        """Return IIIF Presentation manifest URLs for this scraper's source."""

        raise NotImplementedError

    @staticmethod
    def _body_image_url(body: object, *, presentation_version: int) -> str | None:
        if not isinstance(body, dict):
            return None

        body_type = body.get("type") or body.get("@type")
        if body_type == "Choice":
            choices = body.get("items") or body.get("default")
            if not isinstance(choices, list):
                choices = [choices]
            for choice in choices:
                image_url = IIIFImageScraper._body_image_url(
                    choice,
                    presentation_version=presentation_version,
                )
                if image_url is not None:
                    return image_url
            return None

        image_url = body.get("id") or body.get("@id")
        if isinstance(image_url, str) and image_url:
            return image_url

        services = body.get("service")
        if not isinstance(services, list):
            services = [services]
        for service in services:
            if not isinstance(service, dict):
                continue
            service_url = service.get("id") or service.get("@id")
            if not isinstance(service_url, str) or not service_url:
                continue
            size = "max" if presentation_version == 3 else "full"
            return f"{service_url.rstrip('/')}/full/{size}/0/default.jpg"
        return None

    @classmethod
    def _presentation_3_image_urls(cls, manifest: dict[str, object]) -> list[str]:
        image_urls = []
        canvases = manifest.get("items")
        if not isinstance(canvases, list):
            return image_urls

        for canvas in canvases:
            if not isinstance(canvas, dict):
                continue
            annotation_pages = canvas.get("items")
            if not isinstance(annotation_pages, list):
                continue
            for annotation_page in annotation_pages:
                if not isinstance(annotation_page, dict):
                    continue
                annotations = annotation_page.get("items")
                if not isinstance(annotations, list):
                    continue
                for annotation in annotations:
                    if not isinstance(annotation, dict):
                        continue
                    motivation = annotation.get("motivation")
                    if motivation not in {None, "painting"}:
                        continue
                    bodies = annotation.get("body")
                    if not isinstance(bodies, list):
                        bodies = [bodies]
                    for body in bodies:
                        image_url = cls._body_image_url(
                            body,
                            presentation_version=3,
                        )
                        if image_url is not None:
                            image_urls.append(image_url)
        return image_urls

    @classmethod
    def _presentation_2_image_urls(cls, manifest: dict[str, object]) -> list[str]:
        image_urls = []
        sequences = manifest.get("sequences")
        if not isinstance(sequences, list):
            return image_urls

        for sequence in sequences:
            if not isinstance(sequence, dict):
                continue
            canvases = sequence.get("canvases")
            if not isinstance(canvases, list):
                continue
            for canvas in canvases:
                if not isinstance(canvas, dict):
                    continue
                annotations = canvas.get("images")
                if not isinstance(annotations, list):
                    continue
                for annotation in annotations:
                    if not isinstance(annotation, dict):
                        continue
                    image_url = cls._body_image_url(
                        annotation.get("resource"),
                        presentation_version=2,
                    )
                    if image_url is not None:
                        image_urls.append(image_url)
        return image_urls

    @classmethod
    def _manifest_image_urls(cls, manifest: object) -> list[str]:
        if not isinstance(manifest, dict):
            raise ValueError("IIIF manifest must be a JSON object")

        manifest_type = manifest.get("type") or manifest.get("@type")
        if manifest_type not in {"Manifest", "sc:Manifest"}:
            raise ValueError("IIIF Presentation manifest expected")

        if manifest_type == "Manifest":
            image_urls = cls._presentation_3_image_urls(manifest)
        else:
            image_urls = cls._presentation_2_image_urls(manifest)

        return list(dict.fromkeys(image_urls))

    @classmethod
    def _image_suffix(cls, image_url: str) -> str:
        suffix = Path(unquote(urlparse(image_url).path)).suffix.lower()
        if suffix in cls.IMAGE_SUFFIXES:
            return suffix
        return ".jpg"

    @staticmethod
    def _response_json(response: requests.Response) -> object:
        try:
            return response.json()
        except (AttributeError, requests.exceptions.JSONDecodeError):
            return json.loads(response.text)

    def download(self, target: Path) -> None:
        with requests.Session() as session:
            image_urls = []
            for manifest_url in self.manifest_urls(session):
                manifest_response = session.get(
                    manifest_url,
                    timeout=self.REQUEST_TIMEOUT,
                )
                manifest_response.raise_for_status()
                image_urls.extend(
                    self._manifest_image_urls(self._response_json(manifest_response))
                )

            for image_number, image_url in enumerate(
                dict.fromkeys(image_urls),
                start=1,
            ):
                parsed_url = urlparse(image_url)
                if parsed_url.scheme not in {"http", "https"}:
                    raise ValueError(f"Unsupported IIIF image URL: {image_url}")
                filename = f"{image_number:04d}{self._image_suffix(image_url)}"
                with session.get(
                    image_url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True,
                ) as image_response:
                    image_response.raise_for_status()
                    with (target / filename).open("wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=64 * 1024):
                            image_file.write(chunk)


class OesterreichischeNationalbibliothekScraper(IIIFImageScraper):
    """Find and download IIIF images exposed by Austrian National Library pages."""

    SOURCE_HOSTS = frozenset(
        {
            "api.onb.ac.at",
            "data.onb.ac.at",
            "digital.onb.ac.at",
            "onb.digital",
            "search.onb.ac.at",
            "viewer.onb.ac.at",
        }
    )
    MANIFEST_ROOT = "https://api.onb.ac.at/iiif/presentation/v3/manifest/"
    LINK_LABEL = "Volldigitalisat"
    DIGITALISAT_LABEL = "Zum Digitalisat"

    @staticmethod
    def _path_starts_with(path: str, prefix: str) -> bool:
        return path == prefix or path.startswith(prefix + "/")

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            return False
        if parsed_url.hostname not in self.SOURCE_HOSTS:
            return False
        return (
            (
                parsed_url.hostname == "data.onb.ac.at"
                and self._path_starts_with(parsed_url.path, "/rec")
            )
            or (
                parsed_url.hostname == "data.onb.ac.at"
                and self._path_starts_with(parsed_url.path, "/rep")
            )
            or (
                parsed_url.hostname == "onb.digital"
                and self._path_starts_with(parsed_url.path, "/result")
            )
            or (
                parsed_url.hostname == "digital.onb.ac.at"
                and self._path_starts_with(parsed_url.path, "/rep/access/open")
            )
            or parsed_url.hostname == "viewer.onb.ac.at"
            or (
                parsed_url.hostname == "search.onb.ac.at"
                and self._path_starts_with(
                    parsed_url.path,
                    "/primo-explore/fulldisplay",
                )
            )
            or (
                parsed_url.hostname == "api.onb.ac.at"
                and self._path_starts_with(
                    parsed_url.path,
                    "/iiif/presentation/v3/manifest",
                )
            )
        )

    @staticmethod
    def _response_url(response: requests.Response, fallback: str) -> str:
        return response.url or fallback

    @staticmethod
    def _link_url_by_text(html: str, page_url: str, label: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a", href=True):
            if link.get_text(" ", strip=True) == label:
                return urljoin(page_url, link["href"])
        return None

    @classmethod
    def _digitalisat_url(cls, html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        link = soup.select_one("a#Digitalisat[href]")
        if link is not None:
            return urljoin(page_url, link["href"])

        link_url = cls._link_url_by_text(html, page_url, cls.DIGITALISAT_LABEL)
        if link_url is None:
            raise ValueError("ONB page has no 'Zum Digitalisat' link")
        return link_url

    @classmethod
    def _manifest_url_from_direct_url(cls, url: str) -> str | None:
        parsed_url = urlparse(url)
        if parsed_url.hostname == "api.onb.ac.at" and cls._path_starts_with(
            parsed_url.path,
            "/iiif/presentation/v3/manifest",
        ):
            return url

        identifier = None
        if parsed_url.hostname == "viewer.onb.ac.at":
            identifier = parsed_url.path.strip("/").split("/", 1)[0]
        elif parsed_url.hostname == "digital.onb.ac.at" and cls._path_starts_with(
            parsed_url.path,
            "/rep/access/open",
        ):
            identifier = parsed_url.path.rstrip("/").rpartition("/")[2]

        if not identifier:
            return None
        return cls.MANIFEST_ROOT + quote(unquote(identifier), safe="")

    @classmethod
    def _primo_full_digitization_url(
        cls,
        session: requests.Session,
        page_url: str,
    ) -> str:
        parsed_url = urlparse(page_url)
        query = parse_qs(parsed_url.query)

        def query_value(name: str, default: str = "") -> str:
            values = query.get(name)
            return values[0] if values else default

        document_id = query_value("docid")
        view_id = query_value("vid", "ONB")
        language = query_value("lang", "de_DE")
        context = query_value("context", "L")
        if not document_id:
            raise ValueError("ONB Primo URL has no document ID")

        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        guest_response = session.get(
            f"{origin}/primo_library/libweb/webservices/rest/v1/guestJwt/{view_id}",
            params={
                "isGuest": "true",
                "lang": language,
                "targetUrl": quote(page_url, safe=""),
                "viewId": view_id,
            },
            timeout=cls.REQUEST_TIMEOUT,
        )
        guest_response.raise_for_status()
        token = cls._response_json(guest_response)
        if not isinstance(token, str) or not token:
            raise ValueError("ONB Primo guest token is missing")

        record_params = {"vid": view_id, "lang": language}
        for name in ("search_scope", "adaptor"):
            value = query_value(name)
            if value:
                record_params[name] = value
        record_response = session.get(
            f"{origin}/primo_library/libweb/webservices/rest/primo-explore/"
            f"v1/pnxs/{quote(context, safe='')}/{quote(document_id, safe='')}",
            params=record_params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=cls.REQUEST_TIMEOUT,
        )
        record_response.raise_for_status()
        record = cls._response_json(record_response)
        if not isinstance(record, dict):
            raise ValueError("ONB Primo record response is invalid")
        delivery = record.get("delivery")
        links = delivery.get("link") if isinstance(delivery, dict) else None
        if not isinstance(links, list):
            links = []
        for link in links:
            if not isinstance(link, dict):
                continue
            display_label = link.get("displayLabel")
            label = BeautifulSoup(str(display_label or ""), "html.parser").get_text(
                " ",
                strip=True,
            )
            link_url = link.get("linkURL")
            if label == cls.LINK_LABEL and isinstance(link_url, str) and link_url:
                return urljoin(page_url, link_url)
        raise ValueError("ONB Primo record has no 'Volldigitalisat' link")

    @classmethod
    def _full_digitization_url(
        cls,
        session: requests.Session,
        page_response: requests.Response,
        requested_url: str,
    ) -> str:
        page_url = cls._response_url(page_response, requested_url)
        link_url = cls._link_url_by_text(
            page_response.text,
            page_url,
            cls.LINK_LABEL,
        )
        if link_url is not None:
            return link_url
        if urlparse(page_url).hostname == "search.onb.ac.at":
            return cls._primo_full_digitization_url(session, page_url)
        raise ValueError("ONB record has no 'Volldigitalisat' link")

    def manifest_urls(self, session: requests.Session) -> list[str]:
        direct_manifest_url = self._manifest_url_from_direct_url(self.url)
        if direct_manifest_url is not None:
            return [direct_manifest_url]

        page_response = session.get(self.url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()
        page_url = self._response_url(page_response, self.url)

        direct_manifest_url = self._manifest_url_from_direct_url(page_url)
        if direct_manifest_url is not None:
            return [direct_manifest_url]

        parsed_page_url = urlparse(page_url)
        if parsed_page_url.hostname == "onb.digital" and self._path_starts_with(
            parsed_page_url.path, "/result"
        ):
            result_response = page_response
        else:
            full_digitization_url = self._full_digitization_url(
                session,
                page_response,
                self.url,
            )
            direct_manifest_url = self._manifest_url_from_direct_url(
                full_digitization_url
            )
            if direct_manifest_url is not None:
                return [direct_manifest_url]
            result_response = session.get(
                full_digitization_url,
                timeout=self.REQUEST_TIMEOUT,
            )
            result_response.raise_for_status()

        result_url = self._response_url(result_response, page_url)
        direct_manifest_url = self._manifest_url_from_direct_url(result_url)
        if direct_manifest_url is not None:
            return [direct_manifest_url]
        digitalisat_url = self._digitalisat_url(result_response.text, result_url)
        manifest_url = self._manifest_url_from_direct_url(digitalisat_url)
        if manifest_url is None:
            raise ValueError(f"Unsupported ONB digitalisat URL: {digitalisat_url}")
        return [manifest_url]


class BerlPapScraper(ImageScraperBase):
    """Download full-resolution images from the Berliner Papyrusdatenbank."""

    HOST = "berlpap.smb.museum"
    REQUEST_TIMEOUT = 30

    def responsible(self, url: str) -> bool:
        parsed_url = urlparse(url)
        return parsed_url.scheme in {"http", "https"} and parsed_url.netloc == self.HOST

    def _image_urls(self, html: str) -> list[str]:
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
            image_url = urljoin(self.url, link["href"])
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

    def download(self, target: Path) -> None:
        page_response = requests.get(self.url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()

        for image_url in self._image_urls(page_response.text):
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
        root = ElementTree.fromstring(mets)
        files_by_use: dict[str, list[tuple[str | None, str]]] = {
            use: [] for use in cls.IMAGE_USES
        }

        for file_group in root.findall(f".//{{{METS_NAMESPACE}}}fileGrp"):
            use = (file_group.get("USE") or "").upper()
            if use not in files_by_use:
                continue
            for file_element in file_group.findall(f"{{{METS_NAMESPACE}}}file"):
                location = file_element.find(f"{{{METS_NAMESPACE}}}FLocat")
                if location is None:
                    continue
                href = location.get(f"{{{XLINK_NAMESPACE}}}href") or location.get(
                    "href"
                )
                if not href:
                    continue
                mime_type = (file_element.get("MIMETYPE") or "").lower()
                suffix = Path(unquote(urlparse(href).path)).suffix.lower()
                if mime_type and not mime_type.startswith("image/"):
                    continue
                if not mime_type and suffix not in cls.IMAGE_SUFFIXES:
                    continue
                files_by_use[use].append((file_element.get("ID"), href))

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
                for struct_map in root.findall(f".//{{{METS_NAMESPACE}}}structMap")
                if (struct_map.get("TYPE") or "").upper() == "PHYSICAL"
            ),
            None,
        )
        if physical_map is not None:
            for element in physical_map.iter():
                if element.tag.rpartition("}")[2] not in {"fptr", "area"}:
                    continue
                for file_id in (element.get("FILEID") or "").split():
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

        for image_path in image_paths:
            image_url = urljoin(derivate_url.rstrip("/") + "/", image_path.lstrip("/"))
            self._download_image(session, image_url, target)

    def download(self, target: Path) -> None:
        with requests.Session() as session:
            page_response = session.get(self.url, timeout=self.REQUEST_TIMEOUT)
            page_response.raise_for_status()
            final_url = self._response_url(page_response, self.url)

            if self._is_viewer_url(final_url):
                self._download_viewer(
                    session,
                    final_url,
                    target,
                    viewer_response=page_response,
                )
                return

            for viewer_url in self._viewer_urls(page_response.text, final_url):
                self._download_viewer(session, viewer_url, target)


def scrape_images(
    target: Path,
    todo_filename: str | Path,
    error_filename: str | Path,
    *,
    idp_data: str | Path = Path("idp.data"),
) -> None:
    """Download images referenced by all HGV metadata records.

    Each HGV record is downloaded into its own directory below *target*.
    Unknown image sources are written to *todo_filename*, one per line in
    ``HGV_ID: URL`` form. Sources whose download fails are written in the same
    form to *error_filename*. Existing HGV directories are left untouched.
    A summary of scraped, skipped, and failed image references is printed after
    processing.
    """

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)
    error_path = Path(error_filename)
    scraped_count = 0
    existing_count = 0
    no_scraper_count = 0
    error_count = 0

    with (
        todo_path.open("w", encoding="utf-8") as todo_file,
        error_path.open("w", encoding="utf-8") as error_file,
    ):
        for hgv_id, metadata, _, _ in iterate_hgv_triples(idp_data):
            root = ElementTree.parse(metadata).getroot()
            graphics = root.findall(
                GRAPHIC_PATH,
                namespaces={"tei": TEI_NAMESPACE},
            )
            papyrus_target = target / hgv_id
            if graphics and papyrus_target.exists():
                existing_count += len(graphics)
                continue

            for graphic in graphics:
                url = graphic.get("url")
                if not url:
                    continue

                for scraper_type in ImageScraperBase.registered_scrapers():
                    scraper = scraper_type(url)
                    if scraper.responsible(url):
                        papyrus_target.mkdir(parents=True, exist_ok=True)
                        try:
                            scraper.download(papyrus_target)
                        except Exception:
                            try:
                                papyrus_target.rmdir()
                            except OSError:
                                pass
                            error_count += 1
                            error_file.write(f"{hgv_id}: {url}\n")
                        else:
                            scraped_count += 1
                        break
                else:
                    no_scraper_count += 1
                    todo_file.write(f"{hgv_id}: {url}\n")

    print(
        f"Images scraped: {scraped_count}; "
        f"skipped because they exist: {existing_count}; "
        f"skipped because no scraper was available: {no_scraper_count}; "
        f"errors: {error_count}"
    )
