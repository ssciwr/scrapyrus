from saxonche import PySaxonProcessor

from scrapyrus.metadata.origdate import OrigDateModelFactory


def test_orig_date_model_factory_extracts_machine_readable_dates(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt>
                <idno type="TM">46</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin>
                      <origDate when="0582-01-09" cert="low">9 Jan. 582</origDate>
                      <origDate xml:id="dateAlternativeX"
                                notBefore="-0075-06-08"
                                notAfter="-0075-07-07"
                                precision="low">
                        <certainty locus="value" match="../year-from-date(@notBefore)"/>8 June - 7 July 75 BCE
                      </origDate>
                      <origDate when-custom="0300-02-29"
                                datingMethod="#julian">29 Feb. 300</origDate>
                      <origDate>unbekannt</origDate>
                    </origin>
                  </history>
                </msDesc>
              </sourceDesc>
            </fileDesc>
          </teiHeader>
        </TEI>
        """,
        encoding="utf-8",
    )

    with PySaxonProcessor(license=False) as proc:
        models = OrigDateModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
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
        },
        {
            "date_id": 2,
            "tm_id": 46,
            "date_text": "8 June - 7 July 75 BCE",
            "certainty": None,
            "precision": "low",
            "not_before_year": -75,
            "not_before_month": 6,
            "not_before_day": 8,
            "not_after_year": -75,
            "not_after_month": 7,
            "not_after_day": 7,
            "alternative": True,
        },
        {
            "date_id": 3,
            "tm_id": 46,
            "date_text": "29 Feb. 300",
            "certainty": None,
            "precision": None,
            "not_before_year": 300,
            "not_before_month": 2,
            "not_before_day": 29,
            "not_after_year": 300,
            "not_after_month": 2,
            "not_after_day": 29,
            "alternative": False,
        },
    ]
