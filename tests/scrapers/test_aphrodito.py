from scrapyrus.scrapers.aphrodito import AphroditoScraper


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

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses[url]

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        pass


def test_aphrodito_scraper_responsibility():
    scraper = AphroditoScraper()

    assert scraper.responsible(
        "https://bipab.aphrodito.info/pages_html/P_Lond_V_1662.html"
    )
    assert scraper.responsible(
        "http://bipab.aphrodito.info/pages_html/P_Lond_V_1662.html"
    )
    assert not scraper.responsible(
        "https://bipab.aphrodito.info/images/grandes_images/P_Lond_V_1662.jpg"
    )
    assert not scraper.responsible(
        "https://bipab.aphrodito.info.example/pages_html/P_Lond_V_1662.html"
    )
    assert not scraper.responsible(
        "https://bipab.aphrodito.info/pages_html/nested/P_Lond_V_1662.html"
    )


def test_aphrodito_scraper_finds_all_large_image_links():
    page_url = "https://bipab.aphrodito.info/pages_html/P_Vat_Aphrod_7.html"
    html = """
        <a href="../images/moyennes_images/P_Vat_Aphrod_7_A.jpg">Image moyenne</a>
        <a href="../images/grandes_images/P_Vat_Aphrod_7_A.jpg">
            Grande <strong>image</strong>
        </a>
        <a href="/images/grandes_images/P_Vat_Aphrod_7_B__et__frag.jpg">
            grande&nbsp;&nbsp;IMAGE
        </a>
        <a href="../images/grandes_images/P_Vat_Aphrod_7_A.jpg">Grande image</a>
        <a href="https://example.com/unrelated.jpg">Grande image</a>
        <a href="javascript:void(0)">Grande image</a>
    """

    assert AphroditoScraper._image_urls(html, page_url) == [
        "https://bipab.aphrodito.info/images/grandes_images/P_Vat_Aphrod_7_A.jpg",
        "https://bipab.aphrodito.info/images/grandes_images/"
        "P_Vat_Aphrod_7_B__et__frag.jpg",
    ]


def test_aphrodito_scraper_downloads_all_linked_large_images(tmp_path, monkeypatch):
    page_url = "https://bipab.aphrodito.info/pages_html/P_Vat_Aphrod_7.html"
    first_image_url = (
        "https://bipab.aphrodito.info/images/grandes_images/P_Vat_Aphrod_7_A.jpg"
    )
    second_image_url = (
        "https://bipab.aphrodito.info/images/grandes_images/"
        "P_Vat_Aphrod_7_B__et__frag.jpg"
    )
    html = f"""
        <a href="{first_image_url}">Grande image </a>
        <a href="../images/grandes_images/P_Vat_Aphrod_7_B__et__frag.jpg">
            Grande image
        </a>
    """
    session = FakeSession(
        {
            page_url: FakeResponse(page_url, text=html),
            first_image_url: FakeResponse(
                first_image_url, chunks=(b"first ", b"image")
            ),
            second_image_url: FakeResponse(second_image_url, chunks=(b"second image",)),
        }
    )
    monkeypatch.setattr(
        "scrapyrus.scrapers.aphrodito.requests.Session", lambda: session
    )

    AphroditoScraper().download(page_url, tmp_path)

    assert (tmp_path / "P_Vat_Aphrod_7_A.jpg").read_bytes() == b"first image"
    assert (tmp_path / "P_Vat_Aphrod_7_B__et__frag.jpg").read_bytes() == b"second image"
    assert session.requests == [
        (page_url, {"timeout": 30}),
        (first_image_url, {"timeout": 30, "stream": True}),
        (second_image_url, {"timeout": 30, "stream": True}),
    ]
