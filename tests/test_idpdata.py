from types import GeneratorType

import pytest

from scrapyrus.idpdata import (
    iterate_dclp_triples,
    iterate_hgv_triples,
    iterate_idpdata_triples,
)


def _write_tei_metadata(
    path,
    *,
    tm_id,
    body="",
    ddb_filename=None,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    ddb_idno = (
        f'<idno type="ddb-filename">{ddb_filename}</idno>' if ddb_filename else ""
    )
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><publicationStmt>"
        f'<idno type="TM">{tm_id}</idno>'
        f"{ddb_idno}"
        "</publicationStmt></fileDesc></teiHeader>"
        f"<text><body>{body}</body></text>"
        "</TEI>",
        encoding="utf-8",
    )


def test_iterate_hgv_triples_returns_generator(idp_data):
    triples = iterate_hgv_triples(idp_data)

    assert isinstance(triples, GeneratorType)


def test_iterate_hgv_triples_finds_associated_files(idp_data):
    expected_ids = {"1", "53", "272"}
    results = {}

    for triple in iterate_hgv_triples(idp_data, progressbar=False):
        if triple[0] in expected_ids:
            results[triple[0]] = triple
        if results.keys() == expected_ids:
            break

    assert results["1"] == (
        "1",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "1.xml",
        idp_data / "DDbDP" / "0" / "1.xml",
        (),
    )
    assert results["53"] == (
        "53",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "53.xml",
        idp_data / "DDbDP" / "0" / "53.xml",
        (
            idp_data / "Translations" / "0" / "53-1.xml",
            idp_data / "Translations" / "0" / "53-2.xml",
        ),
    )
    assert results["272"] == (
        "272",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "272.xml",
        None,
        (),
    )


def test_iterate_hgv_triples_returns_tm_id_from_metadata(tmp_path):
    idp_data = tmp_path / "idp.data"
    metadata_root = idp_data / "HGV_meta_EpiDoc" / "HGV999"
    transcription_root = idp_data / "DDbDP" / "123"
    translation_root = idp_data / "Translations" / "999"
    metadata_root.mkdir(parents=True)
    transcription_root.mkdir(parents=True)
    translation_root.mkdir(parents=True)

    metadata = metadata_root / "999999.xml"
    metadata.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        "<teiHeader><fileDesc><publicationStmt>"
        '<idno type="filename">999999</idno>'
        '<idno type="TM">123456</idno>'
        '<idno type="ddb-filename">p.test.1</idno>'
        "</publicationStmt></fileDesc></teiHeader>"
        "</TEI>",
        encoding="utf-8",
    )
    transcription = transcription_root / "123456.xml"
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="edition"><ab>Text.</ab></div></TEI>',
        encoding="utf-8",
    )
    translation = translation_root / "999999-1.xml"
    translation.write_text("<TEI />", encoding="utf-8")

    assert list(iterate_hgv_triples(idp_data, progressbar=False)) == [
        ("123456", metadata, transcription, (translation,))
    ]


def test_iterate_hgv_triples_shows_progressbar_by_default(idp_data, monkeypatch):
    progress = {}

    def fake_tqdm(iterable, *, total, unit, desc):
        progress.update(iterable=iterable, total=total, unit=unit, desc=desc)
        return iterable

    monkeypatch.setattr("scrapyrus.idpdata.tqdm", fake_tqdm)

    next(iterate_hgv_triples(idp_data))

    assert progress["total"] == len(progress["iterable"])
    assert progress["unit"] == "record"
    assert progress["desc"] == "Iterating HGV"


def test_iterate_hgv_triples_accepts_custom_progressbar_title(
    idp_data,
    monkeypatch,
):
    progress = {}

    def fake_tqdm(iterable, *, total, unit, desc):
        progress["desc"] = desc
        return iterable

    monkeypatch.setattr("scrapyrus.idpdata.tqdm", fake_tqdm)

    next(iterate_hgv_triples(idp_data, progressbar_title="Finding records"))

    assert progress["desc"] == "Finding records"


def test_iterate_dclp_triples_returns_generator(tmp_path):
    triples = iterate_dclp_triples(tmp_path / "idp.data")

    assert isinstance(triples, GeneratorType)


def test_iterate_dclp_triples_reuses_metadata_for_nonempty_edition(tmp_path):
    idp_data = tmp_path / "idp.data"
    with_transcription = idp_data / "DCLP" / "1" / "123.xml"
    empty_transcription = idp_data / "DCLP" / "1" / "124.xml"
    without_transcription = idp_data / "DCLP" / "2" / "125.xml"
    _write_tei_metadata(
        with_transcription,
        tm_id="123",
        body='<div type="edition"><ab>Text</ab></div>',
    )
    _write_tei_metadata(
        empty_transcription,
        tm_id="124",
        body='<div type="edition" />',
    )
    _write_tei_metadata(
        without_transcription,
        tm_id="125",
        body='<div type="commentary"><p>Commentary</p></div>',
    )

    assert list(iterate_dclp_triples(idp_data, progressbar=False)) == [
        ("123", with_transcription, with_transcription, ()),
        ("124", empty_transcription, None, ()),
        ("125", without_transcription, None, ()),
    ]


def test_iterate_dclp_triples_shows_progressbar_by_default(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    _write_tei_metadata(
        idp_data / "DCLP" / "1" / "123.xml",
        tm_id="123",
        body='<div type="edition"><ab>Text</ab></div>',
    )
    progress = {}

    def fake_tqdm(iterable, *, total, unit, desc):
        progress.update(iterable=iterable, total=total, unit=unit, desc=desc)
        return iterable

    monkeypatch.setattr("scrapyrus.idpdata.tqdm", fake_tqdm)

    next(iterate_dclp_triples(idp_data))

    assert progress["total"] == len(progress["iterable"])
    assert progress["unit"] == "record"
    assert progress["desc"] == "Iterating DCLP"


def test_iterate_idpdata_triples_concatenates_with_single_progressbar(
    tmp_path,
    monkeypatch,
):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "1.xml"
    transcription = idp_data / "DDbDP" / "0" / "1.xml"
    translation_root = idp_data / "Translations"
    dclp = idp_data / "DCLP" / "2" / "2.xml"
    _write_tei_metadata(metadata, tm_id="1", ddb_filename="p.test.1")
    transcription.parent.mkdir(parents=True)
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="edition"><ab>Text.</ab></div></TEI>',
        encoding="utf-8",
    )
    translation_root.mkdir()
    _write_tei_metadata(
        dclp,
        tm_id="2",
        body='<div type="edition"><ab>Text</ab></div>',
    )
    progress_calls = []

    def fake_tqdm(iterable, *, total, unit, desc):
        progress_calls.append(
            {"iterable": iterable, "total": total, "unit": unit, "desc": desc}
        )
        return iterable

    monkeypatch.setattr("scrapyrus.idpdata.tqdm", fake_tqdm)

    assert list(iterate_idpdata_triples(idp_data)) == [
        ("1", metadata, transcription, ()),
        ("2", dclp, dclp, ()),
    ]
    assert len(progress_calls) == 1
    assert progress_calls[0]["total"] == 2
    assert progress_calls[0]["unit"] == "record"
    assert progress_calls[0]["desc"] == "Iterating idp.data"


def test_iterate_hgv_triples_rejects_obsolete_layout(tmp_path):
    idp_data = tmp_path / "idp.data"
    (idp_data / "HGV_meta_EpiDoc").mkdir(parents=True)
    (idp_data / "DDB_EpiDoc_XML").mkdir()
    (idp_data / "HGV_trans_EpiDoc").mkdir()

    with pytest.raises(
        FileNotFoundError,
        match=r"missing directories: DDbDP, Translations",
    ):
        next(iterate_hgv_triples(idp_data, progressbar=False))
