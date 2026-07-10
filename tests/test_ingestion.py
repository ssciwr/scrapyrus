import csv

import psycopg
import pytest
from pydantic import ValidationError
from saxonche import PySaxonApiError

from scrapyrus.ingestion import dump_metadata_tables, ingest_metadata
from scrapyrus.metadata import (
    AncientEditionMetadataTable,
    KeywordMetadataTable,
    OrigDateMetadataTable,
    OrigPlaceMetadataTable,
    PapyrusMetadataTable,
    PrincipalEditionMetadataTable,
)


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
                  <history>
                    <origin>
                      <origPlace>Philadelphia? (Arsinoites)</origPlace>
                      <origDate when="0582-01-09" cert="low">9 Jan. 582</origDate>
                    </origin>
                    <provenance type="located">
                      <p>
                        <placeName type="ancient"
                                   ref="https://pleiades.stoa.org/places/737008 https://www.trismegistos.org/place/1760">Philadelphia</placeName>
                        <placeName type="ancient"
                                   subtype="region">Ägypten</placeName>
                        <placeName type="modern">Philadelphia</placeName>
                      </p>
                    </provenance>
                  </history>
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
          <text>
            <body>
              <div type="bibliography" subtype="ancientEdition">
                <listBibl>
                  <bibl type="publication" subtype="ancient">
                    <author ref="http://data.perseus.org/catalog/urn:cts:greekLit:tlg0012">Homerus</author>
                    <title type="main"
                           level="m"
                           ref="http://www.trismegistos.org/authorwork/511">Ilias</title>
                  </bibl>
                </listBibl>
              </div>
              <div type="bibliography" subtype="principalEdition">
                <listBibl>
                  <bibl>
                    <ptr target="http://papyri.info/biblio/95120"/>
                    <title type="abbreviated">P.Oxy. 7</title>
                    <author>Jane Smith</author>
                    <biblScope unit="volume">7</biblScope>
                    <biblScope unit="number">12</biblScope>
                    <biblScope unit="page">34-36</biblScope>
                  </bibl>
                </listBibl>
              </div>
            </body>
          </text>
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
    assert (
        _normalize_sql(cursor.executions[1][0])
        == "DROP TABLE IF EXISTS principal_editions"
    )
    assert cursor.executions[1][1] is None
    assert _normalize_sql(cursor.executions[2][0]) == "DROP TABLE IF EXISTS keywords"
    assert cursor.executions[2][1] is None
    assert _normalize_sql(cursor.executions[3][0]) == "DROP TABLE IF EXISTS orig_dates"
    assert cursor.executions[3][1] is None
    assert _normalize_sql(cursor.executions[4][0]) == "DROP TABLE IF EXISTS orig_places"
    assert cursor.executions[4][1] is None
    assert (
        _normalize_sql(cursor.executions[5][0])
        == "DROP TABLE IF EXISTS ancient_editions"
    )
    assert cursor.executions[5][1] is None
    assert cursor.executions[6][0].startswith("CREATE TABLE IF NOT EXISTS papyri")
    assert cursor.executions[6][1] is None
    schema_sql = _normalize_sql(cursor.executions[6][0])
    assert "source_path text NOT NULL PRIMARY KEY" in schema_sql
    assert "CREATE INDEX" not in schema_sql
    assert "CREATE TABLE IF NOT EXISTS principal_editions" in schema_sql
    assert "principal_edition_id integer NOT NULL PRIMARY KEY" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS keywords" in schema_sql
    assert "keyword_id integer NOT NULL PRIMARY KEY" in schema_sql
    assert "uncertain boolean NOT NULL" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS orig_dates" in schema_sql
    assert "date_id integer NOT NULL PRIMARY KEY" in schema_sql
    assert "alternative boolean NOT NULL" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS orig_places" in schema_sql
    assert "place_id integer NOT NULL PRIMARY KEY" in schema_sql
    assert "granularity text NOT NULL" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS ancient_editions" in schema_sql
    assert "ancient_edition_id integer NOT NULL PRIMARY KEY" in schema_sql
    assert "perseus_author_urn text" in schema_sql
    columns = list(PapyrusMetadataTable().columns)
    assert _normalize_sql(cursor.executions[7][0]) == (
        f"INSERT INTO papyri ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert cursor.executions[7][1] == {
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
    columns = list(PrincipalEditionMetadataTable().columns)
    assert _normalize_sql(cursor.executions[8][0]) == (
        f"INSERT INTO principal_editions ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert cursor.executions[8][1] == {
        "principal_edition_id": 1,
        "tm_id": 46,
        "biblio_id": 95120,
        "title": "P.Oxy. 7",
        "author": "Jane Smith",
        "volume": "7",
        "number": "12",
        "page": "34-36",
    }
    columns = list(KeywordMetadataTable().columns)
    assert _normalize_sql(cursor.executions[9][0]) == (
        f"INSERT INTO keywords ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert [execution[1] for execution in cursor.executions[9:13]] == [
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
    columns = list(OrigDateMetadataTable().columns)
    assert _normalize_sql(cursor.executions[13][0]) == (
        f"INSERT INTO orig_dates ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert cursor.executions[13][1] == {
        "date_id": 1,
        "tm_id": 46,
        "date_text": "9 Jan. 582",
        "certainty": "low",
        "precision": None,
        "not_before_year": 582,
        "not_before_month": 1,
        "not_before_day": 9,
        "not_after_year": 582,
        "not_after_month": 1,
        "not_after_day": 9,
        "alternative": False,
    }
    columns = list(OrigPlaceMetadataTable().columns)
    assert _normalize_sql(cursor.executions[14][0]) == (
        f"INSERT INTO orig_places ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert [execution[1] for execution in cursor.executions[14:16]] == [
        {
            "place_id": 1,
            "tm_id": 46,
            "full_place_name": "Philadelphia? (Arsinoites)",
            "place_name": "Philadelphia",
            "tm_place_id": 1760,
            "pleiades_place_id": 737008,
            "place_type": "located",
            "granularity": "settlement",
        },
        {
            "place_id": 2,
            "tm_id": 46,
            "full_place_name": "Philadelphia? (Arsinoites)",
            "place_name": "Ägypten",
            "tm_place_id": None,
            "pleiades_place_id": None,
            "place_type": "located",
            "granularity": "region",
        },
    ]
    columns = list(AncientEditionMetadataTable().columns)
    assert _normalize_sql(cursor.executions[16][0]) == (
        f"INSERT INTO ancient_editions ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
    )
    assert cursor.executions[16][1] == {
        "ancient_edition_id": 1,
        "tm_id": 46,
        "title": "Ilias",
        "tm_title_id": 511,
        "author": "Homerus",
        "perseus_author_urn": "urn:cts:greekLit:tlg0012",
    }
    assert _normalize_sql(cursor.executions[17][0]) == (
        "CREATE INDEX IF NOT EXISTS papyri_tm_id_idx ON papyri (tm_id);"
    )
    assert cursor.executions[17][1] is None


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

    first_row = cursor.executions[7][1]
    second_row = cursor.executions[8][1]
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
    principal_edition_rows = [
        (1, 13, 95120, "P.Oxy. 7", "Jane Smith", "7", "12", "34-36"),
    ]
    orig_date_rows = [
        (1, 13, "9 Jan. 582", "low", None, 582, 1, 9, 582, 1, 9, False),
    ]
    orig_place_rows = [
        (
            1,
            13,
            "Found: Pathyris (Pathyrites, Egypt)",
            "Pathyris",
            1628,
            756888,
            "found",
            "settlement",
        ),
        (
            2,
            13,
            "Found: Pathyris (Pathyrites, Egypt)",
            "Egypt",
            None,
            None,
            "found",
            "region",
        ),
    ]
    ancient_edition_rows = [
        (1, 13, "Ilias", 511, "Homerus", "urn:cts:greekLit:tlg0012"),
        (2, 13, "Short Title", None, "Jane Doe", None),
    ]
    cursor = DumpCursor(
        [
            papyri_rows,
            principal_edition_rows,
            keyword_rows,
            orig_date_rows,
            orig_place_rows,
            ancient_edition_rows,
        ]
    )
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
    assert len(cursor.executions) == 6
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
    with (tmp_path / "metadata-csv" / "principal_editions.csv").open(
        encoding="utf-8", newline=""
    ) as csv_file:
        dumped_principal_editions = list(csv.reader(csv_file))

    assert dumped_principal_editions == [
        list(PrincipalEditionMetadataTable().columns),
        ["1", "13", "95120", "P.Oxy. 7", "Jane Smith", "7", "12", "34-36"],
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
    with (tmp_path / "metadata-csv" / "orig_dates.csv").open(
        encoding="utf-8", newline=""
    ) as csv_file:
        dumped_orig_dates = list(csv.reader(csv_file))

    assert dumped_orig_dates == [
        list(OrigDateMetadataTable().columns),
        [
            "1",
            "13",
            "9 Jan. 582",
            "low",
            "",
            "582",
            "1",
            "9",
            "582",
            "1",
            "9",
            "False",
        ],
    ]
    with (tmp_path / "metadata-csv" / "orig_places.csv").open(
        encoding="utf-8", newline=""
    ) as csv_file:
        dumped_orig_places = list(csv.reader(csv_file))

    assert dumped_orig_places == [
        list(OrigPlaceMetadataTable().columns),
        [
            "1",
            "13",
            "Found: Pathyris (Pathyrites, Egypt)",
            "Pathyris",
            "1628",
            "756888",
            "found",
            "settlement",
        ],
        [
            "2",
            "13",
            "Found: Pathyris (Pathyrites, Egypt)",
            "Egypt",
            "",
            "",
            "found",
            "region",
        ],
    ]
    with (tmp_path / "metadata-csv" / "ancient_editions.csv").open(
        encoding="utf-8", newline=""
    ) as csv_file:
        dumped_ancient_editions = list(csv.reader(csv_file))

    assert dumped_ancient_editions == [
        list(AncientEditionMetadataTable().columns),
        ["1", "13", "Ilias", "511", "Homerus", "urn:cts:greekLit:tlg0012"],
        ["2", "13", "Short Title", "", "Jane Doe", ""],
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
