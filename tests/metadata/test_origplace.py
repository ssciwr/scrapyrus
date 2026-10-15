import pytest
from saxonche import PySaxonProcessor

from scrapyrus.metadata.origplace import OrigPlaceModelFactory


def test_orig_place_model_factory_extracts_ancient_provenance_places(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt>
                <idno type="TM">555</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin>
                      <origPlace>Found: Pathyris (Pathyrites, Egypt); written: Pathyris (Pathyrites, Egypt)</origPlace>
                    </origin>
                    <provenance type="found">
                      <placeName type="ancient">Ignored direct child</placeName>
                      <p>
                        <placeName type="ancient"
                                   subtype="nome"
                                   ref="https://www.trismegistos.org/place/2849 https://pleiades.stoa.org/places/756999">Pathyrites</placeName>
                        <placeName type="ancient" subtype="region">Egypt</placeName>
                        <placeName type="ancient"
                                   ref="https://pleiades.stoa.org/places/756888 https://www.trismegistos.org/place/1628">Pathyris</placeName>
                        <placeName type="modern">Cairo</placeName>
                      </p>
                    </provenance>
                    <provenance type="composed">
                      <p>
                        <placeName type="ancient" subtype="region">Egypt</placeName>
                      </p>
                    </provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
            "place_id": 1,
            "tm_id": 555,
            "full_place_name": (
                "Found: Pathyris (Pathyrites, Egypt); written: "
                "Pathyris (Pathyrites, Egypt)"
            ),
            "place_name": "Pathyrites",
            "uncertain": False,
            "tm_place_id": 2849,
            "pleiades_place_id": 756999,
            "place_type": "found",
            "granularity": "nome",
        },
        {
            "place_id": 2,
            "tm_id": 555,
            "full_place_name": (
                "Found: Pathyris (Pathyrites, Egypt); written: "
                "Pathyris (Pathyrites, Egypt)"
            ),
            "place_name": "Egypt",
            "uncertain": False,
            "tm_place_id": None,
            "pleiades_place_id": None,
            "place_type": "found",
            "granularity": "region",
        },
        {
            "place_id": 3,
            "tm_id": 555,
            "full_place_name": (
                "Found: Pathyris (Pathyrites, Egypt); written: "
                "Pathyris (Pathyrites, Egypt)"
            ),
            "place_name": "Pathyris",
            "uncertain": False,
            "tm_place_id": 1628,
            "pleiades_place_id": 756888,
            "place_type": "found",
            "granularity": "settlement",
        },
        {
            "place_id": 4,
            "tm_id": 555,
            "full_place_name": (
                "Found: Pathyris (Pathyrites, Egypt); written: "
                "Pathyris (Pathyrites, Egypt)"
            ),
            "place_name": "Egypt",
            "uncertain": False,
            "tm_place_id": None,
            "pleiades_place_id": None,
            "place_type": "composed",
            "granularity": "region",
        },
    ]


def test_orig_place_model_factory_skips_values_outside_schema_literals(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt>
                <idno type="TM">42</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin>
                      <origPlace>Alexandria</origPlace>
                    </origin>
                    <provenance type="stored">
                      <p>
                        <placeName type="ancient">Stored place</placeName>
                      </p>
                    </provenance>
                    <provenance type="located">
                      <p>
                        <placeName type="ancient" subtype="province">Aegyptus</placeName>
                        <placeName type="ancient">Alexandria</placeName>
                      </p>
                    </provenance>
                    <provenance>
                      <p>
                        <placeName type="ancient" subtype="region">Egypt</placeName>
                      </p>
                    </provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
            "place_id": 1,
            "tm_id": 42,
            "full_place_name": "Alexandria",
            "place_name": "Alexandria",
            "uncertain": False,
            "tm_place_id": None,
            "pleiades_place_id": None,
            "place_type": "located",
            "granularity": "settlement",
        },
        {
            "place_id": 2,
            "tm_id": 42,
            "full_place_name": "Alexandria",
            "place_name": "Egypt",
            "uncertain": False,
            "tm_place_id": None,
            "pleiades_place_id": None,
            "place_type": None,
            "granularity": "region",
        },
    ]


def test_orig_place_model_factory_expands_multiple_tm_place_ids(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt>
                <idno type="TM">37313</idno>
              </publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin>
                      <origPlace>Kynopolis</origPlace>
                    </origin>
                    <provenance type="located">
                      <p>
                        <placeName type="ancient"
                                   cert="low"
                                   ref="https://pleiades.stoa.org/places/736949 https://www.trismegistos.org/place/3389 https://www.trismegistos.org/place/1195 https://www.trismegistos.org/place/5392">Kynopolis</placeName>
                      </p>
                    </provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [model.model_dump() for model in models] == [
        {
            "place_id": 1,
            "tm_id": 37313,
            "full_place_name": "Kynopolis",
            "place_name": "Kynopolis",
            "uncertain": True,
            "tm_place_id": 3389,
            "pleiades_place_id": 736949,
            "place_type": "located",
            "granularity": "settlement",
        },
        {
            "place_id": 2,
            "tm_id": 37313,
            "full_place_name": "Kynopolis",
            "place_name": "Kynopolis",
            "uncertain": True,
            "tm_place_id": 1195,
            "pleiades_place_id": 736949,
            "place_type": "located",
            "granularity": "settlement",
        },
        {
            "place_id": 3,
            "tm_id": 37313,
            "full_place_name": "Kynopolis",
            "place_name": "Kynopolis",
            "uncertain": True,
            "tm_place_id": 5392,
            "pleiades_place_id": 736949,
            "place_type": "located",
            "granularity": "settlement",
        },
    ]


def test_orig_place_model_factory_prefers_cert_low_and_cleans_all_markers(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt><idno type="TM">99</idno></publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin><origPlace>Memphis (?) or Arsinoites (?)</origPlace></origin>
                    <provenance type="located">
                      <p>
                        <placeName type="ancient" cert="low">Memphis</placeName>
                        <placeName type="ancient" subtype="nome">Arsinoites (?)</placeName>
                        <placeName type="ancient" subtype="region">Egypt</placeName>
                      </p>
                    </provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [(model.place_name, model.uncertain) for model in models] == [
        ("Memphis", True),
        ("Arsinoites", False),
        ("Egypt", False),
    ]


def test_orig_place_model_factory_prefers_literal_markers_to_fallback(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt><idno type="TM">100</idno></publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin><origPlace>Memphis or Arsinoites (?)</origPlace></origin>
                    <provenance type="located">
                      <p>
                        <placeName type="ancient">Memphis</placeName>
                        <placeName type="ancient" subtype="nome">Arsinoites (?)</placeName>
                        <placeName type="ancient" subtype="region">Egypt</placeName>
                      </p>
                    </provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [(model.place_name, model.uncertain) for model in models] == [
        ("Memphis", False),
        ("Arsinoites", True),
        ("Egypt", False),
    ]


def test_orig_place_model_factory_fallback_marks_most_specific_ties(tmp_path):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt><idno type="TM">101</idno></publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin><origPlace>Memphis or Thebes (?)</origPlace></origin>
                    <provenance type="located">
                      <p>
                        <placeName type="ancient">Memphis</placeName>
                        <placeName type="ancient">Thebes</placeName>
                        <placeName type="ancient" subtype="nome">Memphites</placeName>
                        <placeName type="ancient" subtype="region">Egypt</placeName>
                      </p>
                    </provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [(model.place_name, model.uncertain) for model in models] == [
        ("Memphis", True),
        ("Thebes", True),
        ("Memphites", False),
        ("Egypt", False),
    ]


@pytest.mark.parametrize(
    ("place_nodes", "expected"),
    [
        (
            """
            <placeName type="ancient" subtype="nome">Arsinoites</placeName>
            <placeName type="ancient" subtype="nome">Herakleopolites</placeName>
            <placeName type="ancient" subtype="region">Egypt</placeName>
            """,
            [
                ("Arsinoites", True),
                ("Herakleopolites", True),
                ("Egypt", False),
            ],
        ),
        (
            '<placeName type="ancient" subtype="region">Egypt</placeName>',
            [("Egypt", True)],
        ),
    ],
)
def test_orig_place_model_factory_fallback_supports_broader_granularities(
    tmp_path, place_nodes, expected
):
    metadata = tmp_path / "metadata.xml"
    metadata.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <publicationStmt><idno type="TM">102</idno></publicationStmt>
              <sourceDesc>
                <msDesc>
                  <history>
                    <origin><origPlace>Unknown (?)</origPlace></origin>
                    <provenance type="located"><p>{place_nodes}</p></provenance>
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
        models = OrigPlaceModelFactory(proc).parse(str(metadata))

    assert [(model.place_name, model.uncertain) for model in models] == expected
