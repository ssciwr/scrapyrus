# Check the latest upstream idp.data checkout against Scrapyrus's supported layout.

import argparse
from collections import Counter
from pathlib import Path
import subprocess

from scrapyrus.idpdata import iterate_idpdata_triples


def _revision(idp_data: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=idp_data,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check_compatibility(idp_data: Path) -> Counter[str]:
    """Exercise the complete upstream corpus and return association counts."""

    counts: Counter[str] = Counter()
    for _, metadata, transcription, translations in iterate_idpdata_triples(
        idp_data,
        progressbar=False,
    ):
        if not metadata.is_file():
            raise FileNotFoundError(f"Missing yielded metadata file: {metadata}")
        counts["records"] += 1
        if metadata.is_relative_to(idp_data / "HGV_meta_EpiDoc"):
            counts["hgv_records"] += 1
        elif metadata.is_relative_to(idp_data / "DCLP"):
            counts["dclp_records"] += 1
        else:
            raise ValueError(f"Unexpected metadata location: {metadata}")

        if transcription is not None:
            if not transcription.is_file():
                raise FileNotFoundError(
                    f"Missing yielded transcription file: {transcription}"
                )
            counts["transcriptions"] += 1

        for translation in translations:
            if not translation.is_file():
                raise FileNotFoundError(
                    f"Missing yielded translation file: {translation}"
                )
            counts["translations"] += 1

    required_nonzero_counts = (
        "hgv_records",
        "dclp_records",
        "transcriptions",
        "translations",
    )
    missing = [name for name in required_nonzero_counts if not counts[name]]
    if missing:
        raise ValueError("Upstream compatibility check found no " + ", ".join(missing))
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("idp_data", type=Path)
    arguments = parser.parse_args()

    idp_data = arguments.idp_data.resolve()
    revision = _revision(idp_data)
    counts = check_compatibility(idp_data)
    print(f"Compatible idp.data revision: {revision}")
    for name in (
        "records",
        "hgv_records",
        "dclp_records",
        "transcriptions",
        "translations",
    ):
        print(f"{name}: {counts[name]}")


if __name__ == "__main__":
    main()
