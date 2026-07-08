from saxonche import PySaxonProcessor

from scrapyrus.metadata.keywords import KeywordModelFactory


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
