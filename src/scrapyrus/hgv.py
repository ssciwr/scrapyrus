from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree

from tqdm import tqdm


def transcription_xml_snippet(
    transcription: Path,
    *,
    remove_namespaces: bool = True,
) -> str | None:
    """Return the edition division from a transcription XML file.

    The first ``div`` element with a ``type`` attribute of ``edition`` is
    returned as a serialized XML string. If the file has no such element,
    return ``None``. By default, namespace qualifiers are removed from TEI
    element tags in the returned snippet.
    """

    for element in ElementTree.parse(transcription).iter():
        local_name = element.tag.rpartition("}")[2]
        if local_name == "div" and element.get("type") == "edition":
            element.tail = None
            if remove_namespaces:
                for descendant in element.iter():
                    descendant.tag = descendant.tag.rpartition("}")[2]
            return ElementTree.tostring(element, encoding="unicode")
    return None


def _ddb_filename(metadata: Path) -> str | None:
    """Return the DDbDP filename referenced by an HGV metadata file."""

    for identifier in ElementTree.parse(metadata).iter(
        "{http://www.tei-c.org/ns/1.0}idno"
    ):
        if identifier.get("type") == "ddb-filename":
            return identifier.text
    return None


def iterate_hgv_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating HGV",
) -> Iterator[tuple[str, Path, Path | None, Path | None]]:
    """Yield the files associated with every HGV metadata record.

    Each result contains the HGV ID followed by its metadata, transcription,
    and translation paths. Records without a transcription or translation
    contain ``None`` in the corresponding position. Set ``progressbar`` to
    ``False`` to disable progress reporting. Use ``progressbar_title`` to
    customize the progress bar description.
    """

    idp_data = Path(idp_data)
    metadata_root = idp_data / "HGV_meta_EpiDoc"
    transcription_root = idp_data / "DDB_EpiDoc_XML"
    translation_root = idp_data / "HGV_trans_EpiDoc"

    # DDbDP's directory structure cannot be derived reliably from its filename
    # (series names may themselves contain dots), while leaf names are unique.
    transcriptions = {
        transcription.stem: transcription
        for transcription in transcription_root.rglob("*.xml")
    }

    metadata_files = sorted(metadata_root.glob("HGV*/*.xml"))
    metadata_iterator = (
        tqdm(
            metadata_files,
            total=len(metadata_files),
            unit="record",
            desc=progressbar_title,
        )
        if progressbar
        else metadata_files
    )
    for metadata in metadata_iterator:
        hgv_id = metadata.stem
        transcription = transcriptions.get(_ddb_filename(metadata))
        translation = translation_root / f"{hgv_id}.xml"

        yield (
            hgv_id,
            metadata,
            transcription,
            translation if translation.is_file() else None,
        )
