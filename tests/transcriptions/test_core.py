from saxonche import PySaxonProcessor

from scrapyrus.saxon_xml import (
    attribute_value,
    direct_children,
    document_element,
    expanded_name,
    normalized_text,
    parse_xml_text,
)
from scrapyrus.transcriptions import (
    available_translation_languages,
    epidoc_xml_to_text,
    transcription_language,
    transcription_xml_snippet,
    translation_epidoc_xml_to_text,
)


def _parse_snippet(proc: PySaxonProcessor, snippet: str):
    return document_element(parse_xml_text(proc, snippet))


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
    with PySaxonProcessor(license=False) as proc:
        edition = _parse_snippet(proc, snippet)
        assert expanded_name(edition) == "div"
        assert attribute_value(edition, "type") == "edition"
        assert normalized_text(direct_children(edition, "ab")[0]) == "Text"


def test_transcription_xml_snippet_can_retain_namespaces(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="edition"><ab>Text</ab></div></TEI>'
    )

    snippet = transcription_xml_snippet(transcription, remove_namespaces=False)

    with PySaxonProcessor(license=False) as proc:
        edition = _parse_snippet(proc, snippet)
        assert expanded_name(edition) == "{http://www.tei-c.org/ns/1.0}div"
        assert (
            normalized_text(
                direct_children(edition, "{http://www.tei-c.org/ns/1.0}ab")[0]
            )
            == "Text"
        )


def test_transcription_xml_snippet_returns_none_without_edition(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text('<TEI><div type="commentary" /></TEI>')

    assert transcription_xml_snippet(transcription) is None


def test_transcription_language_returns_edition_language():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">
    <text><body>
        <div xml:lang="grc" type="edition"><ab>Text</ab></div>
    </body></text>
    </TEI>"""

    assert transcription_language(xml) == "grc"


def test_transcription_language_falls_back_to_document_language(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="la">'
        '<text><body><div type="edition"><ab>Text</ab></div></body></text>'
        "</TEI>",
        encoding="utf-8",
    )

    assert transcription_language(transcription) == "la"


def test_transcription_language_returns_none_without_language():
    assert transcription_language('<TEI><div type="edition" /></TEI>') is None


def test_epidoc_xml_to_text_defaults_to_known_papyrus_text():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
    <text><body><div type="edition" xml:space="preserve"><ab>
    <lb n="1"/>α<unclear>β</unclear> <expan>γ<ex>δε</ex></expan> <supplied reason="lost">ζη</supplied> <choice><reg>θι</reg><orig>κι</orig></choice>
    <lb n="2"/>λ<expan><ex>μ</ex></expan>
    </ab></div></body></text>
    </TEI>"""

    assert epidoc_xml_to_text(xml) == "α γ κι\nλ"


def test_epidoc_xml_to_text_can_expand_abbreviations():
    xml = '<div type="edition"><ab><lb n="1"/><expan>γ<ex>δε</ex></expan></ab></div>'

    assert epidoc_xml_to_text(xml, abbrev=True) == "γδε"


def test_epidoc_xml_to_text_preserves_acrophonic_numerals():
    xml = '<div type="edition"><ab><lb n="1"/>α  𐅵   𐅷 𐅸 β</ab></div>'

    assert epidoc_xml_to_text(xml) == "α 𐅵 𐅷 𐅸 β"


def test_epidoc_xml_to_text_can_break_on_gaps():
    xml = '<div type="edition"><ab><lb n="1"/>α<gap reason="lost"/>β</ab></div>'

    assert epidoc_xml_to_text(xml) == "αβ"
    assert epidoc_xml_to_text(xml, break_on_gap=True) == "α\nβ"


def test_epidoc_xml_to_text_can_include_lost_text():
    xml = '<div type="edition"><ab><lb n="1"/>α<supplied reason="lost">β</supplied></ab></div>'

    assert epidoc_xml_to_text(xml, lost=True) == "αβ"


def test_epidoc_xml_to_text_can_include_unclear_text():
    xml = '<div type="edition"><ab><lb n="1"/>α<unclear>β</unclear></ab></div>'

    assert epidoc_xml_to_text(xml, unclear=True) == "αβ"


def test_epidoc_xml_to_text_can_regularize_choices():
    xml = (
        '<div type="edition"><ab><lb n="1"/>'
        "<choice><reg>θι</reg><orig>κι</orig></choice>"
        "</ab></div>"
    )

    assert epidoc_xml_to_text(xml, regularize=True) == "θι"


def test_epidoc_xml_to_text_combines_flags():
    xml = """<div type="edition" xml:space="preserve"><ab>
    <lb n="1"/>α<unclear>β</unclear> <expan>γ<ex>δε</ex></expan> <supplied reason="lost">ζη</supplied> <choice><reg>θι</reg><orig>κι</orig></choice>
    <lb n="2"/>λ<expan><ex>μ</ex></expan>
    </ab></div>"""

    assert (
        epidoc_xml_to_text(
            xml,
            abbrev=True,
            lost=True,
            unclear=True,
            regularize=True,
        )
        == "αβ γδε ζη θι\nλμ"
    )


def test_epidoc_xml_to_text_accepts_paths_and_namespace_stripped_snippets(tmp_path):
    transcription = tmp_path / "transcription.xml"
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        '<div type="edition"><ab><lb n="1"/>α<expan>β<ex>γ</ex></expan></ab></div>'
        "</body></text></TEI>",
        encoding="utf-8",
    )

    snippet = transcription_xml_snippet(transcription)

    assert epidoc_xml_to_text(transcription, abbrev=True) == "αβγ"
    assert epidoc_xml_to_text(snippet, abbrev=True) == "αβγ"


def test_translation_epidoc_xml_to_text_extracts_translation():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">
    <teiHeader><fileDesc><titleStmt><title>Header</title></titleStmt></fileDesc></teiHeader>
    <text><body>
        <div xml:lang="en" type="translation" xml:space="preserve">
            <p>
                <milestone unit="line" n="1"/> First sentence.
                <milestone unit="line" n="2" rend="break"/> Second sentence.
                <note>Translation credit.</note>
            </p>
        </div>
    </body></text>
    </TEI>"""

    assert translation_epidoc_xml_to_text(xml) == "First sentence.\nSecond sentence."


def test_translation_epidoc_xml_to_text_separates_textparts_and_paragraphs():
    xml = """<div type="translation" xml:space="preserve">
        <div n="r" type="textpart">
            <p><milestone unit="line" n="1"/> Recto.</p>
        </div>
        <div n="v" type="textpart">
            <p><milestone unit="line" n="12"/> Verso.</p>
            <p>Endorsement.</p>
        </div>
    </div>"""

    assert translation_epidoc_xml_to_text(xml) == "Recto.\nVerso.\nEndorsement."


def test_translation_epidoc_xml_to_text_joins_multiple_translation_divs():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
    <text><body>
        <div xml:lang="de" type="translation"><p>Deutsch.</p></div>
        <div xml:lang="en" type="translation"><p>English.</p></div>
    </body></text>
    </TEI>"""

    assert translation_epidoc_xml_to_text(xml) == "Deutsch.\n\nEnglish."


def test_translation_epidoc_xml_to_text_can_filter_by_language():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
    <text><body>
        <div xml:lang="de" type="translation"><p>Deutsch.</p></div>
        <div xml:lang="en" type="translation"><p>English one.</p></div>
        <div xml:lang="en" type="translation"><p>English two.</p></div>
    </body></text>
    </TEI>"""

    assert (
        translation_epidoc_xml_to_text(xml, language="en")
        == "English one.\n\nEnglish two."
    )
    assert translation_epidoc_xml_to_text(xml, language="fr") == ""


def test_translation_epidoc_xml_to_text_accepts_paths_and_snippets(tmp_path):
    translation = tmp_path / "translation.xml"
    translation.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        '<div type="translation"><p><milestone unit="line" n="1"/>Text.</p></div>'
        "</body></text></TEI>",
        encoding="utf-8",
    )
    snippet = (
        '<div type="translation"><p><milestone unit="line" n="1"/>Snippet.</p></div>'
    )

    assert translation_epidoc_xml_to_text(translation) == "Text."
    assert translation_epidoc_xml_to_text(snippet) == "Snippet."


def test_available_translation_languages_returns_unique_languages_in_order():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
    <text><body>
        <div xml:lang="de" type="translation"><p>Deutsch.</p></div>
        <div xml:lang="en" type="translation"><p>English one.</p></div>
        <div xml:lang="en" type="translation"><p>English two.</p></div>
        <div type="translation"><p>No language.</p></div>
        <div xml:lang="fr" type="translation">
            <div xml:lang="it" type="textpart"><p>Nested textpart.</p></div>
        </div>
    </body></text>
    </TEI>"""

    assert available_translation_languages(xml) == ["de", "en", "fr"]


def test_available_translation_languages_accepts_paths(tmp_path):
    translation = tmp_path / "translation.xml"
    translation.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        '<div xml:lang="en" type="translation"><p>Text.</p></div>'
        "</body></text></TEI>",
        encoding="utf-8",
    )

    assert available_translation_languages(translation) == ["en"]
