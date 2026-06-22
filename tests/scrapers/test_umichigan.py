import pytest

from scrapyrus.scrapers.iiif import IIIFImageScraper
from scrapyrus.scrapers.umichigan import UMichiganScraper


def test_umichigan_scraper_responsibility():
    scraper = UMichiganScraper()

    assert scraper.responsible("http://quod.lib.umich.edu/a/apis/x-3043")
    assert scraper.responsible("https://quod.lib.umich.edu/a/apis/x-14401/")
    assert scraper.responsible(
        "https://quod.lib.umich.edu/a/apis/x-3043?view=thumbnail"
    )
    assert not scraper.responsible(
        "https://quod.lib.umich.edu/a/apis/x-3043/6954R_A.TIF"
    )
    assert not scraper.responsible("https://quod.lib.umich.edu/b/basp/example/76")
    assert not scraper.responsible("https://quod.lib.umich.edu/a/apis?q=3043")
    assert not scraper.responsible("https://quod.lib.umich.edu.example/a/apis/x-3043")


def test_umichigan_scraper_reuses_iiif_image_scraper():
    assert issubclass(UMichiganScraper, IIIFImageScraper)


def test_umichigan_scraper_builds_manifest_url_without_requesting_source_page():
    source_url = "http://quod.lib.umich.edu/a/apis/x-3043"

    assert UMichiganScraper().manifest_urls(source_url, session=None) == [
        "https://quod.lib.umich.edu/cgi/i/image/api/manifest/apis:3043"
    ]


def test_umichigan_scraper_rejects_unsupported_manifest_source():
    with pytest.raises(ValueError, match="Unsupported University of Michigan APIS URL"):
        UMichiganScraper().manifest_urls(
            "https://quod.lib.umich.edu/a/apis/x-3043/image.tif",
            session=None,
        )
