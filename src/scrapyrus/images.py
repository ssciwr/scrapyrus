from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from xml.etree import ElementTree

from tqdm import tqdm

from scrapyrus.hgv import iterate_hgv_triples


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
GRAPHIC_PATH = "./tei:text/tei:body/tei:div/tei:p/tei:figure/tei:graphic"
LOGGER_NAME = "scrapyrus.images"


logger = logging.getLogger(LOGGER_NAME)
logger.addHandler(logging.NullHandler())
logger.propagate = False


@contextmanager
def image_log_file(
    filename: str | Path,
    level: str | int,
) -> Iterator[None]:
    """Write image scraper logs to *filename* for the duration of the context."""

    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f"Unknown logging level: {level}")
    else:
        numeric_level = level

    handler = logging.FileHandler(filename, encoding="utf-8")
    handler.setLevel(numeric_level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    )
    previous_level = logger.level
    logger.setLevel(numeric_level)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()


class RateLimitedMixin:
    """Pace requests and track whether a scraper encountered a rate limit."""

    REQUEST_INTERVAL = 1.0
    _rate_limited = False
    _last_request_at: float | None = None

    def wait_for_request_slot(self) -> None:
        """Wait until the configured interval has passed since the last request."""

        now = time.monotonic()
        if self._last_request_at is not None:
            delay = self.REQUEST_INTERVAL - (now - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
        self._last_request_at = now

    def mark_rate_limited(self) -> None:
        """Make this scraper unavailable for the remainder of the run."""

        self._rate_limited = True

    def available(self) -> bool:
        """Return whether this scraper has not encountered a rate limit."""

        return not self._rate_limited


class ImageScraperBase:
    """Base class for image scrapers selected by source URL.

    Subclasses are registered in definition order. :func:`scrape_images`
    creates one instance of each registered subclass for the duration of a
    run, allowing scraper implementations to retain state between downloads.
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

    @classmethod
    def registered_scrapers(cls) -> tuple[type[ImageScraperBase], ...]:
        """Return registered scraper classes in responsibility-chain order."""

        return tuple(cls._scrapers)

    def responsible(self, url: str) -> bool:
        """Return whether this scraper can handle *url*."""

        raise NotImplementedError

    def available(self) -> bool:
        """Return whether this scraper is currently able to download images."""

        return True

    def resolve(self, url: str) -> str:
        """Return the URL that should be offered to the scraper chain.

        Downloading scrapers return *url* unchanged. Resolver scrapers return a
        different URL, which restarts selection at the beginning of the chain.
        """

        return url

    def download(self, url: str, target: Path) -> None:
        """Download images referenced by *url* into *target*."""

        raise NotImplementedError


@dataclass(frozen=True)
class _ImageDownload:
    hgv_id: str
    url: str
    target: Path
    scraper: ImageScraperBase


@dataclass
class _ScraperOutcomeCounts:
    scraped: int = 0
    existing: int = 0
    unavailable: int = 0
    errors: int = 0


class _ImageURLResolutionError(RuntimeError):
    """Report a failure while resolving an effective image URL."""

    def __init__(
        self,
        url: str,
        scraper: ImageScraperBase,
        message: str,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.scraper = scraper


def _responsible_scraper(
    url: str,
    scrapers: tuple[ImageScraperBase, ...],
) -> ImageScraperBase | None:
    """Return the first scraper responsible for *url*, if any."""

    return next(
        (candidate for candidate in scrapers if candidate.responsible(url)),
        None,
    )


def _resolve_scraper(
    url: str,
    scraper: ImageScraperBase,
    scrapers: tuple[ImageScraperBase, ...],
) -> tuple[str, ImageScraperBase | None]:
    """Resolve *url* and return its effective URL and responsible scraper."""

    effective_url = url
    seen_urls = {effective_url}

    while True:
        try:
            resolved_url = scraper.resolve(effective_url)
        except Exception as error:
            raise _ImageURLResolutionError(
                effective_url,
                scraper,
                f"{type(scraper).__name__} failed to resolve {effective_url}",
            ) from error

        if resolved_url == effective_url:
            return effective_url, scraper
        if not resolved_url:
            raise _ImageURLResolutionError(
                effective_url,
                scraper,
                f"{type(scraper).__name__} resolved {effective_url} to an empty URL",
            )
        if resolved_url in seen_urls:
            raise _ImageURLResolutionError(
                resolved_url,
                scraper,
                f"Image scraper URL resolution cycle detected at {resolved_url}",
            )

        logger.info(
            "Image scraper %s resolved %s to %s",
            type(scraper).__name__,
            effective_url,
            resolved_url,
        )
        seen_urls.add(resolved_url)
        effective_url = resolved_url

        next_scraper = _responsible_scraper(effective_url, scrapers)
        if next_scraper is None:
            return effective_url, None
        scraper = next_scraper


def _format_scraper_outcomes(
    outcomes: dict[type[ImageScraperBase], _ScraperOutcomeCounts],
) -> str:
    """Format outcome counts grouped by responsible scraper class."""

    if not outcomes:
        return "By scraper class: none"

    lines = ["By scraper class:"]
    for scraper_type, counts in sorted(
        outcomes.items(),
        key=lambda item: item[0].__name__,
    ):
        lines.append(
            f"  {scraper_type.__name__}: scraped: {counts.scraped}; "
            f"skipped because they exist: {counts.existing}; "
            f"skipped because unavailable: {counts.unavailable}; "
            f"errors: {counts.errors}"
        )
    return "\n".join(lines)


def scrape_images(
    target: Path,
    todo_filename: str | Path,
    error_filename: str | Path,
    unavailable_filename: str | Path,
    *,
    idp_data: str | Path = Path("idp.data"),
) -> None:
    """Download images referenced by all HGV metadata records.

    Each HGV record is downloaded into its own directory below *target*.
    Unknown image sources are written to *todo_filename*, one per line in
    ``HGV_ID: URL`` form. Sources whose download fails are written in the same
    form to *error_filename*. Resolver scrapers replace source URLs before
    responsibility is checked again, and these effective URLs are used in the
    todo and error files. A download that returns without writing an image file
    is also treated as a failure. Sources already listed there are not retried.
    Temporarily unavailable sources are skipped and written in the same form to
    *unavailable_filename*. Existing HGV directories are left untouched. A
    summary of scraped, skipped, and failed image references, followed by the
    class-level spread of outcomes that have a responsible scraper, is printed
    after processing.
    """

    logger.info("Starting image scrape: target=%s idp_data=%s", target, idp_data)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)
    error_path = Path(error_filename)
    unavailable_path = Path(unavailable_filename)
    existing_error_text = (
        error_path.read_text(encoding="utf-8") if error_path.exists() else ""
    )
    existing_errors = set(existing_error_text.splitlines())
    error_separator = (
        "\n"
        if existing_error_text and not existing_error_text.endswith(("\n", "\r"))
        else ""
    )
    scraped_count = 0
    existing_count = 0
    no_responsible_scraper_count = 0
    unavailable_scraper_count = 0
    error_count = 0
    outcomes_by_scraper: dict[
        type[ImageScraperBase],
        _ScraperOutcomeCounts,
    ] = {}
    downloads: list[_ImageDownload] = []
    scrapers = tuple(
        scraper_type() for scraper_type in ImageScraperBase.registered_scrapers()
    )

    with (
        todo_path.open("w", encoding="utf-8") as todo_file,
        error_path.open("a", encoding="utf-8") as error_file,
        unavailable_path.open("w", encoding="utf-8") as unavailable_file,
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
                for graphic in graphics:
                    url = graphic.get("url")
                    if not url:
                        continue
                    scraper = _responsible_scraper(url, scrapers)
                    if scraper is not None:
                        outcomes_by_scraper.setdefault(
                            type(scraper),
                            _ScraperOutcomeCounts(),
                        ).existing += 1
                logger.debug(
                    "Skipping %d existing image reference(s) for HGV %s",
                    len(graphics),
                    hgv_id,
                )
                continue

            for graphic in graphics:
                url = graphic.get("url")
                if not url:
                    continue
                source_error_entry = f"{hgv_id}: {url}"
                if source_error_entry in existing_errors:
                    logger.debug("Skipping known error: %s", source_error_entry)
                    continue

                scraper = _responsible_scraper(url, scrapers)
                if scraper is None:
                    no_responsible_scraper_count += 1
                    todo_file.write(f"{hgv_id}: {url}\n")
                    logger.warning(
                        "No image scraper is responsible for HGV %s: %s",
                        hgv_id,
                        url,
                    )
                    continue

                downloads.append(
                    _ImageDownload(
                        hgv_id,
                        url,
                        papyrus_target,
                        scraper,
                    )
                )

        for download in tqdm(
            downloads,
            total=len(downloads),
            unit="image",
            desc="Downloading images",
        ):
            try:
                effective_url, scraper = _resolve_scraper(
                    download.url,
                    download.scraper,
                    scrapers,
                )
            except _ImageURLResolutionError as error:
                error_entry = f"{download.hgv_id}: {error.url}"
                if error_entry in existing_errors:
                    logger.debug("Skipping known error: %s", error_entry)
                    continue
                error_count += 1
                outcomes_by_scraper.setdefault(
                    type(error.scraper),
                    _ScraperOutcomeCounts(),
                ).errors += 1
                error_file.write(f"{error_separator}{error_entry}\n")
                error_separator = ""
                existing_errors.add(error_entry)
                logger.exception(
                    "Image URL resolution failed for HGV %s: %s",
                    download.hgv_id,
                    error.url,
                )
                continue

            error_entry = f"{download.hgv_id}: {effective_url}"
            if error_entry in existing_errors:
                logger.debug("Skipping known error: %s", error_entry)
                continue

            if scraper is None:
                no_responsible_scraper_count += 1
                todo_file.write(f"{download.hgv_id}: {effective_url}\n")
                logger.warning(
                    "No image scraper is responsible for HGV %s: %s",
                    download.hgv_id,
                    effective_url,
                )
                continue

            if not scraper.available():
                unavailable_scraper_count += 1
                outcomes_by_scraper.setdefault(
                    type(scraper),
                    _ScraperOutcomeCounts(),
                ).unavailable += 1
                unavailable_file.write(f"{download.hgv_id}: {effective_url}\n")
                logger.warning(
                    "Image scraper %s is unavailable; skipping HGV %s: %s",
                    type(scraper).__name__,
                    download.hgv_id,
                    effective_url,
                )
                continue
            download.target.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Downloading HGV %s with %s: %s",
                download.hgv_id,
                type(scraper).__name__,
                effective_url,
            )
            try:
                scraper.download(effective_url, download.target)
                if not any(path.is_file() for path in download.target.iterdir()):
                    raise RuntimeError(
                        f"{type(scraper).__name__}.download did not write any images"
                    )
            except Exception:
                try:
                    download.target.rmdir()
                except OSError:
                    pass
                error_count += 1
                outcomes_by_scraper.setdefault(
                    type(scraper),
                    _ScraperOutcomeCounts(),
                ).errors += 1
                error_file.write(
                    f"{error_separator}{download.hgv_id}: {effective_url}\n"
                )
                error_separator = ""
                logger.exception(
                    "Image download failed for HGV %s with %s: %s",
                    download.hgv_id,
                    type(scraper).__name__,
                    effective_url,
                )
            else:
                scraped_count += 1
                outcomes_by_scraper.setdefault(
                    type(scraper),
                    _ScraperOutcomeCounts(),
                ).scraped += 1
                logger.info("Downloaded HGV %s: %s", download.hgv_id, effective_url)

    summary = (
        f"Images scraped: {scraped_count}; "
        f"skipped because they exist: {existing_count}; "
        "skipped because no scraper was responsible: "
        f"{no_responsible_scraper_count}; "
        "skipped because the responsible scraper was unavailable: "
        f"{unavailable_scraper_count}; "
        f"errors: {error_count}"
    )
    report = f"{summary}\n{_format_scraper_outcomes(outcomes_by_scraper)}"
    logger.info(report)
    print(report)


# Import built-in scrapers after defining the base class so subclasses register.
from scrapyrus import scrapers as _scrapers  # noqa: E402, F401
