from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree

from tqdm import tqdm


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
) -> Iterator[tuple[str, Path, Path | None, Path | None]]:
    """Yield the files associated with every HGV metadata record.

    Each result contains the HGV ID followed by its metadata, transcription,
    and translation paths. Records without a transcription or translation
    contain ``None`` in the corresponding position. Set ``progressbar`` to
    ``False`` to disable progress reporting.
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
        tqdm(metadata_files, total=len(metadata_files), unit="record")
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
