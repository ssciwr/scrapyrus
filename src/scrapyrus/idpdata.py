from collections.abc import Iterator
from itertools import chain
from pathlib import Path
from xml.etree import ElementTree

from tqdm import tqdm


TEI_IDNO = "{http://www.tei-c.org/ns/1.0}idno"


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


def _identifier_text(metadata: Path, identifier_type: str) -> str | None:
    """Return a metadata ``idno`` value by type."""

    for identifier in ElementTree.parse(metadata).iter(TEI_IDNO):
        if identifier.get("type") == identifier_type and identifier.text:
            return identifier.text.strip()
    return None


def _ddb_filename(metadata: Path) -> str | None:
    """Return the DDbDP filename referenced by an HGV metadata file."""

    return _identifier_text(metadata, "ddb-filename")


def _has_nonempty_edition(metadata: Path) -> bool:
    """Return whether an XML file contains a non-empty edition division."""

    for element in ElementTree.parse(metadata).iter():
        local_name = element.tag.rpartition("}")[2]
        if (
            local_name == "div"
            and element.get("type") == "edition"
            and ((element.text and element.text.strip()) or len(element))
        ):
            return True
    return False


def trismegistos_id(metadata: Path) -> str:
    """Return the Trismegistos identifier declared by an HGV metadata file."""

    tm_id = _identifier_text(metadata, "TM")
    if tm_id is None:
        raise ValueError(f"{metadata} does not contain an idno with type='TM'")
    return tm_id


def iterate_hgv_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating HGV",
) -> Iterator[tuple[str, Path, Path | None, Path | None]]:
    """Yield the files associated with every HGV metadata record.

    Each result contains the Trismegistos ID followed by its HGV metadata,
    transcription, and translation paths. Records without a transcription or
    translation contain ``None`` in the corresponding position. Set
    ``progressbar`` to ``False`` to disable progress reporting. Use
    ``progressbar_title`` to customize the progress bar description.
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
        tm_id = trismegistos_id(metadata)
        hgv_id = metadata.stem
        transcription = transcriptions.get(_ddb_filename(metadata))
        translation = translation_root / f"{hgv_id}.xml"

        yield (
            tm_id,
            metadata,
            transcription,
            translation if translation.is_file() else None,
        )


def iterate_dclp_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating DCLP",
) -> Iterator[tuple[str, Path, Path | None, Path | None]]:
    """Yield the files associated with every DCLP metadata record.

    Each result contains the Trismegistos ID followed by its DCLP metadata,
    transcription, and translation paths. DCLP metadata and transcriptions are
    stored in the same XML file, so records with a non-empty edition division
    repeat the same path in the metadata and transcription positions. Records
    without a transcription contain ``None`` in the transcription position.
    DCLP translations are not represented as separate files and are yielded as
    ``None``.
    """

    idp_data = Path(idp_data)
    dclp_files = sorted((idp_data / "DCLP").rglob("*.xml"))
    dclp_iterator = (
        tqdm(
            dclp_files,
            total=len(dclp_files),
            unit="record",
            desc=progressbar_title,
        )
        if progressbar
        else dclp_files
    )
    for metadata in dclp_iterator:
        transcription = metadata if _has_nonempty_edition(metadata) else None
        yield (trismegistos_id(metadata), metadata, transcription, None)


def iterate_idpdata_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating idp.data",
) -> Iterator[tuple[str, Path, Path | None, Path | None]]:
    """Yield HGV triples followed by DCLP triples.

    Set ``progressbar`` to ``False`` to disable progress reporting. When
    progress reporting is enabled, a single progress bar covers the full sweep
    across both data sets.
    """

    idp_data = Path(idp_data)
    triples = chain(
        iterate_hgv_triples(idp_data, progressbar=False),
        iterate_dclp_triples(idp_data, progressbar=False),
    )
    if not progressbar:
        yield from triples
        return

    hgv_count = len(list((idp_data / "HGV_meta_EpiDoc").glob("HGV*/*.xml")))
    dclp_count = len(list((idp_data / "DCLP").rglob("*.xml")))
    yield from tqdm(
        triples,
        total=hgv_count + dclp_count,
        unit="record",
        desc=progressbar_title,
    )
