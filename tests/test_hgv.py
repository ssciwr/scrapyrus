from types import GeneratorType

from scrapyrus.hgv import iterate_hgv_triples


def test_iterate_hgv_triples_returns_generator(idp_data):
    triples = iterate_hgv_triples(idp_data)

    assert isinstance(triples, GeneratorType)


def test_iterate_hgv_triples_finds_associated_files(idp_data):
    expected_ids = {"1", "53", "272"}
    results = {}

    for triple in iterate_hgv_triples(idp_data, progressbar=False):
        if triple[0] in expected_ids:
            results[triple[0]] = triple
        if results.keys() == expected_ids:
            break

    assert results["1"] == (
        "1",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "1.xml",
        idp_data / "DDB_EpiDoc_XML" / "p.adl" / "p.adl.G2.xml",
        None,
    )
    assert results["53"] == (
        "53",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "53.xml",
        idp_data / "DDB_EpiDoc_XML" / "p.ryl" / "p.ryl.4" / "p.ryl.4.581.xml",
        idp_data / "HGV_trans_EpiDoc" / "53.xml",
    )
    assert results["272"] == (
        "272",
        idp_data / "HGV_meta_EpiDoc" / "HGV1" / "272.xml",
        None,
        None,
    )


def test_iterate_hgv_triples_shows_progressbar_by_default(idp_data, monkeypatch):
    progress = {}

    def fake_tqdm(iterable, *, total, unit):
        progress.update(iterable=iterable, total=total, unit=unit)
        return iterable

    monkeypatch.setattr("scrapyrus.hgv.tqdm", fake_tqdm)

    next(iterate_hgv_triples(idp_data))

    assert progress["total"] == len(progress["iterable"])
    assert progress["unit"] == "record"
