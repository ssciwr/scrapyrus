# Biblio XML analysis for bibliographic retrieval

## Executive recommendation

Model each standalone `Biblio` XML file as a bibliographic record, then model its repeatable TEI parts as child tables. Do not flatten the corpus to one citation string per record. The XML is compact, but the retrieval value is spread across typed titles, contributors, identifiers, publication years, page/issue scopes, notes, raw Bibliographie Papyrologique segments, and typed relationships to containers, reviews, and mentioned papyrological documents.

For RAG, use deterministic metadata filters before vector retrieval. A useful query layer should be able to filter or join by Biblio ID, BP ID, ISBN, author/editor name, year, record type, title level, container journal/book, reviewed work, and mentioned DDbDP/TM/DCLP identifiers. Vector embeddings should rank the natural-language citation, title, note, and summary text; they should not be responsible for resolving an identifier such as `sb;30;17293` or a container such as `papyri.info/biblio/511`.

The minimum useful model is:

- one bibliographic record per XML file, with raw XML retained;
- many identifiers, titles, contributors, scopes, notes, original citation segments, links, and relations per record;
- `relatedItem/@type` as a typed edge, not as text;
- `appearsIn` and `reviews` as Biblio-to-Biblio relations when a `ptr` target is present;
- `mentions` as a publication-to-document/series mention, because these entries usually contain DDbDP, TM, DCLP, inventory, title, and scope data rather than a Biblio pointer;
- a separate link table from HGV documents to Biblio records, because direct HGV metadata pointers cover only a small part of the standalone Biblio corpus.

## Scope and method

The current repository checkout does not contain `./idp.data/Biblio`. The analysis used the sibling local checkout at `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio`, with `idp.data` Git revision `f90abd7c1d4578d669f2c28f9356a98309e617ac`.

It is reproducible with the analysis profiler:

```console
python scripts/analyze_biblio.py idp.data/Biblio --idp-data idp.data --output biblio_analysis.json
```

The optional `--idp-data` pass scans `HGV_meta_EpiDoc` for direct `https://papyri.info/biblio/{id}` pointers so the report can distinguish standalone bibliography structure from document-to-bibliography linkage.

## Corpus overview

All 72,065 XML files parsed successfully. They live in 92 numeric directory buckets and represent 72,060 distinct parsed Biblio IDs; five IDs appear twice in the parsed identity set: `95689`, `96520`, `97533`, `97685`, and `97688`.

Identity is mostly regular:

| Identity check | Files |
|---|---:|
| File stem matches root `@xml:id` and `idno type="pi"` | 72,056 |
| File stem matches `idno type="pi"` only | 7 |
| File stem matches root `@xml:id` only | 1 |
| Neither check matches | 1 |

Every file has an `idno type="pi"`. Other identifiers are common enough to normalize:

| `idno/@type` | Occurrences |
|---|---:|
| `pi` | 72,065 |
| `bp` | 52,756 |
| `bp_old` | 17,692 |
| `isbn` | 3,819 |
| `sonderdruck` | 2,436 |
| `checklist` | 716 |
| `herc-id` | 541 |
| `e-issn` | 1 |
| `prefacePageCount` | 1 |

### Record types

| Root `bibl/@type` | Files | Coverage |
|---|---:|---:|
| `article` | 46,413 | 64.40% |
| `book` | 12,554 | 17.42% |
| `review` | 10,755 | 14.92% |
| `journal` | 2,322 | 3.22% |
| no type | 20 | 0.03% |
| `website` | 1 | <0.01% |

| Root `bibl/@subtype` | Files | Coverage |
|---|---:|---:|
| `journal` | 29,865 | 41.44% |
| no subtype | 22,967 | 31.87% |
| `book` | 15,128 | 20.99% |
| `edited` | 2,063 | 2.86% |
| `other` | 1,405 | 1.95% |
| `authored` | 635 | 0.88% |
| `website` | 2 | <0.01% |

`xml:lang` is absent in 56,960 files. The most common populated values are `en` 6,983, `de` 3,128, `it` 2,838, and `fr` 1,844. Treat language as optional metadata for ranking/display, not as a required partition key.

## Main XML fields

The files are standalone TEI `bibl` fragments. Direct children are stable enough for a compact relational schema, but most important fields are repeatable.

| Direct child | Files | Coverage | Occurrences | Modeling note |
|---|---:|---:|---:|---|
| `idno` | 72,065 | 100.00% | 150,027 | Identifier table |
| `author` | 64,640 | 89.69% | 72,666 | Ordered contributor table |
| `seg` | 63,917 | 88.69% | 278,583 | Source citation/search text table |
| `title` | 61,297 | 85.06% | 61,885 | Typed title table |
| `biblScope` | 57,252 | 79.44% | 99,572 | Scope table, mostly pages/issues |
| `date` | 56,596 | 78.53% | 56,597 | Raw date plus parsed year/status |
| `relatedItem` | 55,923 | 77.60% | 88,773 | Typed relation table |
| `note` | 42,667 | 59.20% | 60,583 | Notes/search text/facets |
| `pubPlace` | 12,043 | 16.71% | 13,192 | Publication detail table |
| `series` | 10,798 | 14.98% | 10,846 | Series child table |
| `publisher` | 7,915 | 10.98% | 8,026 | Publication detail table |
| `ptr` | 5,342 | 7.41% | 5,403 | External link table |
| `editor` | 2,882 | 4.00% | 5,926 | Ordered contributor table |

### Titles and contributors

60,923 records have a direct title with `@type="main"`. Direct title signatures are:

| Title signature | Occurrences |
|---|---:|
| `level=a, type=main` | 46,441 |
| `level=m, type=main` | 12,531 |
| `level=j, type=main` | 1,956 |
| `level=j, type=short-BP` | 923 |
| `level=j, type=short` | 17 |
| `level=m, type=short-BP` | 10 |
| `level=j, type=short-Checklist` | 7 |

Authors and editors are mostly structured as direct `forename` plus `surname` children. `author/@n` and `editor/@n` occur often enough to use for contributor order, but ingestion should still assign a sequence from XML order when `@n` is absent.

| Contributor field | Files with none | Files with one | Files with two or more | Occurrences |
|---|---:|---:|---:|---:|
| `author` | 7,425 | 59,565 | 5,075 | 72,666 |
| `editor` | 69,183 | 1,174 | 1,708 | 5,926 |

### Dates and scopes

Direct `date` is text-only in this corpus: no direct date attributes were observed. It is usually a publication year, but it should be stored as raw text plus a parsed year and normalization status. The profiler found 700 distinct date strings, a parsed year span of 1788-2209, and malformed concatenated values such as `19501951` and `19851986`. Do not make a plain integer year the only stored value.

`biblScope` is strongly typed:

| `biblScope/@type` | Occurrences | Notes |
|---|---:|---|
| `pp` | 56,143 | Mostly has `@from` and `@to` |
| `issue` | 41,190 | Journal/volume issue labels |
| `no` | 1,402 | Number labels |
| `col` | 680 | Column labels |
| `fasc` | 99 | Fascicle labels |
| `article` | 33 | Article number labels |
| `tome` | 24 | Tome labels |
| `number` | 1 | Rare variant |

Store scope `type`, visible label, `from`, `to`, and source attributes. Page ranges are important for display and citation matching, but scope labels are heterogeneous.

## Relations

`relatedItem` is the most important structural feature for RAG because it captures bibliography graph edges and mentioned papyrological documents.

| `relatedItem/@type` | Occurrences | Interpretation |
|---|---:|---|
| `appearsIn` | 56,607 | Article/chapter/review appears in a container Biblio record |
| `mentions` | 21,004 | Publication mentions a papyrological text, series item, or inventory reference |
| `reviews` | 11,161 | Review points to the reviewed Biblio record |
| `reedition` | 1 | Rare relation |

67,768 related items contain a `ptr` to `papyri.info/biblio`; all of these are under `appearsIn` or `reviews`. There are 9,439 distinct Biblio targets. The most referenced containers are `511` (4,734 direct target occurrences), `174` (2,470), `912` (1,669), `83` (1,306), and `110` (1,149).

`mentions` is different: the 21,004 occurrences have no `ptr`. Their nested `bibl` usually carries short series titles, volume/number scopes, and identifiers. Nested mentioned-document identifier counts are:

| Nested mentioned `idno/@type` | Occurrences |
|---|---:|
| `ddb` | 16,344 |
| `invNo` | 5,148 |
| `tm` | 1,835 |
| `dclp` | 24 |

For example, a publication may mention `P. Lond. II 363` with `idno type="ddb"` equal to `sb;30;17293`. This should become a document/series mention edge, not a bibliographic-record relation.

## Notes and source citation segments

`note` and `seg` are where much of the natural-language retrieval value lives.

| `note/@type` | Occurrences |
|---|---:|
| no type | 38,638 |
| `pageCount` | 8,140 |
| `illustration` | 7,270 |
| `prefacePageCount` | 4,193 |
| `papyrological-series` | 1,183 |
| `subject` | 1,155 |
| `Pub` | 4 |

There are 278,583 direct `seg type="original"` elements in 63,917 files. These are source Bibliographie Papyrologique strings and should be preserved for search and audit.

| `seg/@subtype` | Occurrences | Use |
|---|---:|---|
| `titre` | 53,170 | Source title string |
| `publication` | 53,134 | Source publication/citation string |
| `index` | 52,698 | Source index term/string |
| `nom` | 52,552 | Source name string |
| `resume` | 38,833 | Abstract/summary-like text |
| `cr` | 13,933 | Review/source citation string |
| `indexBis` | 10,336 | Additional index string |
| `sbSeg` | 3,908 | Sammelbuch-related source string |
| `internet` | 16 | Web source string |

For RAG, embed a curated text assembled from normalized fields plus selected `note` and `seg` text. Keep the `seg` subtype in metadata so answers can explain whether a match came from a title, publication string, index entry, or summary.

## Linkage to HGV metadata

The optional HGV scan found direct `https://papyri.info/biblio/{id}` pointers in only 1,428 of 66,261 HGV metadata files. There are 1,433 pointer occurrences, 617 distinct referenced Biblio IDs, and 613 of those IDs resolve to current Biblio records. Four referenced IDs are missing from the Biblio corpus: `96186`, `86456`, `95426`, and `95660`.

This is useful linkage but very sparse: only 613 of 72,060 distinct standalone Biblio IDs are directly referenced from HGV metadata. Do not use direct HGV pointers as the only path from documents to bibliography. Ingestion should combine:

- HGV metadata bibliography entries and `ptr` links;
- Biblio `relatedItem type="mentions"` DDbDP/TM/DCLP/inventory mentions;
- normalized series/title/scope matching where no explicit identifier exists;
- retained raw XML for curation and audit.

## Recommended PostgreSQL schema

This is deliberately smaller than TEI. It is designed for deterministic filters, graph traversal, and RAG chunking while retaining source XML.

```sql
CREATE TABLE biblio_record (
    id                    bigserial PRIMARY KEY,
    pi_id                 bigint,
    source_path           text NOT NULL UNIQUE,
    tei_xml_id            text,
    record_type           text,
    record_subtype        text,
    xml_lang              text,
    display_title         text,
    publication_year      integer,
    date_label            text,
    normalization_status  text NOT NULL,
    raw_xml               xml NOT NULL,
    source_attributes     jsonb NOT NULL,
    UNIQUE (pi_id, source_path)
);

CREATE TABLE biblio_identifier (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    identifier_type   text NOT NULL,
    identifier_value  text NOT NULL,
    normalized_value  text,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_title (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    level_code        text,
    title_type        text,
    title_text        text NOT NULL,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_contributor (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    role              text NOT NULL CHECK (role IN ('author', 'editor')),
    forename          text,
    surname           text,
    display_name      text NOT NULL,
    tei_xml_id        text,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_date (
    record_id             bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no           integer NOT NULL,
    date_label            text NOT NULL,
    parsed_year           integer,
    normalization_status  text NOT NULL,
    source_attributes     jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_scope (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    scope_type        text,
    label             text NOT NULL,
    from_value        text,
    to_value          text,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_series (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    title_text        text,
    title_type        text,
    scope_type        text,
    scope_label       text,
    source_series     jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_publication_detail (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    detail_type       text NOT NULL CHECK (detail_type IN (
        'pubPlace', 'publisher', 'edition', 'distributor',
        'pageCount', 'prefacePageCount'
    )),
    detail_text       text NOT NULL,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_note (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    note_type         text,
    resp              text,
    note_text         text NOT NULL,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_source_segment (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    segment_subtype   text,
    resp              text,
    segment_text      text NOT NULL,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_external_link (
    record_id         bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    target_uri        text NOT NULL,
    target_kind       text NOT NULL,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (record_id, sequence_no)
);

CREATE TABLE biblio_relation (
    source_record_id  bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    relation_type     text NOT NULL,
    target_record_id  bigint REFERENCES biblio_record(id),
    target_pi_id      bigint,
    target_uri        text,
    target_snapshot   jsonb NOT NULL,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (source_record_id, sequence_no)
);

CREATE TABLE biblio_mentioned_document (
    source_record_id  bigint NOT NULL REFERENCES biblio_record(id),
    sequence_no       integer NOT NULL,
    title_short       text,
    volume_label      text,
    number_label      text,
    ddb_identifier    text,
    tm_identifier     text,
    dclp_identifier   text,
    inventory_number  text,
    source_bibl       jsonb NOT NULL,
    PRIMARY KEY (source_record_id, sequence_no)
);

CREATE TABLE document_bibliography_reference (
    document_id       bigint NOT NULL REFERENCES document(id),
    biblio_record_id  bigint NOT NULL REFERENCES biblio_record(id),
    source            text NOT NULL,
    context_type      text,
    source_path       text,
    source_attributes jsonb NOT NULL,
    PRIMARY KEY (document_id, biblio_record_id, source, source_path)
);
```

Indexes that matter for retrieval:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- Required only if embeddings are stored in PostgreSQL with pgvector.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE INDEX biblio_record_type_idx ON biblio_record (record_type, record_subtype);
CREATE INDEX biblio_record_year_idx ON biblio_record (publication_year);
CREATE INDEX biblio_identifier_lookup_idx ON biblio_identifier (identifier_type, normalized_value);
CREATE INDEX biblio_contributor_name_trgm_idx ON biblio_contributor USING gin (display_name gin_trgm_ops);
CREATE INDEX biblio_title_text_trgm_idx ON biblio_title USING gin (title_text gin_trgm_ops);
CREATE INDEX biblio_relation_target_idx ON biblio_relation (relation_type, target_record_id);
CREATE INDEX biblio_mentioned_ddb_idx ON biblio_mentioned_document (ddb_identifier);
CREATE INDEX biblio_mentioned_tm_idx ON biblio_mentioned_document (tm_identifier);
```

For vector retrieval, build a separate chunk table rather than embedding every child row independently:

```sql
CREATE TABLE rag_biblio_chunk (
    id             bigserial PRIMARY KEY,
    record_id      bigint NOT NULL REFERENCES biblio_record(id),
    chunk_type     text NOT NULL,
    chunk_text     text NOT NULL,
    metadata       jsonb NOT NULL,
    text_search    tsvector,
    embedding      vector
);
```

Suggested chunk types are `citation`, `abstract_note`, `source_segment`, `relation_summary`, and `mentioned_document_summary`. The metadata payload should include `pi_id`, `record_type`, `record_subtype`, `publication_year`, contributor names, title strings, identifier values, relation targets, and mentioned DDbDP/TM/DCLP identifiers.

## Data-quality notes

- Five parsed Biblio IDs are duplicated; use an internal surrogate key and enforce source-path uniqueness until the duplicates are curated.
- Direct dates are raw text and include malformed concatenations and at least one implausible parsed future year. Store normalization status.
- `relatedItem type="mentions"` must not be treated as a failed Biblio pointer. It encodes a different relation class.
- Direct HGV-to-Biblio links are sparse and include four missing Biblio IDs, so document-bibliography linking needs multiple evidence sources.
- Retain raw XML and target snapshots. Nested `relatedItem/bibl` content includes copied titles/authors around protected comments; it is useful for display and audit even when the target Biblio record can be resolved.
