from scrapyrus.scrapers.louvre import LouvreScraper


class FakeResponse:
    def __init__(self, *, json_data=None, chunks=()):
        self.json_data = json_data
        self.chunks = chunks

    def raise_for_status(self):
        pass

    def json(self):
        return self.json_data

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


def test_louvre_scraper_responsibility():
    scraper = LouvreScraper()

    assert scraper.responsible(
        "https://collections.louvre.fr/en/ark:/53355/cl010458981"
    )
    assert scraper.responsible("https://collections.louvre.fr/ark:/53355/cl010458981")
    assert not scraper.responsible(
        "https://collections.louvre.fr/en/ark:/53355/cl010458981.json"
    )
    assert not scraper.responsible(
        "https://collections.louvre.fr/en/ark:/53355/ar010458981"
    )
    assert not scraper.responsible(
        "https://collections.louvre.fr.example/en/ark:/53355/cl010458981"
    )


def test_louvre_scraper_downloads_full_images_from_json(tmp_path, monkeypatch):
    source_url = "https://collections.louvre.fr/en/ark:/53355/cl010458981"
    json_url = source_url + ".json"
    first_image_url = (
        "https://collections.louvre.fr/media/cache/large/front%20image.JPG"
    )
    second_image_url = "https://collections.louvre.fr/media/cache/large/back.png"
    thumbnail_url = "https://collections.louvre.fr/media/cache/small/front.JPG"
    responses = {
        json_url: FakeResponse(
            json_data={
                "image": [
                    {
                        "urlImage": first_image_url,
                        "urlThumbnail": thumbnail_url,
                    },
                    {"urlImage": second_image_url},
                    {"urlImage": first_image_url},
                    {"urlThumbnail": thumbnail_url},
                ]
            }
        ),
        first_image_url: FakeResponse(chunks=(b"front ", b"image")),
        second_image_url: FakeResponse(chunks=(b"back image",)),
    }
    session = FakeSession(responses)
    monkeypatch.setattr("scrapyrus.scrapers.louvre.requests.Session", lambda: session)

    LouvreScraper().download(source_url, tmp_path)

    assert (tmp_path / "front image.JPG").read_bytes() == b"front image"
    assert (tmp_path / "back.png").read_bytes() == b"back image"
    assert session.requests == [
        (json_url, {"timeout": 30}),
        (first_image_url, {"timeout": 30, "stream": True}),
        (second_image_url, {"timeout": 30, "stream": True}),
    ]
