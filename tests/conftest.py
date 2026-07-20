from pathlib import Path

import pytest


def _write_tei(path: Path, *, tm_id: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><publicationStmt>"
        f'<idno type="TM">{tm_id}</idno>'
        "</publicationStmt></fileDesc></teiHeader>"
        f"<text><body>{body}</body></text>"
        "</TEI>",
        encoding="utf-8",
    )


@pytest.fixture
def idp_data(tmp_path: Path) -> Path:
    """Return a minimal, self-contained fixture for the current idp.data layout."""

    root = tmp_path / "idp.data"
    metadata_root = root / "HGV_meta_EpiDoc" / "HGV1"
    ddbdp_root = root / "DDbDP" / "0"
    translations_root = root / "Translations" / "0"
    (root / "DCLP").mkdir(parents=True)
    translations_root.mkdir(parents=True)

    _write_tei(metadata_root / "1.xml", tm_id="1")
    _write_tei(metadata_root / "53.xml", tm_id="53")
    _write_tei(metadata_root / "272.xml", tm_id="272")

    _write_tei(
        ddbdp_root / "1.xml",
        tm_id="1",
        body='<div type="edition"><ab>Text 1.</ab></div>',
    )
    _write_tei(
        ddbdp_root / "53.xml",
        tm_id="53",
        body='<div type="edition"><ab>Text 53.</ab></div>',
    )
    _write_tei(
        ddbdp_root / "272.xml",
        tm_id="272",
        body=(
            '<div type="edition">'
            '<note xml:lang="en">This text has not been added yet.</note>'
            "<ab/>"
            "</div>"
        ),
    )

    _write_tei(
        translations_root / "53-1.xml",
        tm_id="53",
        body='<div type="translation" xml:lang="en"><p>First.</p></div>',
    )
    _write_tei(
        translations_root / "53-2.xml",
        tm_id="53",
        body='<div type="translation" xml:lang="de"><p>Second.</p></div>',
    )
    return root
