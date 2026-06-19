import json
from pathlib import Path

from scrapyrus.images import (
    BerlPapScraper,
    IIIFImageScraper,
    ImageScraperBase,
    OesterreichischeNationalbibliothekScraper,
    PapyrusPortalScraper,
    scrape_images,
)


def write_metadata(path: Path, urls: list[str]) -> None:
    graphics = "".join(f'<graphic url="{url}" />' for url in urls)
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        f"<text><body><div><p><figure>{graphics}</figure></p></div></body></text>"
        "</TEI>",
        encoding="utf-8",
    )


def test_image_scraper_subclasses_register_in_definition_order(monkeypatch):
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FirstScraper(ImageScraperBase):
        pass

    class SecondScraper(ImageScraperBase):
        pass

    assert ImageScraperBase.registered_scrapers() == (FirstScraper, SecondScraper)


def test_berlpap_scraper_responsibility():
    scraper = BerlPapScraper("https://berlpap.smb.museum/00312/")

    assert scraper.responsible("https://berlpap.smb.museum/00312/")
    assert scraper.responsible("http://berlpap.smb.museum/00312/")
    assert not scraper.responsible("https://berlpap.smb.museum.example/00312/")
    assert not scraper.responsible("https://example.com/00312/")


def test_berlpap_scraper_downloads_deduplicated_original_images(tmp_path, monkeypatch):
    page_url = "https://berlpap.smb.museum/00312/"
    recto_url = "https://berlpap.smb.museum/Original/P_25014_R_4_001.jpg"
    verso_url = "https://berlpap.smb.museum/Original/P_25014_V_4_001.jpg"
    html = f"""
        <table><tr><td><img src="/unrelated.jpg" /></td></tr></table>
        <table>
            <tr><td><b>Digitalisate</b>:</td></tr>
            <tr><td><a href="{recto_url}">521 dpi</a></td></tr>
            <tr><td><a href="{recto_url}">preview</a></td></tr>
            <tr><td><a href="/Original/P_25014_V_4_001.jpg">516 dpi</a></td></tr>
            <tr><td><a href="https://dfg-viewer.de/example">DFG</a></td></tr>
        </table>
    """

    class FakeResponse:
        def __init__(self, *, text="", chunks=()):
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

    responses = {
        page_url: FakeResponse(text=html),
        recto_url: FakeResponse(chunks=(b"recto ", b"image")),
        verso_url: FakeResponse(chunks=(b"verso image",)),
    }
    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return responses[url]

    monkeypatch.setattr("scrapyrus.images.requests.get", fake_get)

    BerlPapScraper(page_url).download(tmp_path)

    assert (tmp_path / "P_25014_R_4_001.jpg").read_bytes() == b"recto image"
    assert (tmp_path / "P_25014_V_4_001.jpg").read_bytes() == b"verso image"
    assert requests == [
        (page_url, {"timeout": 30}),
        (recto_url, {"timeout": 30, "stream": True}),
        (verso_url, {"timeout": 30, "stream": True}),
    ]


def test_berlpap_scraper_handles_page_without_digitalisate(tmp_path, monkeypatch):
    class FakeResponse:
        text = "<html><body>No images</body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "scrapyrus.images.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )

    BerlPapScraper("https://berlpap.smb.museum/00313/").download(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_papyrus_portal_scraper_responsibility():
    scraper = PapyrusPortalScraper(
        "https://papyri.uni-leipzig.de/receive/GiePapyri_schrift_00001050"
    )

    assert scraper.responsible(
        "https://papyri.uni-leipzig.de/receive/GiePapyri_schrift_00001050"
    )
    assert scraper.responsible(
        "http://papyri.uni-leipzig.de/rsc/viewer/example_derivate_00000001/a.jpg"
    )
    assert scraper.responsible(
        "https://www.papyrusportal.de/rsc/viewer/example_derivate_00000001/a.jpg"
    )
    assert scraper.responsible("https://papyrusportal.de/receive/example_schrift_1")
    assert not scraper.responsible(
        "https://papyri.uni-leipzig.de/receive-example/GiePapyri_schrift_00001050"
    )
    assert not scraper.responsible(
        "https://papyri.uni-leipzig.de.example/receive/GiePapyri_schrift_00001050"
    )
    assert not scraper.responsible(
        "https://example.com/rsc/viewer/example_derivate_00000001/a.jpg"
    )


class FakePapyrusPortalResponse:
    def __init__(self, url, *, text="", content=None, chunks=()):
        self.url = url
        self.text = text
        self.content = text.encode() if content is None else content
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


class FakePapyrusPortalSession:
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


def viewer_html(properties, *, declaration="var json"):
    configuration = json.dumps({"resources": {}, "properties": properties})
    return f"<script>{declaration} = {configuration};</script>"


def test_papyrus_portal_scraper_downloads_mets_master_images(tmp_path, monkeypatch):
    viewer_url = (
        "https://www.papyrusportal.de/rsc/viewer/Test_derivate_00000001/start.jpg"
    )
    derivate_url = (
        "https://www.papyrusportal.de/servlets/MCRFileNodeServlet/"
        "Test_derivate_00000001/"
    )
    mets_url = (
        "https://www.papyrusportal.de/servlets/MCRMETSServlet/Test_derivate_00000001"
    )
    first_image_url = derivate_url + "nested/first%20image.jpg"
    second_image_url = derivate_url + "second.jpg"
    mets = b"""<?xml version="1.0"?>
        <mets:mets xmlns:mets="http://www.loc.gov/METS/"
                   xmlns:xlink="http://www.w3.org/1999/xlink">
          <mets:fileSec>
            <mets:fileGrp USE="IVIEW2">
              <mets:file ID="preview" MIMETYPE="image/jpeg">
                <mets:FLocat xlink:href="preview.jpg" />
              </mets:file>
            </mets:fileGrp>
            <mets:fileGrp USE="MASTER">
              <mets:file ID="first" MIMETYPE="image/jpeg">
                <mets:FLocat xlink:href="nested/first%20image.jpg" />
              </mets:file>
              <mets:file ID="metadata" MIMETYPE="application/xml">
                <mets:FLocat xlink:href="metadata.xml" />
              </mets:file>
              <mets:file ID="second" MIMETYPE="image/jpeg">
                <mets:FLocat xlink:href="second.jpg" />
              </mets:file>
            </mets:fileGrp>
          </mets:fileSec>
          <mets:structMap TYPE="PHYSICAL">
            <mets:div>
              <mets:div><mets:fptr FILEID="second" /></mets:div>
              <mets:div><mets:fptr FILEID="first" /></mets:div>
            </mets:div>
          </mets:structMap>
        </mets:mets>
    """
    responses = {
        viewer_url: FakePapyrusPortalResponse(
            viewer_url,
            text=viewer_html(
                {
                    "derivate": "Test_derivate_00000001",
                    "derivateURL": derivate_url,
                    "metsURL": mets_url,
                    "filePath": "/start.jpg",
                }
            ),
        ),
        mets_url: FakePapyrusPortalResponse(mets_url, content=mets),
        second_image_url: FakePapyrusPortalResponse(
            second_image_url, chunks=(b"second ", b"image")
        ),
        first_image_url: FakePapyrusPortalResponse(
            first_image_url, chunks=(b"first image",)
        ),
    }
    session = FakePapyrusPortalSession(responses)
    monkeypatch.setattr("scrapyrus.images.requests.Session", lambda: session)

    PapyrusPortalScraper(viewer_url).download(tmp_path)

    assert (tmp_path / "second.jpg").read_bytes() == b"second image"
    assert (tmp_path / "first image.jpg").read_bytes() == b"first image"
    assert not (tmp_path / "preview.jpg").exists()
    assert session.requests == [
        (viewer_url, {"timeout": 30}),
        (mets_url, {"timeout": 30}),
        (second_image_url, {"timeout": 30, "stream": True}),
        (first_image_url, {"timeout": 30, "stream": True}),
    ]


def test_papyrus_portal_scraper_follows_record_links_and_uses_start_file_fallback(
    tmp_path, monkeypatch
):
    legacy_url = "https://papyri.uni-leipzig.de/receive/GiePapyri_schrift_00000830"
    record_url = "https://www.papyrusportal.de/receive/GiePapyri_schrift_00000830"
    recto_viewer = (
        "https://www.papyrusportal.de/rsc/viewer/GiePapyri_derivate_00000830/recto.jpg"
    )
    verso_viewer = (
        "https://www.papyrusportal.de/rsc/viewer/GiePapyri_derivate_00000834/verso.jpg"
    )
    recto_base = (
        "https://www.papyrusportal.de/servlets/MCRFileNodeServlet/"
        "GiePapyri_derivate_00000830/"
    )
    verso_base = (
        "https://www.papyrusportal.de/servlets/MCRFileNodeServlet/"
        "GiePapyri_derivate_00000834/"
    )
    record_html = f"""
        <a href="{recto_viewer}">recto</a>
        <a href="{recto_viewer}">duplicate recto</a>
        <a href="{verso_viewer}">verso</a>
        <a href="https://example.com/rsc/viewer/Other_derivate_1/image.jpg">
          unrelated viewer
        </a>
    """
    responses = {
        legacy_url: FakePapyrusPortalResponse(record_url, text=record_html),
        recto_viewer: FakePapyrusPortalResponse(
            recto_viewer,
            text=viewer_html(
                {
                    "derivate": "GiePapyri_derivate_00000830",
                    "derivateURL": recto_base,
                    "filePath": "/recto.jpg",
                }
            ),
        ),
        verso_viewer: FakePapyrusPortalResponse(
            verso_viewer,
            text=viewer_html(
                {
                    "derivate": "GiePapyri_derivate_00000834",
                    "derivateURL": verso_base,
                    "filePath": "GiePapyri_derivate_00000834/verso.jpg",
                },
                declaration="let configuration",
            ),
        ),
        recto_base + "recto.jpg": FakePapyrusPortalResponse(
            recto_base + "recto.jpg", chunks=(b"recto",)
        ),
        verso_base + "verso.jpg": FakePapyrusPortalResponse(
            verso_base + "verso.jpg", chunks=(b"verso",)
        ),
    }
    session = FakePapyrusPortalSession(responses)
    monkeypatch.setattr("scrapyrus.images.requests.Session", lambda: session)

    PapyrusPortalScraper(legacy_url).download(tmp_path)

    assert (tmp_path / "recto.jpg").read_bytes() == b"recto"
    assert (tmp_path / "verso.jpg").read_bytes() == b"verso"
    assert [request[0] for request in session.requests] == [
        legacy_url,
        recto_viewer,
        recto_base + "recto.jpg",
        verso_viewer,
        verso_base + "verso.jpg",
    ]


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
    monkeypatch.setattr("scrapyrus.images.requests.Session", lambda: session)

    class ExampleIIIFScraper(IIIFImageScraper, register=False):
        def responsible(self, url: str) -> bool:
            return True

        def manifest_urls(self, session):
            return [manifest_url]

    ExampleIIIFScraper(source_url).download(tmp_path)

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


def test_onb_scraper_responsibility():
    scraper = OesterreichischeNationalbibliothekScraper(
        "http://data.onb.ac.at/rec/RZ00071734"
    )

    assert scraper.responsible("http://data.onb.ac.at/rec/RZ00071734")
    assert scraper.responsible("https://data.onb.ac.at/rep/131A98B7")
    assert scraper.responsible("https://onb.digital/result/131A98B7")
    assert scraper.responsible("https://viewer.onb.ac.at/131A98B7")
    assert scraper.responsible(
        "https://search.onb.ac.at/primo-explore/fulldisplay?docid=record"
    )
    assert scraper.responsible(
        "https://api.onb.ac.at/iiif/presentation/v3/manifest/131A98B7"
    )
    assert not scraper.responsible("https://data.onb.ac.at/unrelated/RZ00071734")
    assert not scraper.responsible("https://data.onb.ac.at.example/rec/RZ00071734")


def test_onb_scraper_follows_equivalent_page_links_with_beautiful_soup():
    record_url = "http://data.onb.ac.at/rec/RZ00071734"
    primo_url = "https://search.onb.ac.at/primo-explore/fulldisplay?docid=record"
    representation_url = "http://data.onb.ac.at/rep/131A98B7"
    result_url = "https://onb.digital/result/131A98B7"
    digitalisat_url = "https://digital.onb.ac.at/rep/access/open/131A98B7"
    manifest_url = "https://api.onb.ac.at/iiif/presentation/v3/manifest/131A98B7"
    responses = {
        record_url: FakeIIIFResponse(
            primo_url,
            text=f"""
                <a href="https://example.com/not-it">Volldigitalisat preview</a>
                <a href="{representation_url}"><span>Volldigitalisat</span></a>
            """,
        ),
        representation_url: FakeIIIFResponse(
            result_url,
            text=f"""
                <a id="Digitalisat" href="{digitalisat_url}">
                    Zum Digitalisat
                </a>
            """,
        ),
    }
    session = FakeIIIFSession(responses)

    assert OesterreichischeNationalbibliothekScraper(record_url).manifest_urls(
        session
    ) == [manifest_url]
    assert session.requests == [
        (record_url, {"timeout": 30}),
        (representation_url, {"timeout": 30}),
    ]


def test_onb_scraper_uses_primo_api_when_record_html_is_javascript_shell():
    record_url = "http://data.onb.ac.at/rec/RZ00071734"
    primo_url = (
        "https://search.onb.ac.at/primo-explore/fulldisplay"
        "?docid=ONB_alma21473259130003338&context=L&vid=ONB&lang=de_DE"
        "&search_scope=ONB_gesamtbestand&adaptor=Local%20Search%20Engine"
    )
    guest_url = (
        "https://search.onb.ac.at/primo_library/libweb/webservices/rest/v1/guestJwt/ONB"
    )
    pnx_url = (
        "https://search.onb.ac.at/primo_library/libweb/webservices/rest/"
        "primo-explore/v1/pnxs/L/ONB_alma21473259130003338"
    )
    representation_url = "http://data.onb.ac.at/rep/131A98B7"
    result_url = "https://onb.digital/result/131A98B7"
    digitalisat_url = "https://digital.onb.ac.at/rep/access/open/131A98B7"
    manifest_url = "https://api.onb.ac.at/iiif/presentation/v3/manifest/131A98B7"
    responses = {
        record_url: FakeIIIFResponse(primo_url, text="<primo-explore></primo-explore>"),
        guest_url: FakeIIIFResponse(guest_url, json_data="guest-token"),
        pnx_url: FakeIIIFResponse(
            pnx_url,
            json_data={
                "delivery": {
                    "link": [
                        {
                            "displayLabel": "Volldigitalisat",
                            "linkURL": representation_url,
                        }
                    ]
                }
            },
        ),
        representation_url: FakeIIIFResponse(
            result_url,
            text=f'<a id="Digitalisat" href="{digitalisat_url}">link</a>',
        ),
    }
    session = FakeIIIFSession(responses)

    assert OesterreichischeNationalbibliothekScraper(record_url).manifest_urls(
        session
    ) == [manifest_url]
    assert session.requests == [
        (record_url, {"timeout": 30}),
        (
            guest_url,
            {
                "params": {
                    "isGuest": "true",
                    "lang": "de_DE",
                    "targetUrl": (
                        "https%3A%2F%2Fsearch.onb.ac.at%2Fprimo-explore%2F"
                        "fulldisplay%3Fdocid%3DONB_alma21473259130003338%26"
                        "context%3DL%26vid%3DONB%26lang%3Dde_DE%26search_scope%"
                        "3DONB_gesamtbestand%26adaptor%3DLocal%2520Search%2520Engine"
                    ),
                    "viewId": "ONB",
                },
                "timeout": 30,
            },
        ),
        (
            pnx_url,
            {
                "params": {
                    "vid": "ONB",
                    "lang": "de_DE",
                    "search_scope": "ONB_gesamtbestand",
                    "adaptor": "Local Search Engine",
                },
                "headers": {"Authorization": "Bearer guest-token"},
                "timeout": 30,
            },
        ),
        (representation_url, {"timeout": 30}),
    ]


def test_scrape_images_uses_responsibility_chain_and_writes_todo(tmp_path, monkeypatch):
    metadata_without_image = tmp_path / "1.xml"
    write_metadata(metadata_without_image, [])
    known_metadata = tmp_path / "2.xml"
    write_metadata(known_metadata, ["https://known.example/recto"])
    unknown_metadata = tmp_path / "3.xml"
    write_metadata(unknown_metadata, ["https://unknown.example/verso"])

    triples = [
        ("1", metadata_without_image, None, None),
        ("2", known_metadata, None, None),
        ("3", unknown_metadata, None, None),
    ]
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples", lambda idp_data: iter(triples)
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    checked_urls = []

    class KnownScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            checked_urls.append(url)
            return url.startswith("https://known.example/")

        def download(self, target: Path) -> None:
            (target / "image").write_text(self.url, encoding="utf-8")

    output = tmp_path / "images"
    monkeypatch.chdir(tmp_path)
    todo = Path("todo.txt")
    error = Path("error.txt")
    scrape_images(output, todo, error, idp_data=tmp_path / "idp.data")

    assert (output / "2" / "image").read_text(encoding="utf-8") == (
        "https://known.example/recto"
    )
    assert not (output / "1").exists()
    assert not (output / "3").exists()
    assert checked_urls == [
        "https://known.example/recto",
        "https://unknown.example/verso",
    ]
    assert todo.read_text(encoding="utf-8") == "3: https://unknown.example/verso\n"
    assert error.read_text(encoding="utf-8") == ""
    assert not (output / "todo.txt").exists()


def test_scrape_images_passes_papyrus_directory_for_multiple_images(
    tmp_path, monkeypatch
):
    metadata = tmp_path / "42.xml"
    write_metadata(
        metadata,
        ["https://images.example/recto", "https://images.example/verso"],
    )
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    downloaded = []

    class Scraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, target: Path) -> None:
            downloaded.append((self.url, target))
            filename = self.url.rpartition("/")[2]
            (target / filename).write_text(self.url, encoding="utf-8")

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert downloaded == [
        ("https://images.example/recto", output / "42"),
        ("https://images.example/verso", output / "42"),
    ]
    assert (output / "42" / "recto").read_text(encoding="utf-8") == (
        "https://images.example/recto"
    )
    assert (output / "42" / "verso").read_text(encoding="utf-8") == (
        "https://images.example/verso"
    )
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_skips_existing_papyrus_directory(tmp_path, monkeypatch):
    metadata = tmp_path / "42.xml"
    write_metadata(metadata, ["https://images.example/recto"])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    downloads = []

    class Scraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, target: Path) -> None:
            downloads.append(target)

    output = tmp_path / "images"
    (output / "42").mkdir(parents=True)
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert downloads == []
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == ""


def test_scrape_images_writes_download_failures_to_error_file(tmp_path, monkeypatch):
    metadata = tmp_path / "42.xml"
    url = "https://images.example/recto"
    write_metadata(metadata, [url])
    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter([("42", metadata, None, None)]),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class FailingScraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return True

        def download(self, target: Path) -> None:
            raise RuntimeError("download failed")

    output = tmp_path / "images"
    todo = tmp_path / "todo.txt"
    error = tmp_path / "error.txt"

    scrape_images(output, todo, error)

    assert not (output / "42").exists()
    assert todo.read_text(encoding="utf-8") == ""
    assert error.read_text(encoding="utf-8") == f"42: {url}\n"


def test_scrape_images_prints_outcome_counts(tmp_path, monkeypatch, capsys):
    metadata_paths = []
    for hgv_id, urls in (
        ("existing", ["https://images.example/recto", "https://images.example/verso"]),
        ("scraped", ["https://images.example/success"]),
        ("unsupported", ["https://unsupported.example/image"]),
        ("failed", ["https://images.example/failure"]),
    ):
        metadata = tmp_path / f"{hgv_id}.xml"
        write_metadata(metadata, urls)
        metadata_paths.append((hgv_id, metadata, None, None))

    monkeypatch.setattr(
        "scrapyrus.images.iterate_hgv_triples",
        lambda idp_data: iter(metadata_paths),
    )
    monkeypatch.setattr(ImageScraperBase, "_scrapers", [])

    class Scraper(ImageScraperBase):
        def responsible(self, url: str) -> bool:
            return url.startswith("https://images.example/")

        def download(self, target: Path) -> None:
            if self.url.endswith("/failure"):
                raise RuntimeError("download failed")

    output = tmp_path / "images"
    (output / "existing").mkdir(parents=True)

    scrape_images(output, tmp_path / "todo.txt", tmp_path / "error.txt")

    assert capsys.readouterr().out == (
        "Images scraped: 1; skipped because they exist: 2; "
        "skipped because no scraper was available: 1; errors: 1\n"
    )
