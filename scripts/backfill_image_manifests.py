# Used to add scrape manifests to a TM image tree migrated from HGV directories.

"""Backfill image scrape manifests for a TM image directory tree."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from tqdm import tqdm

from scrapyrus.idpdata import trismegistos_id
from scrapyrus.image_manifest import (
    IMAGE_MANIFEST_FILENAME,
    file_sha256,
    record_image_manifest_entry,
)


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
GRAPHIC_PATH = ".//tei:graphic"


@dataclass(frozen=True)
class HGVImageRecord:
    tm_id: str
    urls: tuple[str, ...]


@dataclass
class BackfillSummary:
    hgv_directories: int = 0
    manifest_entries: int = 0
    missing_metadata: int = 0
    missing_tm_directories: int = 0
    directories_without_files: int = 0
    records_without_urls: int = 0


def backfill_image_manifests(
    idp_data: str | Path,
    hgv_images: str | Path,
    tm_images: str | Path,
    *,
    progressbar: bool = True,
) -> BackfillSummary:
    """Write manifests into *tm_images* based on scraped *hgv_images*."""

    idp_data = Path(idp_data)
    hgv_images = Path(hgv_images)
    tm_images = Path(tm_images)
    if not hgv_images.is_dir():
        raise NotADirectoryError(hgv_images)
    if not tm_images.is_dir():
        raise NotADirectoryError(tm_images)

    hgv_records = _hgv_image_records(idp_data)
    summary = BackfillSummary()
    source_directories = sorted(path for path in hgv_images.iterdir() if path.is_dir())
    iterator = (
        tqdm(
            source_directories,
            total=len(source_directories),
            unit="record",
            desc="Backfilling image manifests",
        )
        if progressbar
        else source_directories
    )

    for source_directory in iterator:
        summary.hgv_directories += 1
        hgv_id = source_directory.name
        record = hgv_records.get(hgv_id)
        if record is None:
            summary.missing_metadata += 1
            continue
        if not record.urls:
            summary.records_without_urls += 1
            continue

        target_directory = tm_images / record.tm_id
        if not target_directory.is_dir():
            summary.missing_tm_directories += 1
            continue

        target_files = _target_files_for_hgv_directory(
            source_directory,
            target_directory,
        )
        if not target_files:
            summary.directories_without_files += 1
            continue

        for url in record.urls:
            if record_image_manifest_entry(
                target_directory,
                source_url=url,
                effective_url=url,
                scraper="backfill",
                files=target_files,
                source_ids=[hgv_id],
            ):
                summary.manifest_entries += 1

    return summary


def _hgv_image_records(idp_data: Path) -> dict[str, HGVImageRecord]:
    metadata_root = idp_data / "HGV_meta_EpiDoc"
    if not metadata_root.is_dir():
        raise NotADirectoryError(metadata_root)

    records = {}
    for metadata in sorted(metadata_root.glob("HGV*/*.xml")):
        urls = _image_urls(metadata)
        records[metadata.stem] = HGVImageRecord(
            tm_id=trismegistos_id(metadata),
            urls=tuple(urls),
        )
    return records


def _image_urls(metadata: Path) -> list[str]:
    root = ElementTree.parse(metadata).getroot()
    return [
        url
        for graphic in root.findall(
            GRAPHIC_PATH,
            namespaces={"tei": TEI_NAMESPACE},
        )
        if (url := graphic.get("url"))
    ]


def _target_files_for_hgv_directory(
    source_directory: Path,
    target_directory: Path,
) -> list[Path]:
    target_index = _target_file_index(target_directory)
    target_files: set[Path] = set()
    for source_file in sorted(
        path
        for path in source_directory.rglob("*")
        if path.is_file() and path.name != IMAGE_MANIFEST_FILENAME
    ):
        relative_path = source_file.relative_to(source_directory)
        file_key = (source_file.stat().st_size, file_sha256(source_file))
        matching_target = _find_matching_target_file(
            target_directory,
            target_index,
            relative_path,
            file_key,
        )
        if matching_target is not None:
            target_files.add(matching_target)
    return sorted(target_files)


def _target_file_index(
    target_directory: Path,
) -> dict[tuple[int, str], list[Path]]:
    by_content: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for target_file in sorted(
        path
        for path in target_directory.rglob("*")
        if path.is_file() and path.name != IMAGE_MANIFEST_FILENAME
    ):
        relative_path = target_file.relative_to(target_directory)
        by_content[(target_file.stat().st_size, file_sha256(target_file))].append(
            relative_path
        )
    return by_content


def _find_matching_target_file(
    target_directory: Path,
    target_index: dict[tuple[int, str], list[Path]],
    source_relative_path: Path,
    file_key: tuple[int, str],
) -> Path | None:
    same_name = target_directory / source_relative_path
    if (
        same_name.is_file()
        and same_name.stat().st_size == file_key[0]
        and file_sha256(same_name) == file_key[1]
    ):
        return source_relative_path

    same_directory_matches = [
        path
        for path in target_index.get(file_key, [])
        if path.parent == source_relative_path.parent
    ]
    if same_directory_matches:
        return sorted(same_directory_matches)[0]

    matches = target_index.get(file_key, [])
    return sorted(matches)[0] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--idp-data",
        type=Path,
        default=Path("idp.data"),
        help="Path to the idp.data repository clone",
    )
    parser.add_argument(
        "hgv_images",
        type=Path,
        help="Existing image tree whose first-level directories are HGV IDs",
    )
    parser.add_argument(
        "tm_images",
        type=Path,
        help="Existing image tree whose first-level directories are TM IDs",
    )
    arguments = parser.parse_args()

    summary = backfill_image_manifests(
        arguments.idp_data,
        arguments.hgv_images,
        arguments.tm_images,
    )
    print(f"Processed {summary.hgv_directories} HGV image directories")
    print(f"Wrote {summary.manifest_entries} manifest entries")
    print(f"Missing metadata: {summary.missing_metadata}")
    print(f"Records without URLs: {summary.records_without_urls}")
    print(f"Missing TM directories: {summary.missing_tm_directories}")
    print(f"Directories without matched files: {summary.directories_without_files}")


if __name__ == "__main__":
    main()
