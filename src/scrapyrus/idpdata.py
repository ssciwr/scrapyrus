from collections.abc import Iterator
from itertools import chain
from pathlib import Path

from saxonche import PySaxonProcessor
from tqdm import tqdm

from scrapyrus.saxon_xml import (
    first_string,
    parse_xml_document,
    xpath_boolean,
    xpath_literal,
)


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
TEI_NAMESPACES = {"tei": TEI_NAMESPACE}


def _identifier_text(metadata: Path, identifier_type: str) -> str | None:
    """Return a metadata ``idno`` value by type."""

    with PySaxonProcessor(license=False) as proc:
        document = parse_xml_document(proc, metadata)
        return _identifier_text_from_document(proc, document, identifier_type)


def _identifier_text_from_document(
    proc: PySaxonProcessor,
    document,
    identifier_type: str,
) -> str | None:
    """Return a metadata ``idno`` value by type from a parsed XML document."""

    return first_string(
        proc,
        document,
        f"normalize-space((.//tei:idno[@type = {xpath_literal(identifier_type)}])[1])",
        namespaces=TEI_NAMESPACES,
    )


def _ddb_filename(metadata: Path) -> str | None:
    """Return the DDbDP filename referenced by an HGV metadata file."""

    return _identifier_text(metadata, "ddb-filename")


def _has_nonempty_edition(metadata: Path) -> bool:
    """Return whether an XML file contains a non-empty edition division."""

    with PySaxonProcessor(license=False) as proc:
        document = parse_xml_document(proc, metadata)
        return _has_nonempty_edition_document(proc, document)


def _has_nonempty_edition_document(proc: PySaxonProcessor, document) -> bool:
    """Return whether a parsed XML document contains a non-empty edition division."""

    return xpath_boolean(
        proc,
        document,
        "exists(.//*[local-name() = 'div'][@type = 'edition']"
        "[normalize-space(.) or *])",
    )


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
    with PySaxonProcessor(license=False) as proc:
        for metadata in metadata_iterator:
            document = parse_xml_document(proc, metadata)
            tm_id = _identifier_text_from_document(proc, document, "TM")
            if tm_id is None:
                raise ValueError(f"{metadata} does not contain an idno with type='TM'")
            hgv_id = metadata.stem
            ddb_filename = _identifier_text_from_document(
                proc,
                document,
                "ddb-filename",
            )
            transcription = transcriptions.get(ddb_filename)
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
    with PySaxonProcessor(license=False) as proc:
        for metadata in dclp_iterator:
            document = parse_xml_document(proc, metadata)
            tm_id = _identifier_text_from_document(proc, document, "TM")
            if tm_id is None:
                raise ValueError(f"{metadata} does not contain an idno with type='TM'")
            transcription = (
                metadata if _has_nonempty_edition_document(proc, document) else None
            )
            yield (tm_id, metadata, transcription, None)


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
