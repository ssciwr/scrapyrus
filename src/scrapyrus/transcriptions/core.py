from pathlib import Path

from saxonche import PySaxonProcessor

from scrapyrus.saxon_xml import (
    first_string,
    parse_xml_document,
    parse_xml_text,
    select_first,
    select_nodes,
    serialize_node,
)


_XSLT_DIR = Path(__file__).with_name("xslt")
_EPIDOC_TO_TEXT_STYLESHEET = _XSLT_DIR / "epidoc-to-text.xsl"
_TRANSLATION_EPIDOC_TO_TEXT_STYLESHEET = _XSLT_DIR / "translation-epidoc-to-text.xsl"


def transcription_xml_snippet(
    transcription: Path,
    *,
    remove_namespaces: bool = True,
) -> str | None:
    """Return the edition division from a transcription XML file.

    The first ``div`` element with a ``type`` attribute of ``edition`` is
    returned as a serialized XML string. If the file has no such element,
    return ``None``. By default, namespace qualifiers are removed from TEI
    element tags in the returned snippet.
    """

    with PySaxonProcessor(license=False) as proc:
        document = parse_xml_document(proc, transcription)
        edition = select_first(
            proc,
            document,
            "(.//*[local-name() = 'div'][@type = 'edition'])[1]",
        )
        if edition is not None:
            return serialize_node(
                proc,
                edition,
                remove_namespaces=remove_namespaces,
            )
    return None


def transcription_language(epidoc_xml: str | bytes | Path) -> str | None:
    """Return the ``xml:lang`` value for an EpiDoc transcription edition."""

    with PySaxonProcessor(license=False) as proc:
        document = _parse_epidoc_xml(proc, epidoc_xml)
        language = first_string(
            proc,
            document,
            "((descendant-or-self::*[local-name() = 'div']"
            "[@type = 'edition'])[1]"
            "/@*[local-name() = 'lang' and "
            "namespace-uri() = 'http://www.w3.org/XML/1998/namespace'], "
            "/*[1]/@*[local-name() = 'lang' and "
            "namespace-uri() = 'http://www.w3.org/XML/1998/namespace'])[1]",
        )
    if language is None:
        return None

    language = language.strip()
    return language or None


def epidoc_xml_to_text(
    epidoc_xml: str | bytes | Path,
    *,
    abbrev: bool = False,
    break_on_gap: bool = False,
    lost: bool = False,
    unclear: bool = False,
    regularize: bool = False,
) -> str:
    """Return plain text from an EpiDoc XML transcription.

    By default, editorial restorations, expansion text, unclear readings,
    gap line breaks, and regularizations are omitted. Set the corresponding
    flags to include those layers in the output.
    """

    with PySaxonProcessor(license=False) as proc:
        document = _parse_epidoc_xml(proc, epidoc_xml)
        xslt_processor = proc.new_xslt30_processor()
        stylesheet = xslt_processor.compile_stylesheet(
            stylesheet_file=str(_EPIDOC_TO_TEXT_STYLESHEET)
        )
        for name, value in {
            "abbrev": abbrev,
            "break_on_gap": break_on_gap,
            "lost": lost,
            "unclear": unclear,
            "regularize": regularize,
        }.items():
            stylesheet.set_parameter(name, proc.make_boolean_value(value))
        return stylesheet.transform_to_string(xdm_node=document)


def translation_epidoc_xml_to_text(
    epidoc_xml: str | bytes | Path,
    *,
    language: str | None = None,
) -> str:
    """Return plain text from an EpiDoc XML translation.

    When ``language`` is set, only translation divisions with a matching
    ``xml:lang`` value are included.
    """

    with PySaxonProcessor(license=False) as proc:
        document = _parse_epidoc_xml(proc, epidoc_xml)
        xslt_processor = proc.new_xslt30_processor()
        stylesheet = xslt_processor.compile_stylesheet(
            stylesheet_file=str(_TRANSLATION_EPIDOC_TO_TEXT_STYLESHEET)
        )
        if language is not None:
            stylesheet.set_parameter("language", proc.make_string_value(language))
        return stylesheet.transform_to_string(xdm_node=document)


def available_translation_languages(epidoc_xml: str | bytes | Path) -> list[str]:
    """Return unique translation ``xml:lang`` values in document order."""

    with PySaxonProcessor(license=False) as proc:
        document = _parse_epidoc_xml(proc, epidoc_xml)
        language_values = [
            node.string_value
            for node in select_nodes(
                proc,
                document,
                ".//*[local-name() = 'div'][@type = 'translation']"
                "[not(ancestor::*[local-name() = 'div'][@type = 'translation'])]"
                " /@*[local-name() = 'lang' and "
                "namespace-uri() = 'http://www.w3.org/XML/1998/namespace']",
            )
        ]

    seen = set()
    unique_languages = []
    for language in language_values:
        if language and language not in seen:
            seen.add(language)
            unique_languages.append(language)
    return unique_languages


def _parse_epidoc_xml(proc: PySaxonProcessor, epidoc_xml: str | bytes | Path):
    if isinstance(epidoc_xml, Path):
        return parse_xml_document(proc, epidoc_xml)
    if isinstance(epidoc_xml, bytes):
        return parse_xml_text(proc, epidoc_xml)
    if epidoc_xml.lstrip().startswith("<"):
        return parse_xml_text(proc, epidoc_xml)
    return parse_xml_document(proc, Path(epidoc_xml))
