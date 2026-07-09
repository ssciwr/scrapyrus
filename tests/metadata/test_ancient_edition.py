from saxonche import PySaxonProcessor

from scrapyrus.metadata.ancient_edition import AncientEditionModelFactory


def test_ancient_edition_model_factory_extracts_bibliography_rows(tmp_path, capsys):
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
          </teiHeader>
          <text>
            <body>
              <div type="bibliography" subtype="principal">
                <listBibl>
                  <bibl>
                    <author>Ignored Author</author>
                    <title type="main"
                           ref="http://www.trismegistos.org/authorwork/1">
                      Ignored Title
                    </title>
                  </bibl>
                </listBibl>
              </div>
              <div type="bibliography" subtype="ancientEdition">
                <listBibl>
                  <bibl type="publication" subtype="ancient">
                    <author ref="http://data.perseus.org/catalog/urn:cts:greekLit:tlg0012 http://example.test/author">
                      Homerus
                    </author>
                    <title type="abbreviated"
                           ref="http://example.test/abbreviated-title">
                      Il.
                    </title>
                    <title type="main"
                           ref="http://www.trismegistos.org/authorwork/511 http://catalog.perseus.org/catalog/urn:cts:greekLit:tlg0012.tlg001">
                      Ilias
                    </title>
                  </bibl>
                  <bibl type="publication" subtype="ancient">
                    <author>
                      <surname>Doe</surname>
                      <forename>Jane</forename>
                    </author>
                    <title type="abbreviated"
                           ref="http://example.test/non-tm-title">
                      Short Title
                    </title>
                    <title type="short">Other Title</title>
                  </bibl>
                  <bibl type="publication" subtype="ancient">
                    <author ref="http://data.perseus.org/catalog/urn:cts:greekLit:tlg0232">
                      Archilochus
                    </author>
                    <title type="short"
                           ref="http://www.trismegistos.org/authorwork/678">
                      Other Precedence Title
                    </title>
                  </bibl>
                </listBibl>
              </div>
            </body>
          </text>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        models = AncientEditionModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
            "ancient_edition_id": 1,
            "tm_id": 46,
            "title": "Ilias",
            "tm_title_id": 511,
            "author": "Homerus",
            "perseus_author_urn": "urn:cts:greekLit:tlg0012",
        },
        {
            "ancient_edition_id": 2,
            "tm_id": 46,
            "title": "Short Title",
            "tm_title_id": None,
            "author": "Jane Doe",
            "perseus_author_urn": None,
        },
        {
            "ancient_edition_id": 3,
            "tm_id": 46,
            "title": "Other Precedence Title",
            "tm_title_id": 678,
            "author": "Archilochus",
            "perseus_author_urn": "urn:cts:greekLit:tlg0232",
        },
    ]
    captured = capsys.readouterr()
    assert captured.out == ""


def test_ancient_edition_model_factory_skips_empty_bibliography_rows(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt>
                <idno type="TM">47</idno>
              </publicationStmt>
            </fileDesc>
          </teiHeader>
          <text>
            <body>
              <div type="bibliography" subtype="ancientEdition">
                <listBibl>
                  <bibl type="publication" subtype="ancient"/>
                </listBibl>
              </div>
            </body>
          </text>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        models = AncientEditionModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == []
