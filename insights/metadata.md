# HGV TEI metadata inventory

This report inventories the HGV metadata XML for every record returned by `iterate_hgv_triples`. Associated transcription and translation files are counted for linkage coverage but their contents are outside this metadata profile. It is a data profile for designing a practical database schema, not a replacement for the EpiDoc/TEI schema.

## Scope and method

- Corpus: `idp.data` at Git revision `44c9c455e0e4c4c569f36c55633e421a67e1dcf0`.
- Generator: `python scripts/aggregate_hgv_metadata.py idp.data metadata.md`.
- HGV metadata XML files are counted once; associated XML paths are deduplicated for linkage counts.
- “Coverage” is the percentage of successfully parsed HGV metadata XML files.
- “Per present file” is the minimum–maximum cardinality, excluding files where the construct is absent.
- Element presence is structural; empty elements count as present. Attribute value counts are exact up to 10,000 distinct values per field and are marked as truncated beyond that limit.
- Text-value profiles are limited to selected controlled or schema-relevant fields; all element and attribute presence counts cover the complete metadata XML tree, including its body.

## Corpus linkage

| Item | Count | HGV record coverage |
|---|---:|---:|
| HGV records / metadata XML files | 66,261 | 100.00% |
| Records linked to a transcription | 61,286 | 92.49% |
| Unique linked transcription XML files | 60,115 | 90.72% |
| Records linked to a translation | 2,411 | 3.64% |
| Unique linked translation XML files | 2,411 | 3.64% |

## Database-design takeaways

- Keep the HGV record, transcription, and translation as separate entities. Their coverage differs, and the same transcription can be linked from multiple HGV records.
- Model identifiers, provenance places, keywords, bibliography entries, languages, revision events, and typed text divisions as child tables: they are repeatable and carry type/subtype or authority attributes.
- Preserve normalized core columns alongside the source XML. TEI permits mixed content, nested bibliography, open-ended attributes, and uncommon structures that a compact relational schema will otherwise lose.
- Treat dates as an interval-capable value object. The `origDate` inventory below shows exact dates, bounds, ranges, and human-readable labels in the corpus.
- Treat place labels and authority references separately. A place may have multiple space-separated `@ref` URIs and may be classified with `@type`, `@subtype`, and `@n`.
- Do not interpret `langUsage` as the language of the ancient document. Seven language declarations occur in essentially every file and describe the metadata environment; content language belongs to the linked transcription or another explicit field.
- Normalize display labels without discarding them. Material values vary by case and language, the current settlement is `unbekannt` in most populated records, and the keyword vocabulary has more than 10,000 forms.
- Use the high-coverage fields as first-class columns and the long-tail element/attribute inventory as an extension table or retained XML, rather than creating one nullable column for every TEI construct.

## HGV metadata XML

Successfully parsed: 66,261 files.

### Selected schema-relevant fields

| Candidate field | TEI path | XML files | Coverage | Occurrences | Per present file |
|---|---|---:|---:|---:|---:|
| Document title | `/TEI/teiHeader/fileDesc/titleStmt/title` | 66,261 | 100.00% | 66,261 | 1 |
| Publication identifier | `/TEI/teiHeader/fileDesc/publicationStmt/idno` | 66,261 | 100.00% | 325,903 | 3–17 |
| Holding institution | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/institution` | 1 | 0.00% | 1 | 1 |
| Collection | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/collection` | 7,840 | 11.83% | 7,840 | 1 |
| Current settlement | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/placeName/settlement` | 57,741 | 87.14% | 57,741 | 1 |
| Inventory identifier | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/idno` | 16,377 | 24.72% | 16,377 | 1 |
| Material | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc/objectDesc/supportDesc/support/material` | 66,257 | 99.99% | 66,257 | 1 |
| Origin place | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace` | 66,257 | 99.99% | 66,257 | 1 |
| Origin date | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | 66,261 | 100.00% | 69,224 | 1–5 |
| Provenance event | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance` | 55,606 | 83.92% | 55,897 | 1–3 |
| Provenance place | `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | 55,602 | 83.91% | 122,430 | 1–9 |
| Keyword | `/TEI/teiHeader/profileDesc/textClass/keywords/term` | 66,118 | 99.78% | 188,259 | 1–25 |
| Revision event | `/TEI/teiHeader/revisionDesc/change` | 66,258 | 100.00% | 201,070 | 1–14 |
| Typed body division | `/TEI/text/body/div` | 66,261 | 100.00% | 254,011 | 1–8 |
| Division paragraph | `/TEI/text/body/div/p` | 66,156 | 99.84% | 137,341 | 1–31 |
| Structured bibliography entry | `/TEI/text/body/div/listBibl/bibl` | 66,261 | 100.00% | 170,017 | 1–36 |
| Inline illustration reference | `/TEI/text/body/div/p/bibl` | 26,773 | 40.41% | 30,609 | 1–20 |
| Image link | `/TEI/text/body/div/p/figure/graphic` | 35,494 | 53.57% | 41,317 | 1–54 |
| Mentioned date | `/TEI/text/body/div/list/item/date` | 5,088 | 7.68% | 11,142 | 1–65 |

### Identifier types (`idno/@type`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `TM` | 66,261 | 100.00% | 66,261 |
| `ddb-hybrid` | 66,259 | 100.00% | 66,261 |
| `filename` | 66,261 | 100.00% | 66,261 |
| `ddb-filename` | 66,203 | 99.91% | 66,203 |
| `ddb-perseus-style` | 60,760 | 91.70% | 60,760 |
| `invNo` | 16,379 | 24.72% | 16,379 |
| `HGV-deprecated` | 50 | 0.08% | 71 |
| `TM-deprecated` | 50 | 0.08% | 71 |
| `dclp` | 7 | 0.01% | 7 |
| `APD` | 6 | 0.01% | 6 |
| `dclp-hybrid` | 2 | 0.00% | 2 |

### Language identifiers (`language/@ident`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `de` | 66,261 | 100.00% | 66,261 |
| `el` | 66,261 | 100.00% | 66,261 |
| `en` | 66,261 | 100.00% | 66,261 |
| `es` | 66,260 | 100.00% | 66,260 |
| `fr` | 66,260 | 100.00% | 66,260 |
| `it` | 66,260 | 100.00% | 66,260 |
| `la` | 66,260 | 100.00% | 66,260 |
| `ar` | 3 | 0.00% | 3 |

### Division types (`div/@type`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `bibliography` | 66,261 | 100.00% | 176,141 |
| `commentary` | 38,673 | 58.36% | 41,996 |
| `figure` | 35,577 | 53.69% | 35,578 |
| `edition` | 298 | 0.45% | 298 |

### Division subtypes (`div/@subtype`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `principalEdition` | 66,261 | 100.00% | 66,261 |
| `illustrations` | 65,069 | 98.20% | 65,077 |
| `general` | 36,436 | 54.99% | 36,439 |
| `corrections` | 27,475 | 41.46% | 27,484 |
| `otherPublications` | 12,755 | 19.25% | 12,755 |
| `mentionedDates` | 5,557 | 8.39% | 5,557 |
| `translations` | 4,540 | 6.85% | 4,543 |
| `citations` | 21 | 0.03% | 21 |

### Bibliography types (`bibl/@type`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `publication` | 66,261 | 100.00% | 82,313 |
| `BL` | 27,473 | 41.46% | 53,875 |
| `illustration` | 26,774 | 40.41% | 30,610 |
| `BL-online` | 25,417 | 38.36% | 25,419 |
| `translations` | 4,518 | 6.82% | 6,043 |
| `SB` | 1,506 | 2.27% | 1,506 |

### Bibliography subtypes (`bibl/@subtype`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `principal` | 66,261 | 100.00% | 66,261 |
| `other` | 12,729 | 19.21% | 16,052 |

### Bibliographic scope types (`biblScope/@type`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `volume` | 52,715 | 79.56% | 100,587 |
| `numbers` | 64,095 | 96.73% | 64,095 |
| `pages` | 29,147 | 43.99% | 55,780 |
| `generic` | 2,763 | 4.17% | 2,942 |
| `fascicle` | 2,595 | 3.92% | 2,595 |
| `side` | 1,538 | 2.32% | 1,538 |
| `pp` | 1,400 | 2.11% | 1,406 |
| `number` | 1,300 | 1.96% | 1,300 |
| `lines` | 910 | 1.37% | 911 |
| `columns` | 586 | 0.88% | 587 |
| `inventory` | 314 | 0.47% | 314 |
| `folio` | 45 | 0.07% | 45 |
| `null` | 26 | 0.04% | 26 |
| `fragments` | 15 | 0.02% | 15 |

### Provenance types (`provenance/@type`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `located` | 55,104 | 83.16% | 55,111 |
| `found` | 418 | 0.63% | 418 |
| `composed` | 190 | 0.29% | 190 |
| `sent` | 33 | 0.05% | 34 |
| `acquired` | 15 | 0.02% | 15 |
| `received` | 1 | 0.00% | 1 |

### Place types (`placeName/@type`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `ancient` | 55,577 | 83.88% | 122,235 |
| `modern` | 118 | 0.18% | 133 |
| `ancientFindspot` | 7 | 0.01% | 7 |
| `ancientRegion` | 2 | 0.00% | 2 |
| `nome` | 1 | 0.00% | 1 |

### Place subtypes (`placeName/@subtype`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `region` | 42,067 | 63.49% | 42,577 |
| `nome` | 31,999 | 48.29% | 32,506 |
| `province` | 343 | 0.52% | 343 |

### Keyword schemes (`keywords/@scheme`)

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `hgv` | 66,118 | 99.78% | 66,118 |

### Material values

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `Papyrus` | 39,583 | 59.74% | 39,583 |
| `Ostrakon` | 21,989 | 33.19% | 21,989 |
| `Holz` | 2,581 | 3.90% | 2,581 |
| `Stein` | 373 | 0.56% | 373 |
| `Pergament` | 356 | 0.54% | 356 |
| `Graffito` | 234 | 0.35% | 234 |
| `papyrus` | 153 | 0.23% | 153 |
| `Holz (?)` | 94 | 0.14% | 94 |
| `Leinen` | 80 | 0.12% | 80 |
| `Wachstafel` | 73 | 0.11% | 73 |
| `Ton` | 68 | 0.10% | 68 |
| `Ostracon (poterie)` | 54 | 0.08% | 54 |
| `Holztafel` | 37 | 0.06% | 37 |
| `Dipinto` | 30 | 0.05% | 30 |
| `Stein (Graffito)` | 29 | 0.04% | 29 |
| `Papier` | 23 | 0.03% | 23 |
| `Leder` | 14 | 0.02% | 14 |
| `ostrakon` | 13 | 0.02% | 13 |
| `Gips` | 11 | 0.02% | 11 |
| `Kalkstein` | 9 | 0.01% | 9 |
| `Mumienbinde` | 9 | 0.01% | 9 |
| `Mumienhülle` | 9 | 0.01% | 9 |
| `Mumienleinwand` | 9 | 0.01% | 9 |
| `Knochen` | 8 | 0.01% | 8 |
| `Tuch` | 7 | 0.01% | 7 |
| `Leder (Gazelle?)` | 6 | 0.01% | 6 |
| `Bronze` | 5 | 0.01% | 5 |
| `Klapptafel` | 4 | 0.01% | 4 |
| `Krug` | 4 | 0.01% | 4 |
| `Goldblatt` | 3 | 0.00% | 3 |
| … |  | 91 distinct values |  |

### Current settlement values

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `unbekannt` | 49,583 | 74.83% | 49,583 |
| `Qift` | 1,872 | 2.83% | 1,872 |
| `London` | 680 | 1.03% | 680 |
| `Cairo` | 647 | 0.98% | 647 |
| `New York` | 494 | 0.75% | 494 |
| `Toronto` | 374 | 0.56% | 374 |
| `Vienna` | 316 | 0.48% | 316 |
| `Oxford` | 289 | 0.44% | 289 |
| `Paris` | 205 | 0.31% | 205 |
| `New Haven` | 198 | 0.30% | 198 |
| `Ann Arbor` | 181 | 0.27% | 181 |
| `Dublin` | 175 | 0.26% | 175 |
| `Manchester` | 167 | 0.25% | 167 |
| `Berlin` | 126 | 0.19% | 126 |
| `Florence` | 118 | 0.18% | 118 |
| `Wadi Hammamat` | 105 | 0.16% | 105 |
| `Sydney` | 104 | 0.16% | 104 |
| `Cologne` | 103 | 0.16% | 103 |
| `Leiden` | 101 | 0.15% | 101 |
| `Leipzig` | 87 | 0.13% | 87 |
| `Birmingham` | 86 | 0.13% | 86 |
| `Wadi Menih` | 77 | 0.12% | 77 |
| `Egypt` | 76 | 0.11% | 76 |
| `Kellis` | 70 | 0.11% | 70 |
| `Fribourg` | 69 | 0.10% | 69 |
| `Luxor` | 66 | 0.10% | 66 |
| `Berkeley` | 58 | 0.09% | 58 |
| `Köln` | 52 | 0.08% | 52 |
| `Basel` | 50 | 0.08% | 50 |
| `El-Bawiti` | 50 | 0.08% | 50 |
| … |  | 203 distinct values |  |

### Origin place values

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `unbekannt` | 10,732 | 16.20% | 10,732 |
| `Theben` | 5,246 | 7.92% | 5,246 |
| `Oxyrhynchos` | 4,172 | 6.30% | 4,172 |
| `Arsinoites` | 3,884 | 5.86% | 3,884 |
| `Karanis (Arsinoites)` | 2,163 | 3.26% | 2,163 |
| `Abu Mena` | 1,485 | 2.24% | 1,485 |
| `Tebtynis (Arsinoites)` | 1,414 | 2.13% | 1,414 |
| `Hermopolites` | 1,230 | 1.86% | 1,230 |
| `Philadelphia (Arsinoites)` | 1,165 | 1.76% | 1,165 |
| `Hermopolis` | 1,163 | 1.76% | 1,163 |
| `Theadelphia (Arsinoites)` | 1,058 | 1.60% | 1,058 |
| `Soknopaiu Nesos (Arsinoites)` | 1,012 | 1.53% | 1,012 |
| `Herakleopolites` | 935 | 1.41% | 935 |
| `Elephantine` | 931 | 1.41% | 931 |
| `Mons Claudianus` | 862 | 1.30% | 862 |
| `Trimithis (Oasis Magna)` | 831 | 1.25% | 831 |
| `Oxyrhynchites` | 791 | 1.19% | 791 |
| `Apollonopolis` | 783 | 1.18% | 783 |
| `Aphrodites Kome (Antaiopolites)` | 772 | 1.17% | 772 |
| `Theben (Ägypten)` | 765 | 1.15% | 765 |
| `Kysis (Oasis Magna)` | 690 | 1.04% | 690 |
| `Arsinoites (?)` | 674 | 1.02% | 674 |
| `Ptolemais Euergetis (Arsinoites)` | 602 | 0.91% | 602 |
| `Berenike` | 523 | 0.79% | 523 |
| `Oberägypten` | 471 | 0.71% | 471 |
| `Didymoi` | 463 | 0.70% | 463 |
| `Kellis (Oasis Magna)` | 463 | 0.70% | 463 |
| `Arsinoiton Polis` | 456 | 0.69% | 456 |
| `Theben (?)` | 440 | 0.66% | 440 |
| `Panopolis` | 430 | 0.65% | 430 |
| … |  | 2,036 distinct values |  |

### Keyword values

| Value | XML files | Coverage | Occurrences |
|---|---:|---:|---:|
| `Quittung` | 15,806 | 23.85% | 15,807 |
| `Geld` | 8,784 | 13.26% | 8,784 |
| `Steuern` | 7,380 | 11.14% | 7,380 |
| `Vertrag` | 5,255 | 7.93% | 5,256 |
| `Namen` | 4,932 | 7.44% | 4,935 |
| `Liste` | 4,642 | 7.01% | 4,644 |
| `Brief (privat)` | 3,755 | 5.67% | 3,756 |
| `Abrechnung` | 3,618 | 5.46% | 3,618 |
| `Getreide` | 3,399 | 5.13% | 3,399 |
| `Wein` | 2,733 | 4.12% | 2,733 |
| `Brief` | 2,553 | 3.85% | 2,557 |
| `Mumienetikett` | 2,311 | 3.49% | 2,311 |
| `Anweisung` | 2,276 | 3.43% | 2,276 |
| `Land` | 2,133 | 3.22% | 2,133 |
| `unbestimmbar` | 2,124 | 3.21% | 2,124 |
| `Eingabe` | 1,747 | 2.64% | 1,747 |
| `Darlehen` | 1,637 | 2.47% | 1,638 |
| `Pacht` | 1,559 | 2.35% | 1,559 |
| `Weizen` | 1,508 | 2.28% | 1,509 |
| `Zahlung` | 1,479 | 2.23% | 1,479 |
| `Fragment` | 1,474 | 2.22% | 1,474 |
| `Lieferung` | 1,381 | 2.08% | 1,381 |
| `Steuer` | 1,301 | 1.96% | 1,301 |
| `Brief (amtlich)` | 1,280 | 1.93% | 1,280 |
| `Name` | 1,206 | 1.82% | 1,206 |
| `NN an NN` | 1,194 | 1.80% | 1,194 |
| `Kauf` | 1,082 | 1.63% | 1,082 |
| `Transport auf Eseln` | 1,002 | 1.51% | 1,002 |
| `Notiz` | 931 | 1.41% | 931 |
| `Deklaration` | 790 | 1.19% | 790 |
| `Transport` | 771 | 1.16% | 771 |
| `Brief (geschäftlich)` | 766 | 1.16% | 766 |
| `Bank` | 705 | 1.06% | 705 |
| `Register` | 658 | 0.99% | 658 |
| `Arbeit` | 635 | 0.96% | 635 |
| `Lettre` | 621 | 0.94% | 621 |
| `Archives de Frangé` | 600 | 0.91% | 600 |
| `Bericht` | 598 | 0.90% | 598 |
| `Eid` | 545 | 0.82% | 546 |
| `Schreiben (amtlich)` | 511 | 0.77% | 513 |
| `Haus` | 505 | 0.76% | 505 |
| `Militär` | 499 | 0.75% | 499 |
| `Aufstellung` | 490 | 0.74% | 490 |
| `Auftrag` | 479 | 0.72% | 479 |
| `Zahlungen` | 479 | 0.72% | 479 |
| `Öl` | 478 | 0.72% | 479 |
| `Empfang` | 468 | 0.71% | 468 |
| `Gerste` | 460 | 0.69% | 460 |
| `Lohn` | 430 | 0.65% | 430 |
| `Arbeiter` | 423 | 0.64% | 423 |
| … |  | >10,000 distinct values |  |

### `origDate` attribute combinations

| Attributes present together | Elements |
|---|---:|
| `@notAfter`, `@notBefore`, `@precision` | 29,948 |
| `@when` | 15,120 |
| `@notAfter`, `@notBefore` | 12,153 |
| `@when`, `@xml:id` | 2,578 |
| `@cert`, `@notAfter`, `@notBefore`, `@precision` | 1,458 |
| `@notBefore` | 1,186 |
| `@cert`, `@notAfter`, `@notBefore`, `@xml:id` | 1,097 |
| `@precision`, `@when` | 1,091 |
| `@cert`, `@notAfter`, `@notBefore` | 1,063 |
| *(none)* | 915 |
| `@notAfter`, `@notBefore`, `@xml:id` | 869 |
| `@notAfter` | 419 |
| `@cert`, `@when` | 248 |
| `@n`, `@when`, `@xml:id` | 175 |
| `@notBefore`, `@xml:id` | 151 |
| `@cert`, `@when`, `@xml:id` | 128 |
| `@n`, `@notAfter`, `@notBefore`, `@precision`, `@xml:id` | 120 |
| `@n`, `@notAfter`, `@notBefore`, `@xml:id` | 115 |
| `@cert`, `@precision`, `@when` | 98 |
| `@cert`, `@n`, `@notAfter`, `@notBefore`, `@xml:id` | 41 |
| `@cert`, `@notBefore` | 35 |
| `@notAfter`, `@notBefore`, `@precision`, `@xml:id` | 34 |
| `@notAfter`, `@precision` | 23 |
| `@n`, `@notBefore`, `@xml:id` | 21 |
| `@cert`, `@n`, `@when`, `@xml:id` | 18 |
| `@cert`, `@precision`, `@when`, `@xml:id` | 18 |
| `@notAfter`, `@xml:id` | 18 |
| `@cert`, `@notAfter` | 16 |
| `@notBefore`, `@precision` | 13 |
| `@cert`, `@notAfter`, `@notBefore`, `@precision`, `@xml:id` | 12 |
| `@cert`, `@notBefore`, `@xml:id` | 12 |
| `@cert`, `@notAfter`, `@xml:id` | 8 |
| `@precision`, `@when`, `@xml:id` | 4 |
| `@cert`, `@n`, `@notAfter`, `@xml:id` | 3 |
| `@datingMethod`, `@when-custom` | 3 |
| `@n`, `@precision`, `@when`, `@xml:id` | 3 |
| `@precision` | 3 |
| `@cert` | 1 |
| `@cert`, `@n`, `@notBefore`, `@xml:id` | 1 |
| `@n`, `@notAfter`, `@notBefore` | 1 |
| `@n`, `@notAfter`, `@notBefore`, `@precision` | 1 |
| `@n`, `@notAfter`, `@xml:id` | 1 |
| `@n`, `@when` | 1 |
| `@notAfter`, `@notBefore`, `@type` | 1 |

### Complete element-path inventory

Paths distinguish semantically different uses of the same TEI element.

| Element path | XML files | Coverage | Occurrences | Per present file |
|---|---:|---:|---:|---:|
| `/TEI` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/encodingDesc` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/encodingDesc/p` | 66,261 | 100.00% | 66,262 | 1–2 |
| `/TEI/teiHeader/encodingDesc/p/ref` | 62,856 | 94.86% | 62,856 | 1 |
| `/TEI/teiHeader/fileDesc` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/publicationStmt` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/publicationStmt/authority` | 20 | 0.03% | 20 | 1 |
| `/TEI/teiHeader/fileDesc/publicationStmt/idno` | 66,261 | 100.00% | 325,903 | 3–17 |
| `/TEI/teiHeader/fileDesc/sourceDesc` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl` | 1,506 | 2.27% | 1,506 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl/bibl` | 1,506 | 2.27% | 1,506 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl/bibl/biblScope` | 1,399 | 2.11% | 1,399 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl/bibl/ptr` | 1,466 | 2.21% | 1,466 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | 66,261 | 100.00% | 69,224 | 1–5 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/certainty` | 3,478 | 5.25% | 5,690 | 1–8 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/offset` | 2,607 | 3.93% | 2,757 | 1–3 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/precision` | 3,311 | 5.00% | 3,394 | 1–3 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace` | 66,257 | 99.99% | 66,257 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName` | 6 | 0.01% | 9 | 1–3 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName/placeName` | 5 | 0.01% | 8 | 1–3 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance` | 55,606 | 83.92% | 55,897 | 1–3 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p` | 55,605 | 83.92% | 57,362 | 1–4 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/offset` | 62 | 0.09% | 62 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | 55,602 | 83.91% | 122,430 | 1–9 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/placeName` | 1 | 0.00% | 3 | 3 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/altIdentifier` | 2 | 0.00% | 2 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/altIdentifier/idno` | 2 | 0.00% | 2 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/collection` | 7,840 | 11.83% | 7,840 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/idno` | 16,377 | 24.72% | 16,377 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/institution` | 1 | 0.00% | 1 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/placeName` | 57,741 | 87.14% | 57,741 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/placeName/settlement` | 57,741 | 87.14% | 57,741 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc` | 66,257 | 99.99% | 66,257 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc/objectDesc` | 66,257 | 99.99% | 66,257 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc/objectDesc/supportDesc` | 66,257 | 99.99% | 66,257 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc/objectDesc/supportDesc/support` | 66,257 | 99.99% | 66,257 | 1 |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc/objectDesc/supportDesc/support/material` | 66,257 | 99.99% | 66,257 | 1 |
| `/TEI/teiHeader/fileDesc/titleStmt` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/fileDesc/titleStmt/title` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/profileDesc` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/profileDesc/langUsage` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/teiHeader/profileDesc/langUsage/language` | 66,261 | 100.00% | 463,826 | 3–8 |
| `/TEI/teiHeader/profileDesc/textClass` | 66,118 | 99.78% | 66,118 | 1 |
| `/TEI/teiHeader/profileDesc/textClass/keywords` | 66,118 | 99.78% | 66,118 | 1 |
| `/TEI/teiHeader/profileDesc/textClass/keywords/term` | 66,118 | 99.78% | 188,259 | 1–25 |
| `/TEI/teiHeader/revisionDesc` | 66,258 | 100.00% | 66,258 | 1 |
| `/TEI/teiHeader/revisionDesc/change` | 66,258 | 100.00% | 201,070 | 1–14 |
| `/TEI/text` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/text/body` | 66,261 | 100.00% | 66,261 | 1 |
| `/TEI/text/body/div` | 66,261 | 100.00% | 254,011 | 1–8 |
| `/TEI/text/body/div/div` | 2 | 0.00% | 2 | 1 |
| `/TEI/text/body/div/div/p` | 2 | 0.00% | 2 | 1 |
| `/TEI/text/body/div/div/p/figure` | 2 | 0.00% | 2 | 1 |
| `/TEI/text/body/div/div/p/figure/graphic` | 2 | 0.00% | 2 | 1 |
| `/TEI/text/body/div/head` | 33,866 | 51.11% | 49,566 | 1–4 |
| `/TEI/text/body/div/list` | 5,118 | 7.72% | 5,118 | 1 |
| `/TEI/text/body/div/list/item` | 5,118 | 7.72% | 11,189 | 1–65 |
| `/TEI/text/body/div/list/item/date` | 5,088 | 7.68% | 11,142 | 1–65 |
| `/TEI/text/body/div/list/item/date/certainty` | 456 | 0.69% | 1,733 | 1–65 |
| `/TEI/text/body/div/list/item/note` | 476 | 0.72% | 812 | 1–18 |
| `/TEI/text/body/div/list/item/ref` | 5,076 | 7.66% | 11,134 | 1–65 |
| `/TEI/text/body/div/listBibl` | 66,261 | 100.00% | 111,702 | 1–8 |
| `/TEI/text/body/div/listBibl/bibl` | 66,261 | 100.00% | 170,017 | 1–36 |
| `/TEI/text/body/div/listBibl/bibl/biblScope` | 66,259 | 100.00% | 233,091 | 1–46 |
| `/TEI/text/body/div/listBibl/bibl/ptr` | 25,425 | 38.37% | 25,432 | 1–2 |
| `/TEI/text/body/div/listBibl/bibl/title` | 66,261 | 100.00% | 68,610 | 1–3 |
| `/TEI/text/body/div/listBibl/head` | 4,474 | 6.75% | 5,149 | 1–6 |
| `/TEI/text/body/div/note` | 5,495 | 8.29% | 11,303 | 1–4 |
| `/TEI/text/body/div/p` | 66,156 | 99.84% | 137,341 | 1–31 |
| `/TEI/text/body/div/p/bibl` | 26,773 | 40.41% | 30,609 | 1–20 |
| `/TEI/text/body/div/p/figure` | 35,497 | 53.57% | 41,320 | 1–54 |
| `/TEI/text/body/div/p/figure/graphic` | 35,494 | 53.57% | 41,317 | 1–54 |

### Complete path/attribute inventory

| Element path | Attribute | XML files | Coverage | Occurrences | Values |
|---|---|---:|---:|---:|---|
| `/TEI` | `@xml:id` | 62,751 | 94.70% | 62,751 | >10,000 distinct; `hgv12423` (5), `hgv12001b` (3), `hgv13418` (3), `hgv73447` (3), `hgv12095` (2), `hgv25266` (2), `hgv1` (1), `hgv10` (1), `hgv100` (1), `hgv1000` (1), `hgv10000` (1), `hgv10002` (1) |
| `/TEI` | `@xml:lang` | 83 | 0.13% | 83 | 1 distinct; `en` (83) |
| `/TEI/teiHeader/fileDesc/publicationStmt/idno` | `@type` | 66,261 | 100.00% | 325,903 | 10 distinct; `TM` (66,261), `ddb-hybrid` (66,261), `filename` (66,261), `ddb-filename` (66,203), `ddb-perseus-style` (60,760), `HGV-deprecated` (71), `TM-deprecated` (71), `dclp` (7), `APD` (6), `dclp-hybrid` (2) |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl/bibl` | `@type` | 1,506 | 2.27% | 1,506 | 1 distinct; `SB` (1,506) |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl/bibl/biblScope` | `@type` | 1,399 | 2.11% | 1,399 | 1 distinct; `pp` (1,399) |
| `/TEI/teiHeader/fileDesc/sourceDesc/listBibl/bibl/ptr` | `@target` | 1,466 | 2.21% | 1,466 | 659 distinct; `https://papyri.info/biblio/95978` (48), `http://papyri.info/biblio/95450` (31), `https://papyri.info/biblio/96110` (26), `https://papyri.info/biblio/96375` (26), `https://papyri.info/biblio/96415` (25), `http://papyri.info/biblio/86953` (21), `http://papyri.info/biblio/95492` (18), `https://papyri.info/biblio/76146` (18), `http://papyri.info/biblio/86392` (17), `http://papyri.info/biblio/78505` (16), `http://papyri.info/biblio/95443` (14), `https://papyri.info/biblio/97213` (14) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@cert` | 3,551 | 5.36% | 4,257 | 1 distinct; `low` (4,257) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@datingMethod` | 3 | 0.00% | 3 | 1 distinct; `#julian` (3) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@n` | 239 | 0.36% | 501 | 3 distinct; `1` (239), `2` (235), `3` (27) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@notAfter` | 46,160 | 69.66% | 47,401 | 4,286 distinct; `0300` (4,729), `0200` (3,754), `0400` (3,246), `0700` (2,962), `0800` (2,684), `0600` (2,545), `0650` (1,878), `0100` (1,017), `0500` (969), `-0226` (844), `0425` (728), `0750` (720) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@notBefore` | 47,014 | 70.95% | 48,332 | 4,790 distinct; `0101` (5,422), `0601` (4,171), `0501` (3,520), `0301` (3,300), `0201` (3,207), `0001` (2,116), `0701` (1,628), `0401` (1,335), `-0275` (847), `-0200` (720), `0276` (553), `0098` (475) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@precision` | 32,727 | 49.39% | 32,826 | 2 distinct; `low` (31,570), `medium` (1,256) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@type` | 1 | 0.00% | 1 | 1 distinct; `textDate` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@when` | 17,887 | 26.99% | 19,482 | >10,000 distinct; `0100` (44), `0200` (44), `0150` (34), `-0250` (32), `0346` (30), `-0220` (26), `-0221-02-27` (21), `0001` (21), `-0221-02-26` (20), `-0222-01-28` (20), `-0190` (19), `0107` (19) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@when-custom` | 3 | 0.00% | 3 | 1 distinct; `0300-02-29` (3) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate` | `@xml:id` | 2,479 | 3.74% | 5,427 | 3 distinct; `dateAlternativeX` (2,479), `dateAlternativeY` (2,476), `dateAlternativeZ` (472) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/certainty` | `@locus` | 3,478 | 5.25% | 5,690 | 1 distinct; `value` (5,690) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/certainty` | `@match` | 3,478 | 5.25% | 5,690 | 11 distinct; `../year-from-date(@when)` (2,946), `../year-from-date(@notBefore)` (944), `../day-from-date(@when)` (569), `../offset[@type='before']` (400), `../month-from-date(@notBefore)` (208), `../month-from-date(@when)` (204), `../day-from-date(@notBefore)` (184), `../offset[@type='after']` (171), `../year-from-date(@notAfter)` (26), `../day-from-date(@notAfter)` (25), `../month-from-date(@notAfter)` (13) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/certainty` | `@n` | 22 | 0.03% | 61 | 3 distinct; `1` (29), `2` (29), `3` (3) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/offset` | `@n` | 2,607 | 3.93% | 2,757 | 2 distinct; `1` (2,754), `2` (3) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/offset` | `@type` | 2,607 | 3.93% | 2,757 | 2 distinct; `after` (1,798), `before` (959) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/precision` | `@degree` | 3,286 | 4.96% | 3,355 | 3 distinct; `0.5` (3,128), `0.1` (205), `0.3` (22) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/precision` | `@match` | 3,143 | 4.74% | 3,225 | 2 distinct; `../@notBefore` (3,154), `../@notAfter` (71) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate/precision` | `@n` | 22 | 0.03% | 44 | 2 distinct; `1` (22), `2` (22) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace` | `@evidence` | 1 | 0.00% | 1 | 1 distinct; `conjecture` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace` | `@precision` | 1 | 0.00% | 1 | 1 distinct; `low` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName` | `@n` | 1 | 0.00% | 3 | 3 distinct; `1` (1), `2` (1), `3` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName` | `@type` | 5 | 0.01% | 8 | 3 distinct; `ancientFindspot` (5), `ancientRegion` (2), `nome` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName/placeName` | `@key` | 1 | 0.00% | 1 | 1 distinct; `Aegyptus` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName/placeName` | `@n` | 1 | 0.00% | 1 | 1 distinct; `1` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName/placeName` | `@ref` | 1 | 0.00% | 1 | 1 distinct; `https://www.trismegistos.org/place/332 https://pleiades.stoa.org/places/736893` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName/placeName` | `@subtype` | 1 | 0.00% | 2 | 2 distinct; `nome` (1), `region` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace/placeName/placeName` | `@type` | 1 | 0.00% | 2 | 1 distinct; `ancient` (2) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance` | `@n` | 193 | 0.29% | 413 | 3 distinct; `1` (193), `2` (190), `3` (30) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance` | `@type` | 55,478 | 83.73% | 55,769 | 6 distinct; `located` (55,111), `found` (418), `composed` (190), `sent` (34), `acquired` (15), `received` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance` | `@when` | 66 | 0.10% | 66 | 16 distinct; `1930` (34), `1895` (8), `1920` (4), `1924` (3), `1929` (3), `1903` (2), `1928` (2), `2007` (2), `1889` (1), `1917` (1), `1922` (1), `1923` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p` | `@exclude` | 1,469 | 2.22% | 2,943 | 51 distinct; `#geog_1` (1,441), `#geog_2` (1,441), `#geog_1 #geog_2` (5), `#geog_1 #geog_3` (5), `#geog_2 #geog_3` (5), `#geoBHAD7C` (1), `#geoBHDA1E` (1), `#geoBHDIA3` (1), `#geoBJ1C1F` (1), `#geoBJ91ID` (1), `#geoC22EJ9` (1), `#geoC2IH87` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p` | `@n` | 70 | 0.11% | 143 | 2 distinct; `1` (72), `2` (71) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p` | `@xml:id` | 2,811 | 4.24% | 4,444 | 1,362 distinct; `geog_1` (1,449), `geog_2` (1,449), `geoC22EJ9` (40), `geoE4G4CJ` (30), `geoF5H7I8` (12), `geoFEACGH` (10), `geoFBCEA0` (9), `geoJ9FEG` (9), `geoJBHFE9` (9), `geoBJEH7I` (8), `geoJI88DH` (8), `geoBDAGH0` (7) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | `@cert` | 4,955 | 7.48% | 4,984 | 1 distinct; `low` (4,984) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | `@key` | 1,185 | 1.79% | 1,185 | 1 distinct; `Aegyptus` (1,185) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | `@n` | 4,420 | 6.67% | 8,325 | 4 distinct; `1` (4,474), `2` (2,936), `3` (903), `4` (12) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | `@ref` | 52,715 | 79.56% | 75,821 | 780 distinct; `https://www.trismegistos.org/place/332 https://pleiades.stoa.org/places/736893` (17,665), `https://pleiades.stoa.org/places/991398 https://www.trismegistos.org/place/2983 https://w…` (5,907), `https://pleiades.stoa.org/places/736983 https://www.trismegistos.org/place/1524` (4,458), `https://pleiades.stoa.org/places/736982 https://www.trismegistos.org/place/2722` (4,354), `https://www.trismegistos.org/place/2720` (3,603), `https://pleiades.stoa.org/places/736932 https://www.trismegistos.org/place/1008` (2,244), `https://www.trismegistos.org/place/2713 https://pleiades.stoa.org/places/736921` (2,023), `https://www.trismegistos.org/place/2722 https://pleiades.stoa.org/places/736982` (1,517), `https://pleiades.stoa.org/places/737008 https://www.trismegistos.org/place/1760` (1,506), `https://pleiades.stoa.org/places/737072 https://www.trismegistos.org/place/2287` (1,504), `https://pleiades.stoa.org/places/727105 https://www.trismegistos.org/place/2711` (1,485), `https://pleiades.stoa.org/places/756574 https://www.trismegistos.org/place/816` (1,415) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | `@subtype` | 42,848 | 64.67% | 75,422 | 3 distinct; `region` (42,575), `nome` (32,504), `province` (343) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName` | `@type` | 55,602 | 83.91% | 122,365 | 3 distinct; `ancient` (122,230), `modern` (133), `ancientFindspot` (2) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/placeName` | `@ref` | 1 | 0.00% | 2 | 2 distinct; `https://pleiades.stoa.org/places/736982 https://www.trismegistos.org/place/2722` (1), `https://pleiades.stoa.org/places/736983 https://www.trismegistos.org/place/1524` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/placeName` | `@subtype` | 1 | 0.00% | 2 | 2 distinct; `nome` (1), `region` (1) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/placeName` | `@type` | 1 | 0.00% | 3 | 1 distinct; `ancient` (3) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/altIdentifier` | `@type` | 2 | 0.00% | 2 | 1 distinct; `temporary` (2) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/altIdentifier/idno` | `@type` | 2 | 0.00% | 2 | 1 distinct; `invNo` (2) |
| `/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/idno` | `@type` | 16,377 | 24.72% | 16,377 | 1 distinct; `invNo` (16,377) |
| `/TEI/teiHeader/profileDesc/langUsage/language` | `@ident` | 66,261 | 100.00% | 463,826 | 8 distinct; `de` (66,261), `el` (66,261), `en` (66,261), `es` (66,260), `fr` (66,260), `it` (66,260), `la` (66,260), `ar` (3) |
| `/TEI/teiHeader/profileDesc/textClass/keywords` | `@scheme` | 66,118 | 99.78% | 66,118 | 1 distinct; `hgv` (66,118) |
| `/TEI/teiHeader/profileDesc/textClass/keywords/term` | `@n` | 5,575 | 8.41% | 17,007 | 15 distinct; `1` (5,575), `2` (5,111), `3` (3,505), `4` (1,614), `5` (714), `6` (288), `7` (110), `8` (46), `9` (18), `10` (9), `11` (8), `12` (4) |
| `/TEI/teiHeader/revisionDesc/change` | `@when` | 66,258 | 100.00% | 201,070 | >10,000 distinct; `2011-04-20` (56,099), `2009-07-02` (25,721), `2011-04-19` (18,926), `2011-04-18` (4,122), `2009-07-23` (1,519), `2009-01-22` (1,383), `2013-04-05` (1,257), `2003-09-07` (1,169), `1990-02-26` (1,001), `2012-08-28` (912), `2010-06-24` (842), `2014-03-05` (802) |
| `/TEI/teiHeader/revisionDesc/change` | `@who` | 66,258 | 100.00% | 201,070 | 335 distinct; `HGV` (120,925), `IDP` (62,240), `http://papyri.info/editor/users/james.cowey` (4,990), `http://papyri.info/users/james.cowey` (2,885), `http://papyri.info/editor/users/paulpeters` (1,584), `http://papyri.info/editor` (1,507), `https://papyri.info/editor/users/Mike%20Sampson` (1,428), `http://papyri.info/editor/users/Mike%20Sampson` (808), `http://papyri.info/editor/users/pag` (490), `http://papyri.info/editor/users/LaviniaFerretti` (393), `http://papyri.info/editor/Mike%20Sampson` (359), `http://papyri.info/editor/users/ngonis` (350) |
| `/TEI/text/body/div` | `@subtype` | 66,261 | 100.00% | 218,137 | 8 distinct; `principalEdition` (66,261), `illustrations` (65,077), `general` (36,439), `corrections` (27,484), `otherPublications` (12,755), `mentionedDates` (5,557), `translations` (4,543), `citations` (21) |
| `/TEI/text/body/div` | `@type` | 66,261 | 100.00% | 254,011 | 4 distinct; `bibliography` (176,141), `commentary` (41,996), `figure` (35,576), `edition` (298) |
| `/TEI/text/body/div/div` | `@type` | 2 | 0.00% | 2 | 1 distinct; `figure` (2) |
| `/TEI/text/body/div/div/p/figure/graphic` | `@url` | 2 | 0.00% | 2 | 2 distinct; `http://purl.flvc.org/fsu/fd/FSU_ostraka_10` (1), `https://digitallibrary.unicatt.it/unicatt/0b02da82804d7ef7` (1) |
| `/TEI/text/body/div/head` | `@xml:lang` | 4,487 | 6.77% | 4,490 | 1 distinct; `de` (4,490) |
| `/TEI/text/body/div/list/item` | `@n` | 136 | 0.21% | 548 | 24 distinct; `1` (136), `2` (136), `3` (75), `4` (45), `5` (33), `6` (23), `7` (20), `8` (12), `9` (12), `10` (9), `11` (8), `12` (8) |
| `/TEI/text/body/div/list/item/date` | `@cert` | 154 | 0.23% | 292 | 1 distinct; `low` (292) |
| `/TEI/text/body/div/list/item/date` | `@notAfter` | 3,106 | 4.69% | 5,486 | 2,291 distinct; `0160` (65), `0146` (63), `0174` (58), `0132` (53), `0154` (51), `0188` (47), `0224` (40), `0118` (39), `-0130` (31), `0104` (29), `0216` (26), `-0163` (25) |
| `/TEI/text/body/div/list/item/date` | `@notBefore` | 3,102 | 4.68% | 5,481 | 2,262 distinct; `0159` (65), `0145` (63), `0173` (57), `0131` (53), `0153` (49), `0187` (47), `0117` (45), `0223` (40), `-0131` (31), `0103` (31), `0215` (26), `-0164` (25) |
| `/TEI/text/body/div/list/item/date` | `@type` | 5,088 | 7.68% | 11,142 | 1 distinct; `mentioned` (11,142) |
| `/TEI/text/body/div/list/item/date` | `@when` | 2,546 | 3.84% | 5,658 | 5,074 distinct; `-0257-07-21` (9), `-0257-05-05` (6), `0217` (6), `0710-02-09` (6), `-0118` (5), `-0257-05-06` (5), `0112-12-24` (5), `0207` (5), `0215-09-03` (5), `0299-12-23` (5), `0368` (5), `-0159-03-08` (4) |
| `/TEI/text/body/div/list/item/date/certainty` | `@degree` | 311 | 0.47% | 1,151 | 1 distinct; `1` (1,151) |
| `/TEI/text/body/div/list/item/date/certainty` | `@given` | 311 | 0.47% | 1,151 | 3 distinct; `#dateAlternativeX` (650), `#dateAlternativeY` (456), `#dateAlternativeZ` (45) |
| `/TEI/text/body/div/list/item/date/certainty` | `@locus` | 456 | 0.69% | 1,733 | 1 distinct; `value` (1,733) |
| `/TEI/text/body/div/list/item/date/certainty` | `@match` | 191 | 0.29% | 582 | 13 distinct; `../date/year-from-date(@when)` (185), `../date/year-from-date(@notAfter)` (102), `../date/year-from-date(@notBefore)` (101), `../date/day-from-date(@when)` (92), `../date/month-from-date(@when)` (22), `../date/day-from-date(@notAfter)` (21), `../date/day-from-date(@notBefore)` (20), `../date/month-from-date(@notAfter)` (12), `../date/month-from-date(@notBefore)` (12), `../year-from-date(@notAfter)` (5), `../year-from-date(@notBefore)` (5), `../year-from-date(@when)` (4) |
| `/TEI/text/body/div/list/item/date/certainty` | `@n` | 14 | 0.02% | 63 | 5 distinct; `1` (25), `2` (25), `3` (8), `4` (3), `5` (2) |
| `/TEI/text/body/div/list/item/note` | `@type` | 476 | 0.72% | 812 | 2 distinct; `comment` (739), `annotation` (73) |
| `/TEI/text/body/div/listBibl` | `@xml:lang` | 4,494 | 6.78% | 5,162 | 5 distinct; `en` (2,436), `de` (1,335), `fr` (872), `it` (449), `es` (70) |
| `/TEI/text/body/div/listBibl/bibl` | `@n` | 501 | 0.76% | 1,532 | 17 distinct; `1` (569), `2` (566), `3` (233), `4` (84), `5` (38), `6` (14), `7` (8), `8` (6), `10` (2), `11` (2), `12` (2), `13` (2) |
| `/TEI/text/body/div/listBibl/bibl` | `@subtype` | 66,261 | 100.00% | 82,313 | 2 distinct; `principal` (66,261), `other` (16,052) |
| `/TEI/text/body/div/listBibl/bibl` | `@type` | 66,261 | 100.00% | 167,651 | 5 distinct; `publication` (82,313), `BL` (53,875), `BL-online` (25,419), `translations` (6,043), `illustration` (1) |
| `/TEI/text/body/div/listBibl/bibl/biblScope` | `@n` | 4,818 | 7.27% | 11,099 | 5 distinct; `1` (4,812), `2` (3,986), `3` (1,561), `4` (721), `5` (19) |
| `/TEI/text/body/div/listBibl/bibl/biblScope` | `@type` | 66,259 | 100.00% | 230,742 | 14 distinct; `volume` (100,587), `numbers` (64,095), `pages` (55,780), `generic` (2,942), `fascicle` (2,595), `side` (1,538), `number` (1,300), `lines` (911), `columns` (587), `inventory` (314), `folio` (45), `null` (26) |
| `/TEI/text/body/div/listBibl/bibl/ptr` | `@target` | 25,425 | 38.37% | 25,432 | >10,000 distinct; `https://beehive.zaw.uni-heidelberg.de/hgv/10432b` (5), `https://beehive.zaw.uni-heidelberg.de/hgv/14167` (3), `https://beehive.zaw.uni-heidelberg.de/hgv/11569` (2), `https://beehive.zaw.uni-heidelberg.de/hgv/12001b` (2), `https://beehive.zaw.uni-heidelberg.de/hgv/13418` (2), `https://beehive.zaw.uni-heidelberg.de/hgv/15019` (2), `https://beehive.zaw.uni-heidelberg.de/hgv/19921` (2), `https://beehive.zaw.uni-heidelberg.de/hgv/21285` (2), `https://beehive.zaw.uni-heidelberg.de/hgv/22344` (2), `86328` (1), `86913` (1), `https://beehive.zaw.uni-heidelberg.de/hgv/1` (1) |
| `/TEI/text/body/div/listBibl/bibl/title` | `@level` | 66,261 | 100.00% | 66,261 | 1 distinct; `s` (66,261) |
| `/TEI/text/body/div/listBibl/bibl/title` | `@type` | 66,261 | 100.00% | 66,261 | 1 distinct; `abbreviated` (66,261) |
| `/TEI/text/body/div/listBibl/head` | `@xml:lang` | 4,474 | 6.75% | 5,149 | 1 distinct; `de` (5,149) |
| `/TEI/text/body/div/note` | `@subtype` | 269 | 0.41% | 583 | 3 distinct; `X` (269), `Y` (269), `Z` (45) |
| `/TEI/text/body/div/note` | `@type` | 5,495 | 8.29% | 11,303 | 2 distinct; `original` (5,809), `source` (5,494) |
| `/TEI/text/body/div/p/bibl` | `@n` | 310 | 0.47% | 811 | 12 distinct; `1` (313), `2` (305), `3` (90), `4` (38), `5` (21), `6` (15), `7` (10), `8` (8), `9` (5), `10` (3), `11` (2), `12` (1) |
| `/TEI/text/body/div/p/bibl` | `@type` | 26,773 | 40.41% | 30,609 | 1 distinct; `illustration` (30,609) |
| `/TEI/text/body/div/p/figure` | `@n` | 1,298 | 1.96% | 1,949 | 30 distinct; `1` (1,293), `2` (532), `3` (54), `4` (16), `5` (8), `6` (5), `7` (5), `8` (5), `9` (5), `10` (4), `11` (2), `12` (2) |
| `/TEI/text/body/div/p/figure/graphic` | `@url` | 35,494 | 53.57% | 41,317 | >10,000 distinct; `http://www.papyrologie.paris-sorbonne.fr/menu1/collections/pgrec/preinach.htm` (68), `http://wwwapp.cc.columbia.edu/ldpd/app/apis/item?mode=item&key=columbia.apis.p329` (19), `https://cbl01.intranda.com/viewer/image/MP_88/1` (17), `http://pcount.arts.kuleuven.ac.be/plates.html` (16), `http://www.columbia.edu/cgi-bin/dlo?obj=nyu.apis.4774` (12), `https://hdl.handle.net/2333.1/vdnck4zp` (12), `http://www.bl.uk/manuscripts/FullDisplay.aspx?ref=Papyrus_828(A-K)` (10), `https://access.bl.uk/item/viewer/ark:/81055/vdc_100147463575.0x000001` (10), `https://web.archive.org/web/20200924190039/http://omeka.wustl.edu/omeka/exhibits/show/pap…` (10), `http://data.onb.ac.at/rec/RZ00000642` (8), `http://quod.lib.umich.edu/a/apis/x-1431` (8), `https://access.bl.uk/item/viewer/ark:/81055/vdc_100147464852.0x000001` (8) |
