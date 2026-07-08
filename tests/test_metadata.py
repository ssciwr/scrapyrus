import csv

import pytest
import psycopg
from pydantic import ValidationError
from saxonche import PySaxonApiError, PySaxonProcessor

from scrapyrus.ingestion import dump_metadata_tables, ingest_metadata
from scrapyrus.metadata import KeywordMetadataTable, PapyrusMetadataTable
from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.keywords import KeywordModel, KeywordModelFactory
from scrapyrus.metadata.papyri import PapyrusModel, PapyrusModelFactory


class RecordingCursor:
    def __init__(self):
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


class DumpCursor:
    def __init__(self, row_batches):
        self.executions = []
        self.row_batches = row_batches
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query):
        self.executions.append(query)
        self.rows = self.row_batches[len(self.executions) - 1]

    def __iter__(self):
        return iter(self.rows)


def _normalize_sql(sql):
    return " ".join(sql.split())


def _write_minimal_metadata(
    path,
    *,
    tm_id,
    title="O.Vleem. 11A",
    material="Papyrus",
    ddb_filename=None,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    ddb_filename_id = (
        f'<idno type="ddb-filename">{ddb_filename}</idno>' if ddb_filename else ""
    )
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>{title}</title>
              </titleStmt>
              <publicationStmt>
                <idno type="TM">{tm_id}</idno>
                {ddb_filename_id}
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <msIdentifier>
                    <idno>unbekannt</idno>
                  </msIdentifier>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>{material}</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )


def test_metadata_table_subclasses_register_in_definition_order(monkeypatch):
    monkeypatch.setattr(MetadataTable, "_tables", [])

    class FirstTable(MetadataTable):
        pass

    class SecondTable(MetadataTable):
        pass

    class UnregisteredTable(MetadataTable, register=False):
        pass

    assert MetadataTable.registered_tables() == (FirstTable, SecondTable)
    assert UnregisteredTable not in MetadataTable.registered_tables()


def test_metadata_table_registry_contains_builtin_tables():
    assert MetadataTable.registered_tables() == (
        PapyrusMetadataTable,
        KeywordMetadataTable,
    )


def test_metadata_table_columns_match_model_fields():
    papyri = PapyrusMetadataTable()
    keywords = KeywordMetadataTable()

    assert papyri.model_class is PapyrusModel
    assert papyri.columns == tuple(PapyrusModel.model_fields)
    assert keywords.model_class is KeywordModel
    assert keywords.columns == tuple(KeywordModel.model_fields)


def test_papyrus_model_factory_extracts_all_fields(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>O.Vleem. 11A</title>
              </titleStmt>
              <publicationStmt>
                <idno type="TM">46</idno>
                <idno type="dclp">123</idno>
                <idno type="dclp-hybrid">dclp;;123</idno>
                <idno type="ddb-perseus-style">0046;;11A</idno>
                <idno type="ddb-filename">o.vleem.11A</idno>
                <idno type="ddb-hybrid">o.vleem;;11A</idno>
                <idno type="HGV">46</idno>
                <idno type="LDAB">456</idno>
                <idno type="MP3">789</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <msIdentifier>
                    <placeName>
                      <settlement>Cairo</settlement>
                    </placeName>
                  </msIdentifier>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>Papyrus</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        model = PapyrusModelFactory(proc).parse(str(metadata), "metadata.xml")

    assert model.source_path == "metadata.xml"
    assert model.tm_id == 46
    assert model.dclp_id == 123
    assert model.dclp_hybrid_id == "dclp;;123"
    assert model.ddb_perseus_style_id == "0046;;11A"
    assert model.ddb_filename == "o.vleem.11A"
    assert model.ddb_hybrid_id == "o.vleem;;11A"
    assert model.hgv_id == "46"
    assert model.ldab_id == "456"
    assert model.mp3_id == "789"
    assert model.title == "O.Vleem. 11A"
    assert model.material == "papyrus"
    assert model.current_location == "Cairo"


def test_papyrus_model_factory_uses_first_duplicate_scalar_value(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>O.Vleem. 11A</title>
              </titleStmt>
              <publicationStmt>
                <idno type="TM">46</idno>
                <idno type="ddb-hybrid">o.vleem;;11A</idno>
                <idno type="ddb-hybrid">duplicate;;value</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>Papyrus</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        model = PapyrusModelFactory(proc).parse(str(metadata), "metadata.xml")

    assert model.ddb_hybrid_id == "o.vleem;;11A"


def test_papyrus_model_factory_drops_keiner_placeholders(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>keiner</title>
              </titleStmt>
              <publicationStmt>
                <idno type="TM">46</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <msIdentifier>
                    <idno>keiner</idno>
                  </msIdentifier>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>Papyrus</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        model = PapyrusModelFactory(proc).parse(str(metadata), "metadata.xml")

    assert model.title is None
    assert model.current_location is None


def test_papyrus_model_factory_drops_known_dclp_id_placeholders(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>Medical recipe</title>
              </titleStmt>
              <publicationStmt>
                <idno type="filename">hgvTEMP</idno>
                <idno type="dclp">hgvTEMP</idno>
                <idno type="dclp-hybrid"/>
                <idno type="TM">101351</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <msIdentifier>
                    <placeName>
                      <settlement>unbekannt</settlement>
                    </placeName>
                    <idno type="invNo">Vienna, Nationalbibliothek, K 5506</idno>
                  </msIdentifier>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>papyrus</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        model = PapyrusModelFactory(proc).parse(str(metadata), "metadata.xml")

    assert model.tm_id == 101351
    assert model.dclp_id is None
    assert model.dclp_hybrid_id is None


def test_papyrus_model_factory_uses_first_current_location_candidate(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>O.Vleem. 11A</title>
              </titleStmt>
              <publicationStmt>
                <idno type="TM">46</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <msIdentifier>
                    <placeName>
                      <settlement>Cairo</settlement>
                    </placeName>
                    <collection>Egyptian Museum</collection>
                  </msIdentifier>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>Papyrus</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        model = PapyrusModelFactory(proc).parse(str(metadata), "metadata.xml")

    assert model.current_location == "Cairo"


def test_keyword_model_factory_extracts_profile_terms(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt>
                <idno type="TM">46</idno>
              </publicationStmt>
            </fileDesc>
            <profileDesc>
              <textClass>
                <keywords scheme="hgv">
                  <term>prose (?)</term>
                  <term>bible?</term>
                  <term type="culture">literature</term>
                  <term type="religion">christian</term>
                </keywords>
              </textClass>
            </profileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        models = KeywordModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
            "keyword_id": 1,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "prose",
            "uncertain": True,
        },
        {
            "keyword_id": 2,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "bible",
            "uncertain": True,
        },
        {
            "keyword_id": 3,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": "culture",
            "keyword": "literature",
            "uncertain": False,
        },
        {
            "keyword_id": 4,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": "religion",
            "keyword": "christian",
            "uncertain": False,
        },
    ]


def test_ingest_metadata_creates_schema_and_inserts_rows(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "46.xml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>O.Vleem. 11A</title>
              </titleStmt>
              <publicationStmt>
                <idno type="TM">46</idno>
                <idno type="dclp">123</idno>
                <idno type="dclp-hybrid">dclp;;123</idno>
                <idno type="ddb-perseus-style">0046;;11A</idno>
                <idno type="ddb-filename">o.vleem.11A</idno>
                <idno type="ddb-hybrid">o.vleem;;11A</idno>
                <idno type="HGV">46</idno>
                <idno type="LDAB">456</idno>
                <idno type="MP3">789</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <msIdentifier>
                    <idno>unbekannt</idno>
                  </msIdentifier>
                  <physDesc>
                    <objectDesc>
                      <supportDesc>
                        <support>
                          <material>Papyrus</material>
                        </support>
                      </supportDesc>
                    </objectDesc>
                  </physDesc>
                </msDesc>
              </sourceDesc>
            </fileDesc>
            <profileDesc>
              <textClass>
                <keywords scheme="hgv">
                  <term>prose (?)</term>
                  <term>bible?</term>
                  <term type="culture">literature</term>
                  <term type="religion">christian</term>
                </keywords>
              </textClass>
            </profileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    connect_calls = []
    iterator_calls = []

    def connect(conninfo, **kwargs):
        connect_calls.append((conninfo, kwargs))
        return connection

    def iterate(idp_data, *, progressbar):
        iterator_calls.append((idp_data, progressbar))
        yield "46", metadata, None, None

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr("scrapyrus.ingestion.iterate_idpdata_triples", iterate)

    result = ingest_metadata(
        idp_data,
        "postgresql://metadata.example/scrapyrus",
        progressbar=False,
        application_name="scrapyrus-test",
    )

    assert result is None
    assert connect_calls == [
        (
            "postgresql://metadata.example/scrapyrus",
            {"application_name": "scrapyrus-test"},
        )
    ]
    assert iterator_calls == [(idp_data, False)]
    assert _normalize_sql(cursor.executions[0][0]) == "DROP TABLE IF EXISTS papyri"
    assert cursor.executions[0][1] is None
    assert _normalize_sql(cursor.executions[1][0]) == "DROP TABLE IF EXISTS keywords"
    assert cursor.executions[1][1] is None
    assert cursor.executions[2][0].startswith("CREATE TABLE IF NOT EXISTS papyri")
    assert cursor.executions[2][1] is None
    schema_sql = _normalize_sql(cursor.executions[2][0])
    assert "source_path text NOT NULL PRIMARY KEY" in schema_sql
    assert "CREATE INDEX IF NOT EXISTS papyri_tm_id_idx ON papyri (tm_id)" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS keywords" in schema_sql
    assert "keyword_id integer NOT NULL PRIMARY KEY" in schema_sql
    assert "uncertain boolean NOT NULL" in schema_sql
    columns = list(PapyrusMetadataTable().columns)
    assert _normalize_sql(cursor.executions[3][0]) == (
        f"INSERT INTO papyri ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert cursor.executions[3][1] == {
        "source_path": "HGV_meta_EpiDoc/HGV1/46.xml",
        "tm_id": 46,
        "dclp_id": 123,
        "dclp_hybrid_id": "dclp;;123",
        "ddb_perseus_style_id": "0046;;11A",
        "ddb_filename": "o.vleem.11A",
        "ddb_hybrid_id": "o.vleem;;11A",
        "hgv_id": "46",
        "ldab_id": "456",
        "mp3_id": "789",
        "title": "O.Vleem. 11A",
        "material": "papyrus",
        "current_location": None,
    }
    columns = list(KeywordMetadataTable().columns)
    assert _normalize_sql(cursor.executions[4][0]) == (
        f"INSERT INTO keywords ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert [execution[1] for execution in cursor.executions[4:]] == [
        {
            "keyword_id": 1,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "prose",
            "uncertain": True,
        },
        {
            "keyword_id": 2,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "bible",
            "uncertain": True,
        },
        {
            "keyword_id": 3,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": "culture",
            "keyword": "literature",
            "uncertain": False,
        },
        {
            "keyword_id": 4,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": "religion",
            "keyword": "christian",
            "uncertain": False,
        },
    ]


def test_ingest_metadata_stores_duplicate_tm_source_records(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    metadata_a = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "13a.xml"
    metadata_b = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "13b.xml"
    _write_minimal_metadata(
        metadata_a,
        tm_id=13,
        title="Sale of Land",
        ddb_filename="p.adl.G13",
    )
    _write_minimal_metadata(
        metadata_b,
        tm_id=13,
        title="Receipt for Sales Tax",
        ddb_filename="p.adl.G13",
    )
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)

    def connect(conninfo, **kwargs):
        return connection

    def iterate(idp_data, *, progressbar):
        yield "13", metadata_a, None, None
        yield "13", metadata_b, None, None

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr("scrapyrus.ingestion.iterate_idpdata_triples", iterate)

    ingest_metadata(idp_data, progressbar=False)

    first_row = cursor.executions[3][1]
    second_row = cursor.executions[4][1]
    assert first_row["tm_id"] == second_row["tm_id"] == 13
    assert first_row["source_path"] == "HGV_meta_EpiDoc/HGV1/13a.xml"
    assert first_row["title"] == "Sale of Land"
    assert second_row["source_path"] == "HGV_meta_EpiDoc/HGV1/13b.xml"
    assert second_row["title"] == "Receipt for Sales Tax"


def test_dump_metadata_tables_writes_csv_files(tmp_path, monkeypatch):
    papyri_rows = [
        (
            "HGV_meta_EpiDoc/HGV1/13a.xml",
            13,
            None,
            None,
            None,
            "p.adl.G13",
            None,
            "13a",
            None,
            None,
            "Sale of Land",
            "papyrus",
            None,
        ),
        (
            "HGV_meta_EpiDoc/HGV1/13b.xml",
            13,
            None,
            None,
            None,
            "p.adl.G13",
            None,
            "13b",
            None,
            None,
            "Receipt for Sales Tax",
            "papyrus",
            "Cairo",
        ),
    ]
    keyword_rows = [
        (1, 13, "hgv", None, "prose", True),
        (2, 13, "hgv", "culture", "literature", False),
    ]
    cursor = DumpCursor([papyri_rows, keyword_rows])
    connection = RecordingConnection(cursor)
    connect_calls = []

    def connect(conninfo, **kwargs):
        connect_calls.append((conninfo, kwargs))
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)

    dump_metadata_tables(
        tmp_path / "metadata-csv",
        "postgresql://metadata.example/scrapyrus",
        application_name="scrapyrus-test",
    )

    assert connect_calls == [
        (
            "postgresql://metadata.example/scrapyrus",
            {"application_name": "scrapyrus-test"},
        )
    ]
    assert len(cursor.executions) == 2
    with (tmp_path / "metadata-csv" / "papyri.csv").open(
        encoding="utf-8", newline=""
    ) as csv_file:
        dumped_papyri = list(csv.reader(csv_file))

    assert dumped_papyri == [
        list(PapyrusMetadataTable().columns),
        [
            "HGV_meta_EpiDoc/HGV1/13a.xml",
            "13",
            "",
            "",
            "",
            "p.adl.G13",
            "",
            "13a",
            "",
            "",
            "Sale of Land",
            "papyrus",
            "",
        ],
        [
            "HGV_meta_EpiDoc/HGV1/13b.xml",
            "13",
            "",
            "",
            "",
            "p.adl.G13",
            "",
            "13b",
            "",
            "",
            "Receipt for Sales Tax",
            "papyrus",
            "Cairo",
        ],
    ]
    with (tmp_path / "metadata-csv" / "keywords.csv").open(
        encoding="utf-8", newline=""
    ) as csv_file:
        dumped_keywords = list(csv.reader(csv_file))

    assert dumped_keywords == [
        list(KeywordMetadataTable().columns),
        ["1", "13", "hgv", "", "prose", "True"],
        ["2", "13", "hgv", "culture", "literature", "False"],
    ]


def test_ingest_metadata_prints_processed_file_on_validation_error(
    tmp_path, monkeypatch, capsys
):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "invalid.xml"
    _write_minimal_metadata(metadata, tm_id=0)
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)

    def connect(conninfo, **kwargs):
        return connection

    def iterate(idp_data, *, progressbar):
        yield "invalid", metadata, None, None

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr("scrapyrus.ingestion.iterate_idpdata_triples", iterate)

    with pytest.raises(ValidationError):
        ingest_metadata(idp_data, progressbar=False)

    captured = capsys.readouterr()
    assert f"Failed while processing metadata file: {metadata}" in captured.err


def test_ingest_metadata_prints_processed_file_on_saxon_error(
    tmp_path, monkeypatch, capsys
):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "malformed.xml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("<TEI><teiHeader></TEI>", encoding="utf-8")
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)

    def connect(conninfo, **kwargs):
        return connection

    def iterate(idp_data, *, progressbar):
        yield "malformed", metadata, None, None

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr("scrapyrus.ingestion.iterate_idpdata_triples", iterate)

    with pytest.raises(PySaxonApiError):
        ingest_metadata(idp_data, progressbar=False)

    captured = capsys.readouterr()
    assert f"Failed while processing metadata file: {metadata}" in captured.err
