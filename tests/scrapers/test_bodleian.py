import pytest

from scrapyrus.scrapers.bodleian import BodleianScraper
from scrapyrus.scrapers.iiif import IIIFImageScraper


def test_bodleian_scraper_responsibility():
    scraper = BodleianScraper()

    assert scraper.responsible(
        "https://digital.bodleian.ox.ac.uk/objects/"
        "5f5ed198-704b-4770-878c-7aa16d3c1be5/"
    )
    assert scraper.responsible(
        "http://digital.bodleian.ox.ac.uk/objects/140fe333-8238-4a8a-a364-9ed13edcdb46"
    )
    assert scraper.responsible(
        "https://digital.bodleian.ox.ac.uk/objects/"
        "33b62b04-fd21-4ce9-9ee4-d250cc91a61a/?search=papyrus"
    )
    assert not scraper.responsible(
        "https://digital.bodleian.ox.ac.uk/objects/"
        "5f5ed198-704b-4770-878c-7aa16d3c1be5/viewer/"
    )
    assert not scraper.responsible(
        "https://digital.bodleian.ox.ac.uk/objects/not-a-uuid/"
    )
    assert not scraper.responsible(
        "https://digital.bodleian.ox.ac.uk.example/objects/"
        "5f5ed198-704b-4770-878c-7aa16d3c1be5/"
    )
    assert not scraper.responsible(
        "ftp://digital.bodleian.ox.ac.uk/objects/5f5ed198-704b-4770-878c-7aa16d3c1be5/"
    )


def test_bodleian_scraper_reuses_iiif_image_scraper():
    assert issubclass(BodleianScraper, IIIFImageScraper)


def test_bodleian_scraper_builds_manifest_url_without_requesting_source_page():
    assert BodleianScraper().manifest_urls(
        "https://digital.bodleian.ox.ac.uk/objects/"
        "5f5ed198-704b-4770-878c-7aa16d3c1be5/?search=papyrus",
        session=None,
    ) == [
        "https://iiif.bodleian.ox.ac.uk/iiif/manifest/"
        "5f5ed198-704b-4770-878c-7aa16d3c1be5.json"
    ]


def test_bodleian_scraper_rejects_unsupported_manifest_source():
    with pytest.raises(ValueError, match="Unsupported Bodleian URL"):
        BodleianScraper().manifest_urls(
            "https://digital.bodleian.ox.ac.uk/objects/"
            "5f5ed198-704b-4770-878c-7aa16d3c1be5/viewer/",
            session=None,
        )
