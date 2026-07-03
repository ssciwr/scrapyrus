import importlib.util
from pathlib import Path


def load_script():
    script = Path(__file__).resolve().parents[1] / "scripts" / "dirname_hgv_to_tm.py"
    spec = importlib.util.spec_from_file_location("dirname_hgv_to_tm", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_metadata(path: Path, *, tm_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><publicationStmt>"
        f'<idno type="TM">{tm_id}</idno>'
        "</publicationStmt></fileDesc></teiHeader>"
        "</TEI>",
        encoding="utf-8",
    )


def test_hgv_to_tm_ids_reads_metadata_tm_identifiers(tmp_path):
    module = load_script()
    idp_data = tmp_path / "idp.data"
    write_metadata(
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "42.xml",
        tm_id="420000",
    )
    write_metadata(
        idp_data / "HGV_meta_EpiDoc" / "HGV2" / "99.xml",
        tm_id="990000",
    )

    assert module.hgv_to_tm_ids(idp_data) == {"42": "420000", "99": "990000"}


def test_copy_with_tm_directory_names_copies_and_renames_hgv_directories(tmp_path):
    module = load_script()
    source = tmp_path / "images"
    (source / "42").mkdir(parents=True)
    (source / "42" / "recto.jpg").write_bytes(b"recto")
    (source / "nested" / "99").mkdir(parents=True)
    (source / "nested" / "99" / "verso.jpg").write_bytes(b"verso")
    (source / "keep").mkdir()
    (source / "keep" / "note.txt").write_text("unchanged", encoding="utf-8")

    destination = tmp_path / "images_tm"
    renamed = module.copy_with_tm_directory_names(
        source,
        destination,
        {"42": "420000", "99": "990000"},
    )

    assert renamed == [
        (Path("42"), Path("420000")),
        (Path("nested") / "99", Path("nested") / "990000"),
    ]
    assert (source / "42" / "recto.jpg").read_bytes() == b"recto"
    assert (source / "nested" / "99" / "verso.jpg").read_bytes() == b"verso"
    assert not (destination / "42").exists()
    assert not (destination / "nested" / "99").exists()
    assert (destination / "420000" / "recto.jpg").read_bytes() == b"recto"
    assert (destination / "nested" / "990000" / "verso.jpg").read_bytes() == b"verso"
    assert (destination / "keep" / "note.txt").read_text(
        encoding="utf-8"
    ) == "unchanged"


def test_copy_with_tm_directory_names_merges_colliding_directories(tmp_path):
    module = load_script()
    source = tmp_path / "images"
    (source / "42a").mkdir(parents=True)
    (source / "42a" / "same.jpg").write_bytes(b"same")
    (source / "42a" / "recto.jpg").write_bytes(b"recto")
    (source / "42b").mkdir()
    (source / "42b" / "same.jpg").write_bytes(b"same")
    (source / "42b" / "verso.jpg").write_bytes(b"verso")
    destination = tmp_path / "images_tm"

    renamed = module.copy_with_tm_directory_names(
        source,
        destination,
        {"42a": "420000", "42b": "420000"},
    )

    assert renamed == [
        (Path("42a"), Path("420000")),
        (Path("42b"), Path("420000")),
    ]
    assert (destination / "420000" / "same.jpg").read_bytes() == b"same"
    assert (destination / "420000" / "recto.jpg").read_bytes() == b"recto"
    assert (destination / "420000" / "verso.jpg").read_bytes() == b"verso"


def test_copy_with_tm_directory_names_preserves_same_name_file_conflicts(tmp_path):
    module = load_script()
    source = tmp_path / "images"
    (source / "42a").mkdir(parents=True)
    (source / "42a" / "image.jpg").write_bytes(b"first")
    (source / "42b").mkdir()
    (source / "42b" / "image.jpg").write_bytes(b"second")
    destination = tmp_path / "images_tm"

    module.copy_with_tm_directory_names(
        source,
        destination,
        {"42a": "420000", "42b": "420000"},
    )

    assert (destination / "420000" / "image.jpg").read_bytes() == b"first"
    assert (destination / "420000" / "image.42b.jpg").read_bytes() == b"second"
