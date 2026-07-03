from pathlib import Path

from scrapyrus.image_manifest import (
    read_image_manifest,
    record_image_manifest_entry,
)


def test_record_image_manifest_entry_merges_repeated_source_urls(tmp_path):
    image_dir = tmp_path / "42"
    image_dir.mkdir()
    (image_dir / "recto.jpg").write_bytes(b"recto")
    (image_dir / "verso.jpg").write_bytes(b"verso")

    record_image_manifest_entry(
        image_dir,
        source_url="https://images.example/record",
        effective_url="https://images.example/record",
        scraper="backfill",
        files=[Path("recto.jpg")],
        source_ids=["42a"],
    )
    record_image_manifest_entry(
        image_dir,
        source_url="https://images.example/record",
        effective_url="https://images.example/record",
        scraper="backfill",
        files=[Path("verso.jpg")],
        source_ids=["42b"],
    )

    manifest = read_image_manifest(image_dir)

    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["source_ids"] == ["42a", "42b"]
    assert [file["path"] for file in manifest["entries"][0]["files"]] == [
        "recto.jpg",
        "verso.jpg",
    ]
