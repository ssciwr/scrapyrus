import json
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from scrapyrus.images import ImageScraperBase


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

    def manifest_urls(self, url: str, session: requests.Session) -> list[str]:
        """Return IIIF Presentation manifest URLs for *url*."""

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

    def download(self, url: str, target: Path) -> None:
        with requests.Session() as session:
            image_urls = []
            for manifest_url in self.manifest_urls(url, session):
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
