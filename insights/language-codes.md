# Transcription language codes

## Scope and method

- Corpus: `idp.data` at Git revision `aa6879beb41816295326981345faff388db884e3`.
- Generated on 2026-07-14 using the installed `scrapyrus` package from this worktree.
- Iteration used `iterate_idpdata_triples(idp.data, progressbar=False)`.
- For each yielded record with a transcription path, the language was read using the same rule as `transcription_language`: use `xml:lang` on the first edition `<div>`, then fall back to `xml:lang` on the document root.
- Counts are shown both per yielded record and per unique transcription path. A path can occur more than once because multiple metadata records can link to the same transcription.

## Corpus coverage

| Item | Count | Share of all records |
|---|---:|---:|
| Records yielded by `iterate_idpdata_triples` | 81,484 | 100.00% |
| Records with a transcription path | 63,588 | 78.04% |
| Records without a transcription path | 17,896 | 21.96% |
| Unique transcription paths | 62,416 | 76.60% |
| Unique paths linked by more than one record | 514 | 0.63% |

All 63,588 transcription-bearing records have a non-empty language tag directly on the edition `<div>`. No transcription needed the document-root fallback, and no language value was missing.

## Language-code distribution

| Language tag | Meaning | Yielded records | Record share | Unique files | File share |
|---|---|---:|---:|---:|---:|
| `grc` | Ancient Greek | 60,703 | 95.4630% | 59,535 | 95.3842% |
| `cop` | Coptic | 2,034 | 3.1987% | 2,033 | 3.2572% |
| `la` | Latin | 840 | 1.3210% | 837 | 1.3410% |
| `ar` | Arabic | 6 | 0.0094% | 6 | 0.0096% |
| `egy-Egyd` | Ancient Egyptian, Demotic script | 3 | 0.0047% | 3 | 0.0048% |
| `grc-Latn` | Ancient Greek, Latin script | 2 | 0.0031% | 2 | 0.0032% |
| **Total** |  | **63,588** | **100.0000%** | **62,416** | **100.0000%** |

The corpus contains six distinct tags but five primary language subtags: `grc` and `grc-Latn` both identify Ancient Greek, with `Latn` specifying Latin script. Similarly, `Egyd` is a script subtag qualifying `egy`; it denotes Demotic rather than a separate language.

The values mix two-letter primary language subtags (`la`, `ar`) and three-letter subtags (`grc`, `cop`, `egy`). Consumers should therefore store the complete tag as text and should not assume a fixed length or reduce script-qualified tags to their primary language unless that loss of detail is intentional.

## Rare-tag examples

| Tag | Example transcription paths |
|---|---|
| `ar` | `DDB_EpiDoc_XML/pylon/pylon.7/pylon.7.3.xml`; `DDB_EpiDoc_XML/pylon/pylon.7/pylon.7.9_1.xml`; `DDB_EpiDoc_XML/pylon/pylon.7/pylon.7.9_2.xml` |
| `egy-Egyd` | `DDB_EpiDoc_XML/o.dime/o.dime.1/o.dime.1.86.xml`; `DDB_EpiDoc_XML/sb/sb.18/sb.18.13574.xml`; `DCLP/82/81635.xml` |
| `grc-Latn` | `DDB_EpiDoc_XML/crai/crai.2013/crai.2013.426.xml`; `DDB_EpiDoc_XML/p.worp/p.worp.11.xml` |

## Practical summary

Ancient Greek overwhelmingly dominates the corpus: `grc` alone accounts for about 95.4% of transcription files. Coptic contributes about 3.3% and Latin about 1.3%; Arabic, Demotic Egyptian, and Latin-script Ancient Greek together account for only 11 files. Language metadata is complete for every linked transcription in this revision, but downstream validation should accept BCP 47-style language tags rather than only bare ISO language codes.
