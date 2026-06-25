import pytest

from scrapyrus.scrapers.iiif import IIIFImageScraper
from scrapyrus.scrapers.uni_hamburg import UniHamburgScraper


def test_uni_hamburg_scraper_responsibility():
    scraper = UniHamburgScraper()

    assert scraper.responsible("http://resolver.sub.uni-hamburg.de/goobi/HANSh574")
    assert scraper.responsible("https://resolver.sub.uni-hamburg.de/kitodo/HANSh3950")
    assert scraper.responsible(
        "https://resolver.sub.uni-hamburg.de/goobi/HANSh574?lang=de"
    )
    assert not scraper.responsible(
        "https://resolver.sub.uni-hamburg.de/kitodo/HANSh574/page/1"
    )
    assert not scraper.responsible(
        "https://digitalisate.sub.uni-hamburg.de/recherche/detail?tx_dlf%5Bid%5D=14203"
    )
    assert not scraper.responsible(
        "https://resolver.sub.uni-hamburg.de.example/goobi/HANSh574"
    )
    assert not scraper.responsible("ftp://resolver.sub.uni-hamburg.de/goobi/HANSh574")


def test_uni_hamburg_scraper_reuses_iiif_image_scraper():
    assert issubclass(UniHamburgScraper, IIIFImageScraper)


def test_uni_hamburg_scraper_builds_manifest_url_without_requesting_source_page():
    assert UniHamburgScraper().manifest_urls(
        "http://resolver.sub.uni-hamburg.de/goobi/HANSh574",
        session=None,
    ) == ["https://iiif.sub.uni-hamburg.de/object/HANSh574/manifest"]
    assert UniHamburgScraper().manifest_urls(
        "https://resolver.sub.uni-hamburg.de/kitodo/HANSh3950?lang=de",
        session=None,
    ) == ["https://iiif.sub.uni-hamburg.de/object/HANSh3950/manifest"]


def test_uni_hamburg_scraper_rejects_unsupported_manifest_source():
    with pytest.raises(ValueError, match="Unsupported Uni Hamburg URL"):
        UniHamburgScraper().manifest_urls(
            "https://resolver.sub.uni-hamburg.de/kitodo/HANSh574/page/1",
            session=None,
        )
