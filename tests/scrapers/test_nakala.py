from scrapyrus.scrapers.nakala import NakalaScraper


class FakeResponse:
    def __init__(self, *, headers=None, chunks=()):
        self.headers = {} if headers is None else headers
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


def test_nakala_scraper_responsibility():
    scraper = NakalaScraper()
    image_path = "/iiif/10.34847/nkl.7b5d1i0d/1517428b4533d42a994d53e8cc8f64d6f70a3d7e"

    assert scraper.responsible("https://api.nakala.fr" + image_path)
    assert scraper.responsible("http://api.nakala.fr" + image_path + "/")
    assert not scraper.responsible(
        "https://nakala.fr/10.34847/nkl.7b5d1i0d"
        "#1517428b4533d42a994d53e8cc8f64d6f70a3d7e"
    )
    assert not scraper.responsible("https://api.nakala.fr" + image_path + "/info.json")
    assert not scraper.responsible("https://api.nakala.fr.example" + image_path)


def test_nakala_scraper_downloads_direct_image_using_response_filename(
    tmp_path, monkeypatch
):
    image_url = (
        "https://api.nakala.fr/iiif/10.34847/nkl.7b5d1i0d/"
        "1517428b4533d42a994d53e8cc8f64d6f70a3d7e"
    )
    response = FakeResponse(
        headers={"Content-Disposition": 'inline; filename="OKrok87-3 image.JPG"'},
        chunks=(b"image ", b"contents"),
    )
    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return response

    monkeypatch.setattr("scrapyrus.scrapers.nakala.requests.get", fake_get)

    NakalaScraper().download(image_url, tmp_path)

    assert (tmp_path / "OKrok87-3 image.JPG").read_bytes() == b"image contents"
    assert requests == [(image_url, {"timeout": 30, "stream": True})]


def test_nakala_scraper_uses_identifier_and_content_type_without_filename(
    tmp_path, monkeypatch
):
    identifier = "1517428b4533d42a994d53e8cc8f64d6f70a3d7e"
    image_url = f"https://api.nakala.fr/iiif/10.34847/nkl.7b5d1i0d/{identifier}"
    response = FakeResponse(
        headers={"Content-Type": "image/png; charset=binary"},
        chunks=(b"png",),
    )
    monkeypatch.setattr(
        "scrapyrus.scrapers.nakala.requests.get", lambda url, **kwargs: response
    )

    NakalaScraper().download(image_url, tmp_path)

    assert (tmp_path / f"{identifier}.png").read_bytes() == b"png"
