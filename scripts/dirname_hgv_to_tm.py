# Used to copy a directory tree while renaming HGV-id directories to TM IDs.

"""Copy a directory tree while converting HGV-id directory names to TM IDs."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from scrapyrus.idpdata import trismegistos_id


def hgv_to_tm_ids(idp_data: str | Path) -> dict[str, str]:
    """Return a mapping from HGV metadata filenames to TM identifiers."""

    metadata_root = Path(idp_data) / "HGV_meta_EpiDoc"
    if not metadata_root.is_dir():
        raise NotADirectoryError(metadata_root)

    return {
        metadata.stem: trismegistos_id(metadata)
        for metadata in sorted(metadata_root.glob("HGV*/*.xml"))
    }


def copy_with_tm_directory_names(
    source: str | Path,
    destination: str | Path,
    hgv_to_tm: Mapping[str, str],
) -> list[tuple[Path, Path]]:
    """Copy *source* to *destination*, renaming HGV-id directories to TM IDs."""

    source = Path(source)
    destination = Path(destination)
    if not source.is_dir():
        raise NotADirectoryError(source)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)

    source_resolved = source.resolve()
    destination_resolved = destination.resolve(strict=False)
    if (
        destination_resolved == source_resolved
        or source_resolved in destination_resolved.parents
    ):
        raise ValueError("destination must not be inside source")

    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    renamed: list[tuple[Path, Path]] = []

    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}.",
        dir=destination_parent,
    ) as temporary_directory:
        temporary_destination = Path(temporary_directory) / destination.name
        temporary_destination.mkdir()
        _copy_tree(
            source,
            temporary_destination,
            hgv_to_tm,
            renamed,
            source_root=source,
            destination_root=temporary_destination,
        )
        temporary_destination.replace(destination)

    return renamed


def _copy_tree(
    source: Path,
    destination: Path,
    hgv_to_tm: Mapping[str, str],
    renamed: list[tuple[Path, Path]],
    *,
    source_root: Path,
    destination_root: Path,
) -> None:
    for entry in sorted(source.iterdir()):
        if entry.is_symlink():
            target = destination / entry.name
            _check_available(target, entry)
            os.symlink(os.readlink(entry), target)
            continue

        if entry.is_dir():
            target_name = hgv_to_tm.get(entry.name, entry.name)
            target = destination / target_name
            _check_available(target, entry)
            target.mkdir()
            if target_name != entry.name:
                renamed.append(
                    (
                        entry.relative_to(source_root),
                        target.relative_to(destination_root),
                    )
                )
            _copy_tree(
                entry,
                target,
                hgv_to_tm,
                renamed,
                source_root=source_root,
                destination_root=destination_root,
            )
            shutil.copystat(entry, target, follow_symlinks=False)
            continue

        target = destination / entry.name
        _check_available(target, entry)
        shutil.copy2(entry, target, follow_symlinks=False)


def _check_available(target: Path, source: Path) -> None:
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"{source} would overwrite {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        type=Path,
        help="Directory tree whose HGV-id subdirectories should be renamed",
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="New directory tree to create with TM-id directory names",
    )
    parser.add_argument(
        "--idp-data",
        type=Path,
        default=Path("idp.data"),
        help="Path to the idp.data repository clone",
    )
    arguments = parser.parse_args()

    renamed = copy_with_tm_directory_names(
        arguments.source,
        arguments.destination,
        hgv_to_tm_ids(arguments.idp_data),
    )

    print(f"Copied {arguments.source} to {arguments.destination}")
    print(f"Renamed {len(renamed)} director{'y' if len(renamed) == 1 else 'ies'}")
    for source, destination in renamed:
        print(f"{source} -> {destination}")


if __name__ == "__main__":
    main()
