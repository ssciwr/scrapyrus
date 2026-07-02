# Used to extract namespace-free TEI edition `<div>` snippets from every
# transcription linked by HGV metadata in `idp.data`, writing one XML file per
# TM ID to `transcriptions/`.

from pathlib import Path

from scrapyrus.idpdata import iterate_hgv_triples, transcription_xml_snippet


idp_data = Path("idp.data")
output_directory = Path("transcriptions")
output_directory.mkdir(exist_ok=True)

for tm_id, _, transcription, _ in iterate_hgv_triples(idp_data):
    if transcription is None:
        continue

    snippet = transcription_xml_snippet(transcription, remove_namespaces=True)
    if snippet is not None:
        (output_directory / f"{tm_id}.xml").write_text(snippet, encoding="utf-8")
