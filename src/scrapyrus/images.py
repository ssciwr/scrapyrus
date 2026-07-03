from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from xml.etree import ElementTree

from termgraph import Args, Data, StackedChart
from tqdm import tqdm

from scrapyrus.image_manifest import (
    file_snapshot,
    manifest_has_completed_source,
    record_image_manifest_entry,
)
from scrapyrus.idpdata import iterate_idpdata_triples


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
GRAPHIC_PATH = ".//tei:graphic"
LOGGER_NAME = "scrapyrus.images"
REPORT_WIDTH = 50
REPORT_CATEGORIES = [
    "already present",
    "downloaded on this run",
    "skipped for unavailability",
    "failed on this run",
    "permanently reported as broken",
]
REPORT_COLORS = [
    "38;2;144;238;144",  # light green
    "38;2;0;255;0",  # bright green
    "38;2;173;216;230",  # light blue
    "38;2;255;0;0",  # bright red
    "38;2;255;127;127",  # light red
]
DEFAULT_BROKEN_IMAGE_FILE = Path(__file__).with_name("images_broken.txt")


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
    tm_id: str
    source_id: str
    url: str
    target: Path
    scraper: ImageScraperBase


@dataclass
class _ScraperOutcomeCounts:
    already_present: int = 0
    downloaded: int = 0
    unavailable: int = 0
    failed: int = 0
    broken: int = 0

    def values(self) -> list[int]:
        """Return counts in the same order as the report categories."""

        return [
            self.already_present,
            self.downloaded,
            self.unavailable,
            self.failed,
            self.broken,
        ]


class _NormalizedStackedData(Data):
    """Termgraph data that normalizes every stacked row independently."""

    def normalize(self, width: int) -> list[list[int]]:
        return [_normalized_widths(row, width) for row in self.data]


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


def _normalized_widths(counts: list[int], width: int) -> list[int]:
    """Apportion *width* cells while keeping every nonzero count visible."""

    positive_indices = [index for index, count in enumerate(counts) if count > 0]
    if not positive_indices:
        return [0] * len(counts)
    if width < len(positive_indices):
        raise ValueError("Chart width cannot show every nonzero category")

    widths = [0] * len(counts)
    for index in positive_indices:
        widths[index] = 1

    remaining_width = width - len(positive_indices)
    total = sum(counts[index] for index in positive_indices)
    quotas = [counts[index] * remaining_width / total for index in positive_indices]
    for index, quota in zip(positive_indices, quotas):
        widths[index] += math.floor(quota)

    unallocated = width - sum(widths)
    by_largest_remainder = sorted(
        zip(positive_indices, quotas),
        key=lambda item: (item[1] - math.floor(item[1]), -item[0]),
        reverse=True,
    )
    for index, _ in by_largest_remainder[:unallocated]:
        widths[index] += 1

    return widths


def _draw_scraper_outcomes(
    outcomes: dict[type[ImageScraperBase], _ScraperOutcomeCounts],
) -> None:
    """Draw normalized outcome counts grouped by responsible scraper class."""

    if not outcomes:
        print("No image records were handled by a scraper.")
        return

    sorted_outcomes = sorted(
        outcomes.items(),
        key=lambda item: item[0].__name__,
    )
    data = _NormalizedStackedData(
        data=[counts.values() for _, counts in sorted_outcomes],
        labels=[scraper_type.__name__ for scraper_type, _ in sorted_outcomes],
        categories=REPORT_CATEGORIES,
    )
    chart = StackedChart(
        data,
        Args(
            colors=REPORT_COLORS,
            format="{:.0f}",
            no_readable=True,
            stacked=True,
            width=REPORT_WIDTH,
        ),
    )
    chart.draw()


def _read_broken_image_entries(filename: Path) -> set[str]:
    """Read broken image entries, ignoring blank and comment lines."""

    if not filename.exists():
        return set()
    return {
        line
        for line in filename.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def scrape_images(
    target: Path,
    todo_filename: str | Path,
    error_filename: str | Path,
    unavailable_filename: str | Path,
    *,
    broken_filename: str | Path = DEFAULT_BROKEN_IMAGE_FILE,
    idp_data: str | Path = Path("idp.data"),
) -> None:
    """Download images referenced by all idp.data metadata records.

    Each TM record is downloaded into its own directory below *target*.
    Unknown image sources are written to *todo_filename*, one per line in
    ``TM_ID: URL`` form. Sources listed in *broken_filename* are not retried;
    blank lines and lines starting with ``#`` in that file are ignored.
    Sources whose download fails during this run are written in the same form
    to *error_filename*, replacing any previous contents. Resolver scrapers
    replace source URLs before responsibility is checked again, and these
    effective URLs are used in the todo, broken, and error file processing. A
    download that returns without writing an image file is also treated as a
    failure. Temporarily unavailable sources are skipped and written in the
    same form to *unavailable_filename*. Existing TM directories are reused so
    additional records for the same TM ID can add files there. A normalized
    stacked bar chart of outcomes by responsible scraper class is printed after
    processing.
    """

    logger.info("Starting image scrape: target=%s idp_data=%s", target, idp_data)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    todo_path = Path(todo_filename)
    broken_path = Path(broken_filename)
    error_path = Path(error_filename)
    unavailable_path = Path(unavailable_filename)
    known_broken = _read_broken_image_entries(broken_path)
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
        error_path.open("w", encoding="utf-8") as error_file,
        unavailable_path.open("w", encoding="utf-8") as unavailable_file,
    ):
        for tm_id, metadata, _, _ in iterate_idpdata_triples(idp_data):
            root = ElementTree.parse(metadata).getroot()
            graphics = root.findall(
                GRAPHIC_PATH,
                namespaces={"tei": TEI_NAMESPACE},
            )
            papyrus_target = target / tm_id
            for graphic in graphics:
                url = graphic.get("url")
                if not url:
                    continue
                source_entry = f"{tm_id}: {url}"
                scraper = _responsible_scraper(url, scrapers)
                if manifest_has_completed_source(papyrus_target, url):
                    if scraper is not None:
                        outcomes_by_scraper.setdefault(
                            type(scraper),
                            _ScraperOutcomeCounts(),
                        ).already_present += 1
                    logger.debug(
                        "Skipping already recorded image source for TM %s: %s",
                        tm_id,
                        url,
                    )
                    continue
                if source_entry in known_broken:
                    if scraper is not None:
                        outcomes_by_scraper.setdefault(
                            type(scraper),
                            _ScraperOutcomeCounts(),
                        ).broken += 1
                    logger.debug("Skipping known broken URL: %s", source_entry)
                    continue

                if scraper is None:
                    todo_file.write(f"{tm_id}: {url}\n")
                    logger.warning(
                        "No image scraper is responsible for TM %s: %s",
                        tm_id,
                        url,
                    )
                    continue

                downloads.append(
                    _ImageDownload(
                        tm_id,
                        metadata.stem,
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
                error_entry = f"{download.tm_id}: {error.url}"
                if error_entry in known_broken:
                    outcomes_by_scraper.setdefault(
                        type(error.scraper),
                        _ScraperOutcomeCounts(),
                    ).broken += 1
                    logger.debug("Skipping known broken URL: %s", error_entry)
                    continue
                outcomes_by_scraper.setdefault(
                    type(error.scraper),
                    _ScraperOutcomeCounts(),
                ).failed += 1
                error_file.write(f"{error_entry}\n")
                logger.exception(
                    "Image URL resolution failed for TM %s: %s",
                    download.tm_id,
                    error.url,
                )
                continue

            error_entry = f"{download.tm_id}: {effective_url}"
            if manifest_has_completed_source(
                download.target,
                download.url,
                effective_url,
            ):
                outcomes_by_scraper.setdefault(
                    type(scraper or download.scraper),
                    _ScraperOutcomeCounts(),
                ).already_present += 1
                logger.debug(
                    "Skipping already recorded image source for TM %s: %s",
                    download.tm_id,
                    effective_url,
                )
                continue

            if error_entry in known_broken:
                if scraper is not None:
                    outcomes_by_scraper.setdefault(
                        type(scraper),
                        _ScraperOutcomeCounts(),
                    ).broken += 1
                logger.debug("Skipping known broken URL: %s", error_entry)
                continue

            if scraper is None:
                todo_file.write(f"{download.tm_id}: {effective_url}\n")
                logger.warning(
                    "No image scraper is responsible for TM %s: %s",
                    download.tm_id,
                    effective_url,
                )
                continue

            if not scraper.available():
                outcomes_by_scraper.setdefault(
                    type(scraper),
                    _ScraperOutcomeCounts(),
                ).unavailable += 1
                unavailable_file.write(f"{download.tm_id}: {effective_url}\n")
                logger.warning(
                    "Image scraper %s is unavailable; skipping TM %s: %s",
                    type(scraper).__name__,
                    download.tm_id,
                    effective_url,
                )
                continue
            download.target.mkdir(parents=True, exist_ok=True)
            before_download = file_snapshot(download.target)
            logger.info(
                "Downloading TM %s with %s: %s",
                download.tm_id,
                type(scraper).__name__,
                effective_url,
            )
            try:
                scraper.download(effective_url, download.target)
                after_download = file_snapshot(download.target)
                if not after_download:
                    raise RuntimeError(
                        f"{type(scraper).__name__}.download did not leave any images"
                    )
            except Exception:
                try:
                    download.target.rmdir()
                except OSError:
                    pass
                outcomes_by_scraper.setdefault(
                    type(scraper),
                    _ScraperOutcomeCounts(),
                ).failed += 1
                error_file.write(f"{download.tm_id}: {effective_url}\n")
                logger.exception(
                    "Image download failed for TM %s with %s: %s",
                    download.tm_id,
                    type(scraper).__name__,
                    effective_url,
                )
            else:
                changed_files = [
                    path
                    for path, file_info in after_download.items()
                    if before_download.get(path) != file_info
                ]
                manifest_files = changed_files or list(after_download)
                record_image_manifest_entry(
                    download.target,
                    source_url=download.url,
                    effective_url=effective_url,
                    scraper=type(scraper).__name__,
                    files=manifest_files,
                    source_ids=[download.source_id],
                )
                outcome = outcomes_by_scraper.setdefault(
                    type(scraper),
                    _ScraperOutcomeCounts(),
                )
                if after_download == before_download:
                    outcome.already_present += 1
                    logger.info(
                        "No new image files for TM %s: %s",
                        download.tm_id,
                        effective_url,
                    )
                else:
                    outcome.downloaded += 1
                    logger.info("Downloaded TM %s: %s", download.tm_id, effective_url)

    logger.info("Image scrape outcomes by scraper: %s", outcomes_by_scraper)
    _draw_scraper_outcomes(outcomes_by_scraper)


# Import built-in scrapers after defining the base class so subclasses register.
from scrapyrus import scrapers as _scrapers  # noqa: E402, F401
