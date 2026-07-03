import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from scrapyrus.image_manifest import IMAGE_MANIFEST_FILENAME


def load_script():
    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "backfill_image_manifests.py"
    )
    spec = importlib.util.spec_from_file_location("backfill_image_manifests", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_metadata(path: Path, *, tm_id: str, urls: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    graphics = "".join(f'<graphic url="{url}" />' for url in urls)
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><publicationStmt>"
        f'<idno type="TM">{tm_id}</idno>'
        "</publicationStmt></fileDesc></teiHeader>"
        f"<text><body><div><p><figure>{graphics}</figure></p></div></body></text>"
        "</TEI>",
        encoding="utf-8",
    )


def test_backfill_image_manifests_records_hgv_urls_and_merged_files(tmp_path):
    module = load_script()
    idp_data = tmp_path / "idp.data"
    write_metadata(
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "42a.xml",
        tm_id="420000",
        urls=["https://images.example/recto"],
    )
    write_metadata(
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "42b.xml",
        tm_id="420000",
        urls=["https://images.example/verso"],
    )

    hgv_images = tmp_path / "images"
    (hgv_images / "42a").mkdir(parents=True)
    (hgv_images / "42a" / "image.jpg").write_bytes(b"first")
    (hgv_images / "42b").mkdir()
    (hgv_images / "42b" / "image.jpg").write_bytes(b"second")

    tm_images = tmp_path / "images_tm"
    (tm_images / "420000").mkdir(parents=True)
    (tm_images / "420000" / "image.jpg").write_bytes(b"first")
    (tm_images / "420000" / "image.42b.jpg").write_bytes(b"second")

    summary = module.backfill_image_manifests(
        idp_data,
        hgv_images,
        tm_images,
        progressbar=False,
    )

    manifest = json.loads(
        (tm_images / "420000" / IMAGE_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert summary.hgv_directories == 2
    assert summary.manifest_entries == 2
    assert manifest["entries"] == [
        {
            "source_url": "https://images.example/recto",
            "effective_url": "https://images.example/recto",
            "scraper": "backfill",
            "source_ids": ["42a"],
            "scraped_at": manifest["entries"][0]["scraped_at"],
            "files": [
                {
                    "path": "image.jpg",
                    "size": 5,
                    "sha256": hashlib.sha256(b"first").hexdigest(),
                }
            ],
        },
        {
            "source_url": "https://images.example/verso",
            "effective_url": "https://images.example/verso",
            "scraper": "backfill",
            "source_ids": ["42b"],
            "scraped_at": manifest["entries"][1]["scraped_at"],
            "files": [
                {
                    "path": "image.42b.jpg",
                    "size": 6,
                    "sha256": hashlib.sha256(b"second").hexdigest(),
                }
            ],
        },
    ]
