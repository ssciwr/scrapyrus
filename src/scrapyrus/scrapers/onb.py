import logging
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapyrus.images import RateLimitedMixin
from scrapyrus.scrapers.iiif import IIIFImageScraper


logger = logging.getLogger("scrapyrus.images.scrapers.onb")


class ONBScraper(
    RateLimitedMixin,
    IIIFImageScraper,
):
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
    FULL_DIGITIZATION_LABELS = ("Volldigitalisat", "Digitales Objekt")
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

    def download(self, url: str, target: Path) -> None:
        logger.info("Starting ONB download: %s", url)
        try:
            super().download(url, target)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 429:
                self.mark_rate_limited()
                logger.warning(
                    "ONB rate limit triggered by HTTP 429 for %s (response URL: %s)",
                    url,
                    error.response.url or url,
                )
            raise
        logger.info("Completed ONB download: %s", url)

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
            if (
                label in cls.FULL_DIGITIZATION_LABELS
                and isinstance(link_url, str)
                and link_url
            ):
                return urljoin(page_url, link_url)
        raise ValueError("ONB Primo record has no full-digitization link")

    @classmethod
    def _full_digitization_url(
        cls,
        session: requests.Session,
        page_response: requests.Response,
        requested_url: str,
    ) -> str:
        page_url = cls._response_url(page_response, requested_url)
        for label in cls.FULL_DIGITIZATION_LABELS:
            link_url = cls._link_url_by_text(
                page_response.text,
                page_url,
                label,
            )
            if link_url is not None:
                logger.debug("Found ONB %r link: %s", label, link_url)
                return link_url
        if urlparse(page_url).hostname == "search.onb.ac.at":
            return cls._primo_full_digitization_url(session, page_url)
        raise ValueError("ONB record has no full-digitization link")

    def manifest_urls(self, url: str, session: requests.Session) -> list[str]:
        direct_manifest_url = self._manifest_url_from_direct_url(url)
        if direct_manifest_url is not None:
            return [direct_manifest_url]

        page_response = session.get(url, timeout=self.REQUEST_TIMEOUT)
        page_response.raise_for_status()
        page_url = self._response_url(page_response, url)

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
                url,
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
