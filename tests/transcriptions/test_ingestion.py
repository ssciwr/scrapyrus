import csv

import psycopg

from scrapyrus.transcriptions.core import (
    TRANSCRIPTION_COLUMNS,
    dump_transcriptions,
    ingest_transcriptions,
    translation_xml_snippets,
)


class RecordingCursor:
    def __init__(self, rows=()):
        self.executions = []
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def __iter__(self):
        return iter(self.rows)


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


def _normalize_sql(query):
    return " ".join(str(query).split())


def test_translation_xml_snippets_returns_each_language(tmp_path):
    translation = tmp_path / "translation.xml"
    translation.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        '<div type="translation" xml:lang="de"><p>Deutsch.</p></div>'
        '<div type="translation" xml:lang="en"><p>English.</p>'
        '<div type="textpart"><p>Nested.</p></div></div>'
        '<div type="translation"><p>Unspecified.</p></div>'
        "</body></text></TEI>",
        encoding="utf-8",
    )

    snippets = translation_xml_snippets(translation)

    assert [language for language, _ in snippets] == ["de", "en", None]
    assert all('xmlns="http://www.tei-c.org/ns/1.0"' in xml for _, xml in snippets)
    assert "Nested." in snippets[1][1]


def test_ingest_transcriptions_rebuilds_table_and_inserts_snippets(
    tmp_path,
    monkeypatch,
):
    idp_data = tmp_path / "idp.data"
    transcription = idp_data / "DDB_EpiDoc_XML" / "p.test" / "p.test.46.xml"
    translation = idp_data / "HGV_trans_EpiDoc" / "46.xml"
    transcription.parent.mkdir(parents=True)
    translation.parent.mkdir(parents=True)
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><div type="edition">'
        "<ab>Text</ab></div></TEI>",
        encoding="utf-8",
    )
    translation.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="translation" xml:lang="en"><p>Translation.</p></div></TEI>',
        encoding="utf-8",
    )
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    connect_calls = []
    iterator_calls = []

    def connect(conninfo, **kwargs):
        connect_calls.append((conninfo, kwargs))
        return connection

    def iterate(root, *, progressbar):
        iterator_calls.append((root, progressbar))
        yield "46", idp_data / "metadata.xml", transcription, translation

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.iterate_idpdata_triples",
        iterate,
    )
    text_calls = []

    def transcription_text(xml, **options):
        text_calls.append(("transcription", options))
        return "Maximum transcription text"

    def translation_text(xml):
        text_calls.append(("translation", {}))
        return "Complete translation text"

    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.epidoc_xml_to_text",
        transcription_text,
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.translation_epidoc_xml_to_text",
        translation_text,
    )

    ingest_transcriptions(
        idp_data,
        "postgresql://database.example/scrapyrus",
        progressbar=False,
        application_name="scrapyrus-test",
    )

    assert connect_calls == [
        (
            "postgresql://database.example/scrapyrus",
            {"application_name": "scrapyrus-test"},
        )
    ]
    assert iterator_calls == [(idp_data, False)]
    assert _normalize_sql(cursor.executions[0][0]) == (
        "DROP TABLE IF EXISTS transcriptions"
    )
    schema = _normalize_sql(cursor.executions[1][0])
    assert "xml_content xml NOT NULL" in schema
    assert "type IN ('transcription', 'translation')" in schema
    assert "language text" in schema
    assert "text text NOT NULL" in schema
    assert (
        "text_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED"
    ) in schema
    assert "lemma_text text" in schema
    assert (
        "lemma_vector tsvector GENERATED ALWAYS AS "
        "(to_tsvector('simple', lemma_text)) STORED"
    ) in schema
    rows = [execution[1] for execution in cursor.executions[2:]]
    assert [(row["type"], row["language"]) for row in rows] == [
        ("transcription", None),
        ("translation", "en"),
    ]
    assert rows[0]["source_path"] == "DDB_EpiDoc_XML/p.test/p.test.46.xml"
    assert rows[0]["tm_id"] == 46
    assert rows[1]["source_path"] == "HGV_trans_EpiDoc/46.xml"
    assert 'xmlns="http://www.tei-c.org/ns/1.0"' in rows[0]["xml_content"]
    assert [row["text"] for row in rows] == [
        "Maximum transcription text",
        "Complete translation text",
    ]
    assert text_calls == [
        (
            "transcription",
            {
                "abbrev": True,
                "break_on_gap": False,
                "lost": True,
                "unclear": True,
                "regularize": True,
            },
        ),
        ("translation", {}),
    ]


def test_ingest_transcriptions_extracts_embedded_dclp_translation(
    tmp_path,
    monkeypatch,
):
    idp_data = tmp_path / "idp.data"
    dclp = idp_data / "DCLP" / "1" / "123.xml"
    dclp.parent.mkdir(parents=True)
    dclp.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="edition"><ab>Text.</ab></div>'
        '<div type="translation" xml:lang="en"><p>Translation.</p></div>'
        "</TEI>",
        encoding="utf-8",
    )
    cursor = RecordingCursor()
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda conninfo, **kwargs: RecordingConnection(cursor),
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.iterate_idpdata_triples",
        lambda root, *, progressbar: iter([("123", dclp, dclp, None)]),
    )

    ingest_transcriptions(idp_data, progressbar=False)

    rows = [execution[1] for execution in cursor.executions[2:]]
    assert [(row["type"], row["source_path"]) for row in rows] == [
        ("transcription", "DCLP/1/123.xml"),
        ("translation", "DCLP/1/123.xml"),
    ]


def test_ingest_transcriptions_omits_rows_with_blank_text(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    transcription = idp_data / "DDB_EpiDoc_XML" / "p.test" / "p.test.46.xml"
    translation = idp_data / "HGV_trans_EpiDoc" / "46.xml"
    transcription.parent.mkdir(parents=True)
    translation.parent.mkdir(parents=True)
    transcription.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><div type="edition">'
        "<ab/></div></TEI>",
        encoding="utf-8",
    )
    translation.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<div type="translation" xml:lang="en"><p/></div></TEI>',
        encoding="utf-8",
    )
    cursor = RecordingCursor()
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda conninfo, **kwargs: RecordingConnection(cursor),
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.iterate_idpdata_triples",
        lambda root, *, progressbar: iter(
            [("46", idp_data / "metadata.xml", transcription, translation)]
        ),
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.epidoc_xml_to_text",
        lambda xml, **options: " \n\t",
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.core.translation_epidoc_xml_to_text",
        lambda xml: "",
    )

    ingest_transcriptions(idp_data, progressbar=False)

    assert len(cursor.executions) == 2


def test_dump_transcriptions_writes_csv(tmp_path, monkeypatch):
    rows = [
        (
            1,
            "DDB_EpiDoc_XML/p.test/p.test.46.xml",
            46,
            '<div type="edition"><ab>Text</ab></div>',
            "transcription",
            None,
            "Text",
            "'text':1",
            "lemma",
            "'lemma':1",
        ),
        (
            2,
            "HGV_trans_EpiDoc/46.xml",
            46,
            '<div type="translation" xml:lang="en"><p>Text.</p></div>',
            "translation",
            "en",
            "Text.",
            "'text':1",
            "lemmatized translation",
            "'lemmatized':1 'translation':2",
        ),
    ]
    cursor = RecordingCursor(rows)
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda conninfo, **kwargs: RecordingConnection(cursor),
    )

    dump_transcriptions(tmp_path / "csv")

    with (tmp_path / "csv" / "transcriptions.csv").open(
        encoding="utf-8",
        newline="",
    ) as csv_file:
        assert list(csv.reader(csv_file)) == [
            list(TRANSCRIPTION_COLUMNS),
            [str(value) if value is not None else "" for value in rows[0]],
            [str(value) if value is not None else "" for value in rows[1]],
        ]
    assert len(cursor.executions) == 1
    assert "ORDER BY transcription_id" in str(cursor.executions[0][0])
