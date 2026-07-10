# Transcription token estimate

## Scope and method

- Corpus: `idp.data` at Git revision `38aa5ef77ad2c7f5406263ffb17907538e92b712`.
- Generated on 2026-07-10 with the installed `scrapyrus` package and `saxonche 13.0.0`.
- Iteration used `iterate_idpdata_triples(idp.data, progressbar=False)`.
- For every yielded record with a transcription path, the run extracted the edition with `transcription_xml_snippet(transcription, remove_namespaces=True)`.
- Text was produced with `epidoc_xml_to_text(snippet)` using the default settings: no abbreviation expansion, no gap line breaks, no lost text, no unclear text, and no regularization.
- Token counts are planning estimates, not model-tokenizer counts. The estimate is `ceil(len(text.encode("utf-8")) / 3)`, which is more conservative than a plain character heuristic for Greek-heavy Unicode text. For a model-specific budget, rerun with that model's tokenizer.

## Corpus coverage

| Item | Count | Share |
|---|---:|---:|
| Records yielded by `iterate_idpdata_triples` | 81,104 | 100.00% |
| HGV records | 66,261 | 81.70% |
| DCLP records | 14,843 | 18.30% |
| Records with a transcription path | 63,584 | 78.40% |
| Edition snippets extracted | 63,584 | 78.40% |
| Non-empty transformed texts | 61,745 | 76.13% |
| Empty transformed texts | 1,028 | 1.27% |
| Transformation failures | 811 | 1.00% |
| Records without a transcription path | 17,520 | 21.60% |
| Unique non-empty transcription paths | 60,738 | 74.89% |

All records with a transcription path yielded an edition snippet. The 811 failures happened during `epidoc_xml_to_text`; Saxon/C printed `ArrayIndexOutOfBoundsException` stack traces and Python raised `PySaxonApiError` at `epidoc-to-text.xsl` line 22. Those records are excluded from the length and token totals below.

## Overall token cost

The corpus has two useful cost views:

| Embedding input policy | Inputs | Characters | UTF-8 bytes | Estimated input tokens |
|---|---:|---:|---:|---:|
| One input per non-empty yielded record | 61,745 | 28,716,250 | 55,319,694 | 18,460,388 |
| One input per unique non-empty transcription path | 60,738 | 21,145,420 | 40,716,568 | 13,592,356 |
| Duplicate-record overhead | 1,007 | 7,570,830 | 14,603,126 | 4,868,032 |

If the embedding provider charges `P` per 1 million input tokens, then the estimated input-only cost is:

- Record-level embedding: `18.46 * P`.
- Unique-path embedding: `13.59 * P`.

For example, if `P = $0.02`, the input-only cost would be about `$0.37` at record level or `$0.27` after de-duplicating by transcription path. Use current provider pricing and the target tokenizer before making a budget commitment.

The duplicate overhead is large relative to the duplicate count because several repeated HGV links point to long documents. De-duplicating by transcription path saves an estimated 4.87 million input tokens, about 26.4% of the record-level token total.

## Length distribution

Record-level distribution, using every non-empty yielded record:

| Metric | Min | P10 | P25 | Median | P75 | P90 | P95 | P99 | Max | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Estimated tokens | 1 | 16 | 40 | 91 | 237 | 511 | 805 | 2,813 | 125,878 | 299 |
| Characters | 1 | 26 | 63 | 143 | 369 | 792 | 1,251 | 4,379 | 202,367 | 465 |
| UTF-8 bytes | 1 | 48 | 119 | 272 | 711 | 1,531 | 2,414 | 8,438 | 377,633 | 896 |
| Lines | 1 | 3 | 4 | 8 | 17 | 31 | 44 | 194 | 7,157 | 19 |
| Whitespace words | 1 | 5 | 13 | 28 | 68 | 142 | 220 | 838 | 41,292 | 84 |

Unique-path distribution:

| Metric | Min | P10 | P25 | Median | P75 | P90 | P95 | P99 | Max | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Estimated tokens | 1 | 16 | 39 | 89 | 228 | 481 | 735 | 1,823 | 125,878 | 224 |
| Characters | 1 | 25 | 62 | 140 | 355 | 749 | 1,138 | 2,781 | 202,367 | 348 |
| UTF-8 bytes | 1 | 47 | 117 | 267 | 684 | 1,443 | 2,204 | 5,468 | 377,633 | 670 |
| Lines | 1 | 3 | 4 | 8 | 17 | 29 | 41 | 108 | 7,157 | 16 |
| Whitespace words | 1 | 5 | 13 | 27 | 65 | 134 | 200 | 498 | 41,292 | 64 |

Most transcription inputs are short. At record level, 59.8% are estimated at 128 tokens or less, 89.6% at 512 tokens or less, and 96.6% at 1,024 tokens or less. The long tail matters for batching and model context limits: 447 record-level inputs exceed 4,096 estimated tokens, 242 exceed 8,192, and 137 exceed 16,384.

| Estimated token bucket | Record-level inputs | Share |
|---|---:|---:|
| 1-128 | 36,923 | 59.80% |
| 129-256 | 10,472 | 16.96% |
| 257-512 | 8,212 | 13.30% |
| 513-1,024 | 4,062 | 6.58% |
| 1,025-2,048 | 1,224 | 1.98% |
| 2,049-4,096 | 405 | 0.66% |
| 4,097-8,192 | 205 | 0.33% |
| 8,193-16,384 | 105 | 0.17% |
| >16,384 | 137 | 0.22% |

## HGV vs DCLP

| Source | Non-empty inputs | Characters | UTF-8 bytes | Estimated tokens | Mean tokens/input |
|---|---:|---:|---:|---:|---:|
| HGV linked DDbDP transcriptions | 59,504 | 26,425,750 | 51,028,186 | 17,029,134 | 286 |
| DCLP embedded transcriptions | 2,241 | 2,290,500 | 4,291,508 | 1,431,254 | 639 |

DCLP contributes only 3.6% of the non-empty inputs but 7.8% of the estimated tokens, because the DCLP texts are longer on average.

## Longest transformed texts

| TM ID | Source | Document | Estimated tokens | Characters |
|---|---|---|---:|---:|
| 11999 | HGV | `DDB_EpiDoc_XML/p.mich/p.mich.4.1/p.mich.4.1.224.xml` | 125,878 | 202,367 |
| 62477 | DCLP | `DCLP/63/62477.xml` | 46,826 | 74,031 |
| 62400 | DCLP | `DCLP/63/62400.xml` | 33,977 | 53,933 |
| 62580 | DCLP | `DCLP/63/62580.xml` | 33,189 | 52,409 |
| 865216 | DCLP | `DCLP/866/865216.xml` | 31,763 | 50,587 |
| 62500 | DCLP | `DCLP/63/62500.xml` | 27,686 | 43,983 |
| 8859 | HGV | `DDB_EpiDoc_XML/p.rev.2ed/p.rev.2ed.pg4.xml` | 27,088 | 42,302 |
| 44882 | HGV | `DDB_EpiDoc_XML/p.panop.beatty/p.panop.beatty.2.xml` | 26,763 | 41,344 |

Several of these exceed common embedding context limits. A production embedding job should either skip, chunk, or model-specifically validate the largest texts before submission.

## Duplicate transcription paths

Top repeated non-empty transcription paths:

| Document | Records | Estimated tokens per text |
|---|---:|---:|
| `DDB_EpiDoc_XML/p.bub/p.bub.1/p.bub.1.4.xml` | 68 | 4,553 |
| `DDB_EpiDoc_XML/rom.mil.rec/rom.mil.rec.1/rom.mil.rec.1.76.xml` | 67 | 13,417 |
| `DDB_EpiDoc_XML/p.panop.beatty/p.panop.beatty.1.xml` | 63 | 24,201 |
| `DDB_EpiDoc_XML/p.panop.beatty/p.panop.beatty.2.xml` | 54 | 26,763 |
| `DDB_EpiDoc_XML/p.bub/p.bub.2/p.bub.2.5.xml` | 41 | 5,734 |

There are 485 duplicated non-empty transcription paths. If the downstream store is keyed by document path, it is worth de-duplicating before calling the embedding endpoint, not just before insertion.

## Practical takeaways

- The de-duplicated transcription corpus is modest for embedding: roughly 60.7k inputs and 13.6 million estimated input tokens.
- A naive record-level embedding pass costs about 4.9 million extra estimated tokens because repeated HGV metadata records can point to the same DDbDP XML.
- The median text is tiny, but the long tail is real. Use chunking or a maximum-token guard for documents above the embedding model's context limit.
- Resolve the Saxon/C transformation failures before treating the corpus as complete. With the current runtime, 811 records with extracted edition snippets did not produce text.
