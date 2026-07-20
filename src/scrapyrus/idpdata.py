from collections import defaultdict
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
IdpTriple = tuple[str, Path, Path | None, tuple[Path, ...]]


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


def _has_nonempty_edition_document(proc: PySaxonProcessor, document) -> bool:
    """Return whether a parsed XML document contains a non-empty edition division."""

    return xpath_boolean(
        proc,
        document,
        "exists(.//*[local-name() = 'div'][@type = 'edition']"
        "[normalize-space(string-join(.//text()"
        "[not(ancestor::*[local-name() = 'note'])], '')) "
        "or .//*[not(local-name() = ('div', 'ab', 'p', 'note', 'head'))]])",
    )


def _require_directories(idp_data: Path, directory_names: tuple[str, ...]) -> None:
    """Raise a descriptive error when the current idp.data layout is absent."""

    missing = [name for name in directory_names if not (idp_data / name).is_dir()]
    if missing:
        names = ", ".join(missing)
        raise FileNotFoundError(
            f"{idp_data} does not use the supported idp.data layout; "
            f"missing directories: {names}"
        )


def _partition_name(identifier: str) -> str:
    """Return the idp.data partition containing an identifier."""

    return identifier[:-3] or "0"


def _translation_paths_by_hgv(translation_root: Path) -> dict[str, tuple[Path, ...]]:
    """Index split translation files by the HGV filename they belong to."""

    paths_by_hgv: defaultdict[str, list[Path]] = defaultdict(list)
    for translation in translation_root.rglob("*.xml"):
        hgv_id, separator, sequence = translation.stem.rpartition("-")
        if separator and hgv_id and sequence.isdecimal():
            paths_by_hgv[hgv_id].append(translation)
    return {hgv_id: tuple(sorted(paths)) for hgv_id, paths in paths_by_hgv.items()}


def iterate_hgv_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating HGV",
) -> Iterator[IdpTriple]:
    """Yield the files associated with every HGV metadata record.

    Each result contains the Trismegistos ID followed by its HGV metadata,
    transcription, and translation paths. Records without a transcription
    contain ``None`` in the transcription position. The final position is a
    tuple because the current idp.data layout stores each translation in a
    separate file; records without translations contain an empty tuple. Set
    ``progressbar`` to ``False`` to disable progress reporting. Use
    ``progressbar_title`` to customize the progress bar description.
    """

    idp_data = Path(idp_data)
    _require_directories(
        idp_data,
        ("HGV_meta_EpiDoc", "DDbDP", "Translations"),
    )
    metadata_root = idp_data / "HGV_meta_EpiDoc"
    transcription_root = idp_data / "DDbDP"
    translations_by_hgv = _translation_paths_by_hgv(idp_data / "Translations")

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
    transcription_has_edition: dict[Path, bool] = {}
    with PySaxonProcessor(license=False) as proc:
        for metadata in metadata_iterator:
            document = parse_xml_document(proc, metadata)
            tm_id = _identifier_text_from_document(proc, document, "TM")
            if tm_id is None:
                raise ValueError(f"{metadata} does not contain an idno with type='TM'")
            hgv_id = metadata.stem
            transcription_path = (
                transcription_root / _partition_name(tm_id) / f"{tm_id}.xml"
            )
            transcription = None
            if transcription_path.is_file():
                has_edition = transcription_has_edition.get(transcription_path)
                if has_edition is None:
                    transcription_document = parse_xml_document(
                        proc,
                        transcription_path,
                    )
                    has_edition = _has_nonempty_edition_document(
                        proc,
                        transcription_document,
                    )
                    transcription_has_edition[transcription_path] = has_edition
                if has_edition:
                    transcription = transcription_path

            yield (
                tm_id,
                metadata,
                transcription,
                translations_by_hgv.get(hgv_id, ()),
            )


def iterate_dclp_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating DCLP",
) -> Iterator[IdpTriple]:
    """Yield the files associated with every DCLP metadata record.

    Each result contains the Trismegistos ID followed by its DCLP metadata,
    transcription, and translation paths. DCLP metadata and transcriptions are
    stored in the same XML file, so records with a non-empty edition division
    repeat the same path in the metadata and transcription positions. Records
    without a transcription contain ``None`` in the transcription position.
    DCLP translations are not represented as separate files and the final
    position is therefore an empty tuple.
    """

    idp_data = Path(idp_data)
    _require_directories(idp_data, ("DCLP",))
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
            yield (tm_id, metadata, transcription, ())


def iterate_idpdata_triples(
    idp_data: str | Path,
    *,
    progressbar: bool = True,
    progressbar_title: str = "Iterating idp.data",
) -> Iterator[IdpTriple]:
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
