from pathlib import Path

from saxonche import PySaxonProcessor

from scrapyrus.saxon_xml import (
    parse_xml_document,
    parse_xml_text,
    select_first,
    serialize_node,
)


_XSLT_DIR = Path(__file__).with_name("xslt")
_EPIDOC_TO_TEXT_STYLESHEET = _XSLT_DIR / "epidoc-to-text.xsl"


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


def epidoc_xml_to_text(
    epidoc_xml: str | bytes | Path,
    *,
    abbrev: bool = False,
    lost: bool = False,
    unclear: bool = False,
    regularize: bool = False,
) -> str:
    """Return plain text from an EpiDoc XML transcription.

    By default, editorial restorations, expansion text, unclear readings, and
    regularizations are omitted. Set the corresponding flags to include those
    layers in the output.
    """

    with PySaxonProcessor(license=False) as proc:
        document = _parse_epidoc_xml(proc, epidoc_xml)
        xslt_processor = proc.new_xslt30_processor()
        stylesheet = xslt_processor.compile_stylesheet(
            stylesheet_file=str(_EPIDOC_TO_TEXT_STYLESHEET)
        )
        for name, value in {
            "abbrev": abbrev,
            "lost": lost,
            "unclear": unclear,
            "regularize": regularize,
        }.items():
            stylesheet.set_parameter(name, proc.make_boolean_value(value))
        return stylesheet.transform_to_string(xdm_node=document)


def _parse_epidoc_xml(proc: PySaxonProcessor, epidoc_xml: str | bytes | Path):
    if isinstance(epidoc_xml, Path):
        return parse_xml_document(proc, epidoc_xml)
    if isinstance(epidoc_xml, bytes):
        return parse_xml_text(proc, epidoc_xml)
    if epidoc_xml.lstrip().startswith("<"):
        return parse_xml_text(proc, epidoc_xml)
    return parse_xml_document(proc, Path(epidoc_xml))
