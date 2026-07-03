from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_MANIFEST_FILENAME = ".scrapyrus-images.json"
IMAGE_MANIFEST_VERSION = 1


def image_manifest_path(directory: Path) -> Path:
    """Return the image manifest path for a TM directory."""

    return directory / IMAGE_MANIFEST_FILENAME


def file_sha256(filename: Path) -> str:
    """Return the SHA-256 digest for *filename*."""

    digest = hashlib.sha256()
    with filename.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(directory: Path) -> dict[Path, tuple[int, int]]:
    """Return file sizes and modification times below *directory*."""

    if not directory.exists():
        return {}
    return {
        path.relative_to(directory): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in directory.rglob("*")
        if path.is_file() and path.name != IMAGE_MANIFEST_FILENAME
    }


def read_image_manifest(directory: Path) -> dict[str, Any]:
    """Return the image manifest for *directory*, or an empty manifest."""

    manifest_path = image_manifest_path(directory)
    if not manifest_path.exists():
        return _empty_manifest()

    with manifest_path.open(encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        return _empty_manifest()
    if manifest.get("version") != IMAGE_MANIFEST_VERSION:
        return _empty_manifest()
    if not isinstance(manifest.get("entries"), list):
        manifest["entries"] = []
    return manifest


def write_image_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    """Write *manifest* into *directory*."""

    directory.mkdir(parents=True, exist_ok=True)
    manifest["version"] = IMAGE_MANIFEST_VERSION
    manifest["entries"] = sorted(
        _manifest_entries(manifest),
        key=lambda entry: (
            str(entry.get("source_url", "")),
            str(entry.get("effective_url", "")),
        ),
    )
    manifest_path = image_manifest_path(directory)
    temporary_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
    temporary_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


def image_file_records(directory: Path, files: list[Path]) -> list[dict[str, Any]]:
    """Return manifest file records for relative *files* in *directory*."""

    records = []
    for relative_path in sorted(dict.fromkeys(files), key=str):
        if not _is_safe_relative_path(str(relative_path)):
            continue
        filename = directory / relative_path
        if not filename.is_file():
            continue
        stat = filename.stat()
        records.append(
            {
                "path": relative_path.as_posix(),
                "size": stat.st_size,
                "sha256": file_sha256(filename),
            }
        )
    return records


def manifest_has_completed_source(
    directory: Path,
    source_url: str,
    effective_url: str | None = None,
) -> bool:
    """Return whether *directory* has a complete manifest entry for a URL."""

    manifest = read_image_manifest(directory)
    for entry in _manifest_entries(manifest):
        if entry.get("source_url") == source_url or (
            effective_url is not None and entry.get("effective_url") == effective_url
        ):
            if manifest_entry_complete(directory, entry):
                return True
    return False


def manifest_entry_complete(directory: Path, entry: dict[str, Any]) -> bool:
    """Return whether all files recorded by *entry* are present and unchanged."""

    files = entry.get("files")
    if not isinstance(files, list) or not files:
        return False

    for file_record in files:
        if not isinstance(file_record, dict):
            return False
        relative_path = file_record.get("path")
        if not isinstance(relative_path, str) or not _is_safe_relative_path(
            relative_path
        ):
            return False
        filename = directory / relative_path
        if not filename.is_file():
            return False
        expected_size = file_record.get("size")
        if expected_size is not None and filename.stat().st_size != expected_size:
            return False
        expected_sha256 = file_record.get("sha256")
        if expected_sha256 is not None and file_sha256(filename) != expected_sha256:
            return False
    return True


def record_image_manifest_entry(
    directory: Path,
    *,
    source_url: str,
    effective_url: str,
    scraper: str,
    files: list[Path],
    source_ids: list[str] | None = None,
) -> bool:
    """Record a completed image scrape in *directory*.

    Return whether an entry was written. Entries without any existing image
    files are ignored.
    """

    file_records = image_file_records(directory, files)
    if not file_records:
        return False

    manifest = read_image_manifest(directory)
    entries = []
    merged_source_ids = set(source_ids or [])
    merged_file_records = {record["path"]: record for record in file_records}
    for entry in _manifest_entries(manifest):
        if entry.get("source_url") != source_url:
            entries.append(entry)
            continue
        for source_id in entry.get("source_ids", []):
            if isinstance(source_id, str):
                merged_source_ids.add(source_id)
        for record in entry.get("files", []):
            if isinstance(record, dict) and isinstance(record.get("path"), str):
                merged_file_records.setdefault(record["path"], record)

    entries.append(
        {
            "source_url": source_url,
            "effective_url": effective_url,
            "scraper": scraper,
            "source_ids": sorted(merged_source_ids),
            "scraped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "files": [
                merged_file_records[path] for path in sorted(merged_file_records)
            ],
        }
    )
    manifest["entries"] = entries
    write_image_manifest(directory, manifest)
    return True


def _empty_manifest() -> dict[str, Any]:
    return {"version": IMAGE_MANIFEST_VERSION, "entries": []}


def _manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts
