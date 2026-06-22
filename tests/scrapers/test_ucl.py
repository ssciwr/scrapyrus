import pytest

from scrapyrus.scrapers.ucl import UCLScraper


class FakeResponse:
    def __init__(self, url, *, text="", chunks=()):
        self.url = url
        self.text = text
        self.chunks = chunks

    def raise_for_status(self):
        pass

    def iter_content(self, *, chunk_size):
        assert chunk_size == 64 * 1024
        return iter(self.chunks)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        pass


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.responses[url]

    def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.responses[url]

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        pass


def test_ucl_scraper_responsibility():
    scraper = UCLScraper()

    numeric_url = (
        "http://petriecat.museums.ucl.ac.uk/dispatcher.aspx?"
        "action=search&database=ChoiceUCLPC&"
        "search=accession_number=%20%27UC32465%27"
    )
    suffixed_url = (
        "https://petriecat.museums.ucl.ac.uk/DISPATCHER.ASPX?"
        "action=SEARCH&database=choiceuclpc&"
        "search=accession_number%3D%20%27UC32835%20a-B%27"
    )
    assert scraper.responsible(numeric_url)
    assert scraper.responsible(suffixed_url)
    assert scraper._legacy_accession_number(numeric_url) == "UC32465"
    assert scraper._legacy_accession_number(suffixed_url) == "UC32835"
    assert not scraper.responsible(
        "http://petriecat.museums.ucl.ac.uk/dispatcher.aspx?"
        "action=search&database=ChoiceUCLPC"
    )
    assert not scraper.responsible(
        "http://petriecat.museums.ucl.ac.uk/dispatcher.aspx?"
        "action=search&database=Other&search=accession_number=%27UC32465%27"
    )
    assert not scraper.responsible(
        "http://petriecat.museums.ucl.ac.uk.example/dispatcher.aspx?"
        "action=search&database=ChoiceUCLPC&"
        "search=accession_number=%27UC32465%27"
    )


def test_ucl_scraper_extracts_full_image_links():
    page_url = "https://collections.ucl.ac.uk/Details/collect/66916"
    first_image_url = (
        "https://collections.ucl.ac.uk/AxiellWebApi/wwwopac.ashx?"
        "command=getcontent&server=images&"
        "value=Petrie%20Museum%5CObjects%5CUC32465.jpg&imageformat=jpg"
    )
    second_image_url = (
        "https://collections.ucl.ac.uk/AxiellWebApi/wwwopac.ashx?"
        "command=getcontent&server=images&"
        "value=Petrie%20Museum%5CObjects%5CUC32465v.jpg&imageformat=jpg"
    )
    html = f"""
        <a class="ais-detail-image-viewer-link" href="{first_image_url}">
          <img src="{first_image_url}&amp;width=400&amp;height=400">
        </a>
        <a href="{second_image_url}">second image</a>
        <a href="{first_image_url}">duplicate</a>
        <a href="https://example.com/AxiellWebApi/wwwopac.ashx?command=getcontent&amp;server=images&amp;value=external.jpg">
          external
        </a>
        <a href="/AxiellWebApi/wwwopac.ashx?command=metadata&amp;server=images&amp;value=metadata.xml">
          metadata
        </a>
    """

    assert UCLScraper._image_urls(html, page_url) == [
        first_image_url,
        second_image_url,
    ]


def test_ucl_scraper_downloads_images_from_matching_record(tmp_path, monkeypatch):
    source_url = (
        "http://petriecat.museums.ucl.ac.uk/dispatcher.aspx?"
        "action=search&database=ChoiceUCLPC&"
        "search=accession_number=%20%27UC32465%27"
    )
    search_url = "https://collections.ucl.ac.uk/search/expert"
    results_url = "https://collections.ucl.ac.uk/results"
    record_url = "https://collections.ucl.ac.uk/Details/collect/66916"
    image_url = (
        "https://collections.ucl.ac.uk/AxiellWebApi/wwwopac.ashx?"
        "command=getcontent&server=images&"
        "value=Petrie%20Museum%5CObjects%5CUC32465.jpg&imageformat=jpg"
    )
    results_html = """
        <a href="/Details/collect/66916">LDUCE-UC32465</a>
        <a href="https://example.com/Details/collect/123">unrelated</a>
    """
    record_html = f"""
        <img src="{image_url}&amp;width=400&amp;height=400">
        <a class="ais-detail-image-viewer-link" href="{image_url}">full image</a>
    """
    session = FakeSession(
        {
            search_url: FakeResponse(results_url, text=results_html),
            record_url: FakeResponse(record_url, text=record_html),
            image_url: FakeResponse(image_url, chunks=(b"UCL ", b"image")),
        }
    )
    monkeypatch.setattr("scrapyrus.scrapers.ucl.requests.Session", lambda: session)

    UCLScraper().download(source_url, tmp_path)

    assert (tmp_path / "UC32465.jpg").read_bytes() == b"UCL image"
    assert session.requests == [
        (
            "POST",
            search_url,
            {
                "data": UCLScraper._search_data("UC32465"),
                "timeout": 30,
            },
        ),
        ("GET", record_url, {"timeout": 30}),
        ("GET", image_url, {"timeout": 30, "stream": True}),
    ]


def test_ucl_scraper_rejects_missing_or_ambiguous_search_results():
    with pytest.raises(ValueError, match="returned 0 records"):
        UCLScraper._record_url(
            "<p>No results</p>",
            "https://collections.ucl.ac.uk/results",
            "UC32465",
        )

    with pytest.raises(ValueError, match="returned 2 records"):
        UCLScraper._record_url(
            """
            <a href="/Details/collect/1">first</a>
            <a href="/Details/collect/2">second</a>
            """,
            "https://collections.ucl.ac.uk/results",
            "UC32465",
        )
