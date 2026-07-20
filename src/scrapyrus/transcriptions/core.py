import csv
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg import sql
from saxonche import PySaxonProcessor

from scrapyrus.idpdata import iterate_idpdata_triples
from scrapyrus.saxon_xml import (
    XML_NAMESPACE,
    attribute_value,
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

# The single transcription rendering used for stored text and embeddings.
MAXIMUM_TRANSCRIPTION_OPTIONS = {
    "abbrev": True,
    "break_on_gap": False,
    "lost": True,
    "unclear": True,
    "regularize": True,
}

TRANSCRIPTIONS_TABLE = "transcriptions"
TRANSCRIPTION_COLUMNS = (
    "transcription_id",
    "source_path",
    "tm_id",
    "xml_content",
    "type",
    "language",
    "text",
    "text_vector",
    "lemma_text",
    "lemma_vector",
)
TRANSCRIPTION_IMPORT_COLUMNS = (
    "transcription_id",
    "source_path",
    "tm_id",
    "xml_content",
    "type",
    "language",
    "text",
    "lemma_text",
)
TRANSCRIPTIONS_SCHEMA_SQL = f"""CREATE TABLE {TRANSCRIPTIONS_TABLE} (
    transcription_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_path text NOT NULL,
    tm_id bigint NOT NULL,
    xml_content xml NOT NULL,
    type text NOT NULL CHECK (type IN ('transcription', 'translation')),
    language text,
    text text NOT NULL,
    text_vector tsvector GENERATED ALWAYS AS
        (to_tsvector('simple', text)) STORED,
    lemma_text text,
    lemma_vector tsvector GENERATED ALWAYS AS
        (to_tsvector('simple', lemma_text)) STORED,
    CHECK (type = 'translation' OR language IS NULL)
);
CREATE INDEX {TRANSCRIPTIONS_TABLE}_tm_id_idx
    ON {TRANSCRIPTIONS_TABLE} (tm_id);
"""


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


def translation_xml_snippets(translation: Path) -> list[tuple[str | None, str]]:
    """Return top-level translation divisions and their optional languages.

    Nested translation divisions are part of their containing snippet and are
    not returned separately. TEI namespaces are retained in serialized XML.
    """

    with PySaxonProcessor(license=False) as proc:
        document = parse_xml_document(proc, translation)
        translations = select_nodes(
            proc,
            document,
            ".//*[local-name() = 'div'][@type = 'translation']"
            "[not(ancestor::*[local-name() = 'div'][@type = 'translation'])]",
        )
        return [
            (
                attribute_value(node, f"{{{XML_NAMESPACE}}}lang") or None,
                serialize_node(proc, node),
            )
            for node in translations
        ]


def ingest_transcriptions(
    idp_data: str | Path,
    conninfo: str = "",
    *,
    progressbar: bool = True,
    **connect_kwargs: Any,
) -> None:
    """Rebuild and populate the transcription and translation XML table."""

    idp_data = Path(idp_data)
    insert_sql = f"""
INSERT INTO {TRANSCRIPTIONS_TABLE}
    (source_path, tm_id, xml_content, type, language, text)
VALUES (
    %(source_path)s,
    %(tm_id)s,
    %(xml_content)s,
    %(type)s,
    %(language)s,
    %(text)s
)
"""

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {TRANSCRIPTIONS_TABLE}")
            cursor.execute(TRANSCRIPTIONS_SCHEMA_SQL)

            records = iterate_idpdata_triples(
                idp_data,
                progressbar=progressbar,
            )
            for tm_id, metadata, transcription, translation in records:
                if transcription is not None:
                    try:
                        snippet = transcription_xml_snippet(
                            transcription,
                            remove_namespaces=False,
                        )
                    except Exception:
                        _report_xml_failure(transcription)
                        raise
                    if snippet is not None:
                        row = _transcription_row(
                            idp_data,
                            transcription,
                            tm_id,
                            snippet,
                            "transcription",
                        )
                        if row["text"].strip():
                            cursor.execute(insert_sql, row)

                translation_sources = []
                if metadata.is_relative_to(idp_data / "DCLP"):
                    translation_sources.append(metadata)
                if translation is not None and translation not in translation_sources:
                    translation_sources.append(translation)

                for translation_source in translation_sources:
                    try:
                        snippets = translation_xml_snippets(translation_source)
                    except Exception:
                        _report_xml_failure(translation_source)
                        raise
                    for language, snippet in snippets:
                        row = _transcription_row(
                            idp_data,
                            translation_source,
                            tm_id,
                            snippet,
                            "translation",
                            language,
                        )
                        if row["text"].strip():
                            cursor.execute(insert_sql, row)


def dump_transcriptions(
    target: str | Path,
    conninfo: str = "",
    **connect_kwargs: Any,
) -> None:
    """Dump transcription XML, rendered text, and lemmata to CSV."""

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    output = target / f"{TRANSCRIPTIONS_TABLE}.csv"

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with output.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(TRANSCRIPTION_COLUMNS)
            columns = sql.SQL(", ").join(
                sql.Identifier(column) for column in TRANSCRIPTION_COLUMNS
            )
            query = sql.SQL(
                "SELECT {columns} FROM {table} ORDER BY transcription_id"
            ).format(
                columns=columns,
                table=sql.Identifier(TRANSCRIPTIONS_TABLE),
            )
            with connection.cursor() as cursor:
                cursor.execute(query)
                writer.writerows(cursor)


def import_transcriptions(
    source: str | Path,
    conninfo: str = "",
    **connect_kwargs: Any,
) -> None:
    """Rebuild the transcriptions table from a CSV dump.

    The source must have been produced by :func:`dump_transcriptions`. Identity
    values are restored so that separately dumped embeddings continue to refer
    to the same XML rows. PostgreSQL regenerates the stored text vectors from
    the imported text and lemmata.
    """

    source = Path(source)
    with source.open(encoding="utf-8", newline="") as csv_file:
        header = next(csv.reader(csv_file), None)
    expected_header = list(TRANSCRIPTION_COLUMNS)
    if header != expected_header:
        raise ValueError(
            "Transcription CSV header does not match the dump format: "
            f"expected {expected_header!r}, got {header!r}"
        )

    temporary_table = f"{TRANSCRIPTIONS_TABLE}_import"
    dump_columns = sql.SQL(", ").join(
        sql.Identifier(column) for column in TRANSCRIPTION_COLUMNS
    )
    import_columns = sql.SQL(", ").join(
        sql.Identifier(column) for column in TRANSCRIPTION_IMPORT_COLUMNS
    )

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {TRANSCRIPTIONS_TABLE}")
            cursor.execute(TRANSCRIPTIONS_SCHEMA_SQL)
            cursor.execute(
                sql.SQL(
                    "CREATE TEMP TABLE {temporary_table} (LIKE {table}) ON COMMIT DROP"
                ).format(
                    temporary_table=sql.Identifier(temporary_table),
                    table=sql.Identifier(TRANSCRIPTIONS_TABLE),
                )
            )
            with source.open("rb") as input_file:
                with cursor.copy(
                    sql.SQL(
                        "COPY {temporary_table} ({columns}) FROM STDIN "
                        "WITH (FORMAT CSV, HEADER true)"
                    ).format(
                        temporary_table=sql.Identifier(temporary_table),
                        columns=dump_columns,
                    )
                ) as copy:
                    while chunk := input_file.read(1024 * 1024):
                        copy.write(chunk)

            cursor.execute(
                sql.SQL(
                    "INSERT INTO {table} ({columns}) "
                    "OVERRIDING SYSTEM VALUE "
                    "SELECT {columns} FROM {temporary_table} "
                    "ORDER BY transcription_id"
                ).format(
                    table=sql.Identifier(TRANSCRIPTIONS_TABLE),
                    columns=import_columns,
                    temporary_table=sql.Identifier(temporary_table),
                )
            )
            cursor.execute(
                sql.SQL(
                    "SELECT setval("
                    "pg_get_serial_sequence(%s, %s), "
                    "COALESCE(max(transcription_id), 1), "
                    "max(transcription_id) IS NOT NULL) "
                    "FROM {table}"
                ).format(table=sql.Identifier(TRANSCRIPTIONS_TABLE)),
                (TRANSCRIPTIONS_TABLE, "transcription_id"),
            )


def _transcription_row(
    idp_data: Path,
    source: Path,
    tm_id: str,
    xml_content: str,
    document_type: str,
    language: str | None = None,
) -> dict[str, Any]:
    return {
        "source_path": source.relative_to(idp_data).as_posix(),
        "tm_id": int(tm_id),
        "xml_content": xml_content,
        "type": document_type,
        "language": language,
        "text": _xml_to_stored_text(xml_content, document_type),
    }


def _report_xml_failure(source: Path) -> None:
    print(f"Failed while processing XML file: {source}", file=sys.stderr)


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


def _xml_to_stored_text(xml_content: str, document_type: str) -> str:
    if document_type == "translation":
        return translation_epidoc_xml_to_text(xml_content)
    return epidoc_xml_to_text(xml_content, **MAXIMUM_TRANSCRIPTION_OPTIONS)


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
