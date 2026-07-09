from saxonche import PySaxonProcessor

from scrapyrus.metadata.principal_edition import PrincipalEditionModelFactory


def test_principal_edition_model_factory_extracts_principal_bibliography(tmp_path):
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
              <div type="bibliography" subtype="principalEdition">
                <listBibl>
                  <bibl>
                    <ptr target="https://example.invalid/not-biblio/123"/>
                    <ptr target="http://papyri.info/biblio/95120"/>
                    <title type="abbreviated">P.Oxy. 7</title>
                    <title type="main">The Oxyrhynchus Papyri VII</title>
                    <title type="translated">Ignored lower-precedence title</title>
                    <author>Jane Smith</author>
                    <biblScope unit="volume">7</biblScope>
                    <biblScope unit="number">12</biblScope>
                    <biblScope unit="page">34-36</biblScope>
                  </bibl>
                  <bibl>
                    <title type="translated">Ignored fallback title</title>
                    <title type="abbreviated">SB 20</title>
                    <author>
                      <forename>John</forename>
                      <surname>Doe</surname>
                    </author>
                    <biblScope type="volume">20</biblScope>
                    <biblScope type="numbers">14206</biblScope>
                    <biblScope type="pages">12-13</biblScope>
                  </bibl>
                  <bibl>
                    <title type="translated">Fallback title</title>
                  </bibl>
                </listBibl>
              </div>
              <div type="bibliography" subtype="otherPublications">
                <listBibl>
                  <bibl>
                    <title type="main">Other publication</title>
                  </bibl>
                </listBibl>
              </div>
              <div type="commentary" subtype="principalEdition">
                <listBibl>
                  <bibl>
                    <title type="main">Commentary bibliography</title>
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
        models = PrincipalEditionModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
            "principal_edition_id": 1,
            "tm_id": 46,
            "biblio_id": 95120,
            "title": "The Oxyrhynchus Papyri VII",
            "author": "Jane Smith",
            "volume": "7",
            "number": "12",
            "page": "34-36",
        },
        {
            "principal_edition_id": 2,
            "tm_id": 46,
            "biblio_id": None,
            "title": "SB 20",
            "author": "John Doe",
            "volume": "20",
            "number": "14206",
            "page": "12-13",
        },
        {
            "principal_edition_id": 3,
            "tm_id": 46,
            "biblio_id": None,
            "title": "Fallback title",
            "author": None,
            "volume": None,
            "number": None,
            "page": None,
        },
    ]
