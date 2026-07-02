from types import GeneratorType
from xml.etree import ElementTree

from scrapyrus.idpdata import iterate_hgv_triples, transcription_xml_snippet


def test_transcription_xml_snippet_returns_edition_as_string(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0">
        <text><body>
            <div type="commentary"><p>Commentary</p></div>
            <div xml:lang="grc" type="edition"><ab>Text</ab></div>
        </body></text>
        </TEI>"""
    )

    snippet = transcription_xml_snippet(transcription)

    assert isinstance(snippet, str)
    edition = ElementTree.fromstring(snippet)
    assert edition.tag == "div"
    assert edition.get("type") == "edition"
    assert edition.find("ab").text == "Text"


def test_transcription_xml_snippet_can_retain_namespaces(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="edition"><ab>Text</ab></div></TEI>'
    )

    snippet = transcription_xml_snippet(transcription, remove_namespaces=False)

    edition = ElementTree.fromstring(snippet)
    assert edition.tag == "{http://www.tei-c.org/ns/1.0}div"
    assert edition.find("{http://www.tei-c.org/ns/1.0}ab").text == "Text"


def test_transcription_xml_snippet_returns_none_without_edition(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text('<TEI><div type="commentary" /></TEI>')

    assert transcription_xml_snippet(transcription) is None


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
        idp_data / "DDB_EpiDoc_XML" / "p.adl" / "p.adl.G2.xml",
        None,
    )
    assert results["53"] == (
        "53",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "53.xml",
        idp_data / "DDB_EpiDoc_XML" / "p.ryl" / "p.ryl.4" / "p.ryl.4.581.xml",
        idp_data / "HGV_trans_EpiDoc" / "53.xml",
    )
    assert results["272"] == (
        "272",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "272.xml",
        None,
        None,
    )


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
