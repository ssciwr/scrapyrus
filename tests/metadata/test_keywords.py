import pytest
from saxonche import PySaxonProcessor

from scrapyrus.metadata.keywords import KeywordModelFactory, _keyword_values


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Brief", (("Brief", False, None, False),)),
        ("Brief (?)", (("Brief", True, None, False),)),
        ("bible?", (("bible", True, None, False),)),
        ("Brief (privat)", (("Brief", False, "privat", False),)),
        ("Brief (?, privat)", (("Brief", True, "privat", False),)),
        ("Brief (privat?)", (("Brief", False, "privat", True),)),
        (
            "Brief (privat, verloren)",
            (
                ("Brief", False, "privat", False),
                ("Brief", False, "verloren", False),
            ),
        ),
        (
            "Brief (?, privat?, verloren)",
            (
                ("Brief", True, "privat", True),
                ("Brief", True, "verloren", False),
            ),
        ),
        (
            "  Brief   (  ? ,  privat ? , verloren  ) ",
            (
                ("Brief", True, "privat", True),
                ("Brief", True, "verloren", False),
            ),
        ),
        (
            "Angst vor Anschlag? (Mord)",
            (("Angst vor Anschlag", True, "Mord", False),),
        ),
        (
            "Notiz (?) über Zahlung von Geld (?)",
            (("Notiz über Zahlung von Geld", True, None, False),),
        ),
        (
            "Korrespondenz (amtlich) des Dioiketen",
            (("Korrespondenz (amtlich) des Dioiketen", False, None, False),),
        ),
        ("", ()),
        ("?", ()),
        ("(?)", ()),
    ],
)
def test_keyword_values(source, expected):
    assert _keyword_values(source) == expected


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
                  <term>Brief (privat)</term>
                  <term>Brief (?, amtlich)</term>
                  <term>Brief (privat, verloren)</term>
                  <term>Brief (geschäftlich?)</term>
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
            "qualifier": None,
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 2,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "bible",
            "uncertain": True,
            "qualifier": None,
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 3,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "Brief",
            "uncertain": False,
            "qualifier": "privat",
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 4,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "Brief",
            "uncertain": True,
            "qualifier": "amtlich",
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 5,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "Brief",
            "uncertain": False,
            "qualifier": "privat",
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 6,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "Brief",
            "uncertain": False,
            "qualifier": "verloren",
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 7,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": None,
            "keyword": "Brief",
            "uncertain": False,
            "qualifier": "geschäftlich",
            "qualifier_uncertain": True,
        },
        {
            "keyword_id": 8,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": "culture",
            "keyword": "literature",
            "uncertain": False,
            "qualifier": None,
            "qualifier_uncertain": False,
        },
        {
            "keyword_id": 9,
            "tm_id": 46,
            "scheme": "hgv",
            "keyword_type": "religion",
            "keyword": "christian",
            "uncertain": False,
            "qualifier": None,
            "qualifier_uncertain": False,
        },
    ]
