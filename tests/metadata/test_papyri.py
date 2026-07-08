from saxonche import PySaxonProcessor

from scrapyrus.metadata.papyri import PapyrusModelFactory


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
