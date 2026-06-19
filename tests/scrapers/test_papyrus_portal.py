import json

from scrapyrus.scrapers.papyrus_portal import PapyrusPortalScraper


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
    monkeypatch.setattr(
        "scrapyrus.scrapers.papyrus_portal.requests.Session", lambda: session
    )

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
    monkeypatch.setattr(
        "scrapyrus.scrapers.papyrus_portal.requests.Session", lambda: session
    )

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
