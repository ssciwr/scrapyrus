from scrapyrus.scrapers.iiif import IIIFImageScraper


class FakeIIIFResponse:
    def __init__(self, url, *, text="", json_data=None, chunks=()):
        self.url = url
        self.text = text
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


class FakeIIIFSession:
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


def test_iiif_image_scraper_downloads_presentation_3_canvas_images(
    tmp_path, monkeypatch
):
    source_url = "https://catalogue.example/record/42"
    manifest_url = "https://iiif.example/manifest/42"
    first_image_url = "https://images.example/first/full/max/0/default.jpg"
    second_image_url = "https://images.example/second/full/max/0/default.png"
    manifest = {
        "type": "Manifest",
        "items": [
            {
                "type": "Canvas",
                "items": [
                    {
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {"type": "Image", "id": first_image_url},
                            }
                        ],
                    }
                ],
            },
            {
                "type": "Canvas",
                "items": [
                    {
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {"type": "Image", "id": second_image_url},
                            }
                        ],
                    }
                ],
            },
        ],
    }
    responses = {
        manifest_url: FakeIIIFResponse(manifest_url, json_data=manifest),
        first_image_url: FakeIIIFResponse(
            first_image_url,
            chunks=(b"first ", b"image"),
        ),
        second_image_url: FakeIIIFResponse(second_image_url, chunks=(b"second image",)),
    }
    session = FakeIIIFSession(responses)
    monkeypatch.setattr("scrapyrus.scrapers.iiif.requests.Session", lambda: session)

    class ExampleIIIFScraper(IIIFImageScraper, register=False):
        def responsible(self, url: str) -> bool:
            return True

        def manifest_urls(self, url, session):
            assert url == source_url
            return [manifest_url]

    ExampleIIIFScraper().download(source_url, tmp_path)

    assert (tmp_path / "0001.jpg").read_bytes() == b"first image"
    assert (tmp_path / "0002.png").read_bytes() == b"second image"
    assert session.requests == [
        (manifest_url, {"timeout": 30}),
        (first_image_url, {"timeout": 30, "stream": True}),
        (second_image_url, {"timeout": 30, "stream": True}),
    ]


def test_iiif_image_scraper_reads_presentation_2_and_image_service_fallback():
    direct_image_url = "https://images.example/direct.jpg"
    service_url = "https://images.example/service"
    manifest = {
        "@type": "sc:Manifest",
        "sequences": [
            {
                "canvases": [
                    {"images": [{"resource": {"@id": direct_image_url}}]},
                    {
                        "images": [
                            {
                                "resource": {
                                    "@type": "dctypes:Image",
                                    "service": {"@id": service_url},
                                }
                            }
                        ]
                    },
                ]
            }
        ],
    }

    assert IIIFImageScraper._manifest_image_urls(manifest) == [
        direct_image_url,
        service_url + "/full/full/0/default.jpg",
    ]
