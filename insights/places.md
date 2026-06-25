# `placeName` analysis for geographic retrieval

## Executive recommendation

Model HGV places as grouped assertions, not as a single place column on the
document. The useful geographic data is mostly in
`msDesc/history/provenance/p/placeName`, where one provenance statement often
contains a specific place plus a nome and a region. Store the statement group,
store each `placeName` in that group, and attach zero or more authority links to
each mention.

Use Trismegistos IDs as the primary deterministic geographic filter when they
are present. Do not rely on vector embeddings to infer that a document belongs
to Oxyrhynchos, the Arsinoites, or Egypt. Use label and alias search only to
resolve user queries to candidate authority IDs or to retrieve label-only
records.

The minimum useful model is:

- a document has zero or more geographic statements;
- each statement has one or more place mentions;
- each mention has a source label, type, subtype, certainty, sequence, and raw
  TEI attributes;
- each mention can have many authority links, including multiple Trismegistos
  place IDs in one `@ref`;
- the full Trismegistos dump is a local authority table for names, aliases,
  administrative context, date spans, status, and coordinates;
- unlinked labels can produce candidate TM matches, but most should not be
  auto-linked without curation.

This supports RAG questions such as "from Oxyrhynchos", "in the Arsinoites",
"near Karanis", "same provenance as this text", and "places in Egypt with
coordinates" without collapsing TEI structure into a lossy document-level field.

## Scope and method

The profile covers every metadata XML returned by `iterate_hgv_triples` from
`idp.data` revision `a64df90b7a499939fb684945b0b65981524d6345`:

- 66,261 HGV metadata records;
- structured provenance `placeName` elements;
- current settlement values under `msIdentifier/placeName/settlement`;
- the small number of structured `placeName` elements under `origPlace`;
- all Trismegistos, Pleiades, Wikidata, and GeoNames IDs found in `@ref`;
- the local Trismegistos Places dump in `export_geo.csv`.

It is reproducible with:

```console
python scripts/analyze_places.py idp.data --geo-csv export_geo.csv
```

The terms "record" and "document" below refer to one HGV metadata record.
"Place mention" means one `placeName` element. "Statement" means a provenance
paragraph (`provenance/p`) that groups one to four place mentions.

## What is present

### Geographic fields by role

| Field | Records | Occurrences | Role |
|---|---:|---:|---|
| Provenance `placeName` | 55,603 | 122,433 | Main ancient geographic signal |
| Current settlement | 57,741 | 57,741 | Modern holding/current location label |
| Structured origin `placeName` | 6 | 17 | Too rare for primary modeling |
| Plain `origPlace` text | 66,257 | 66,257 | Useful display/search label, mostly unlinked |

Current settlement should not be mixed into ancient provenance retrieval. It
contains modern repository or holding labels such as `unbekannt`, `Qift`,
`London`, `Cairo`, `New York`, and `Toronto`, and has no TM links.

Plain `origPlace` text is broadly available and often human-readable:
`unbekannt` (10,732), `Theben` (5,246), `Oxyrhynchos` (4,172),
`Arsinoites` (3,884), and `Karanis (Arsinoites)` (2,163) are the top values.
However, it is not structured as linked `placeName` in nearly all records. Use it
as a source label and searchable text, not as the authoritative geographic
filter.

### Provenance statements

55,897 provenance events occur in 55,606 records:

| Provenance `@type` | Events |
|---|---:|
| `located` | 55,111 |
| `found` | 418 |
| `composed` | 190 |
| no `@type` | 128 |
| `sent` | 34 |
| `acquired` | 15 |
| `received` | 1 |

The main structured unit is `provenance/p`. There are 57,362 such paragraphs,
and 57,343 contain place names.

| `placeName` elements per paragraph | Paragraphs |
|---:|---:|
| 1 | 14,178 |
| 2 | 21,260 |
| 3 | 21,888 |
| 4 | 17 |

The common shapes show why one document-level place ID is insufficient:

| Statement shape | Paragraphs |
|---|---:|
| `ancient:ref + ancient:nome:ref + ancient:region` | 18,891 |
| `ancient:ref` | 10,766 |
| `ancient:ref + ancient:region` | 8,725 |
| `ancient:nome:ref + ancient:region` | 8,199 |
| `ancient` | 2,340 |

The corpus is mostly ancient provenance:

| `placeName` attribute | Occurrences |
|---|---:|
| `@type="ancient"` | 122,233 |
| `@type="modern"` | 133 |
| `@type="ancientFindspot"` | 2 |
| `@subtype="region"` | 42,576 |
| `@subtype="nome"` | 32,505 |
| `@subtype="province"` | 343 |
| `@cert="low"` | 4,984 |

## Trismegistos linkage

At the document level, TM coverage is strong: 52,168 of the 55,603 records with
provenance `placeName` data (93.82%) have at least one TM-linked provenance
mention.

At the element level, coverage is lower because many statements include an
unlinked region mention such as `Ägypten`.

| Provenance place mentions | Count | Share |
|---|---:|---:|
| All provenance `placeName` elements | 122,433 | 100.00% |
| With any `@ref` | 75,823 | 61.93% |
| With a Trismegistos place ID | 75,181 | 61.41% |
| With a Pleiades place ID | 70,892 | 57.90% |
| Without a Trismegistos place ID | 47,252 | 38.59% |
| With more than one TM ID in the same element | 8,406 | 6.87% |

The multiple-TM case is common enough to require a link table. For example,
`Theben` often carries both TM 2983 and TM 1281 in one `@ref`; the database must
not collapse that to one nullable `trismegistos_id` column.

TM coverage by provenance paragraph:

| Paragraph TM coverage | Paragraphs |
|---|---:|
| Some place names have TM IDs | 41,460 |
| All place names have TM IDs | 12,180 |
| No place names have TM IDs | 3,703 |

Top referenced TM IDs show a mix of cities, villages, districts, and broader
geographic entities:

| TM ID | HGV label(s), summarized | TM standard name | Status | Occurrences |
|---:|---|---|---|---:|
| 332 | mostly `Arsinoites` | Arsinoites | district: nomos, tesh, pagarchia, kurat | 17,772 |
| 2983 | `Theben`, `Theben (Charax)` | Charax | quarter, street: laura | 5,985 |
| 2722 | `Oxyrhynchites` | Oxyrynchites | district: nomos, tesh, pagarchia | 5,921 |
| 1281 | mostly `Theben` | Kerameia - Madou | village | 5,918 |
| 1524 | `Oxyrhynchos` | Oxyrynchos | city: polis, metropolis, civitas | 4,676 |
| 2720 | `Hermopolites` | Hermopolites | district: nomos, tesh, pagarchia | 3,741 |
| 1008 | `Karanis` | Karanis | village: kome, chorion; vicus | 2,316 |
| 2713 | `Herakleopolites` | Herakleopolites | district: nomos, tesh, pagarchia; nesos | 2,037 |
| 816 | `Hermopolis` | Hermopolis | city: polis, metropolis, civitas, oppidum | 1,606 |
| 2287 | `Tebtynis` | Tebtynis | village: kome, chorion, demi | 1,546 |

Authority labels and HGV labels are not identical. TM 332 is canonical
`Arsinoites`, but 219 HGV occurrences using that TM ID have the label `Ägypten`.
This is a good reason to retain both the source label and the resolved authority
row, and to surface mismatches during curation rather than silently replacing
labels.

## What `export_geo.csv` adds

The Trismegistos Places dump contains 64,857 rows. Every one of the 544 distinct
TM IDs referenced by HGV resolves in the dump.

| Dump feature | All dump rows | Referenced TM IDs |
|---|---:|---:|
| Rows / distinct IDs | 64,857 | 544 |
| With begin/end date span | 64,857 | 544 |
| With coordinates | 24,538 (37.83%) | 230 distinct IDs |

At the occurrence level, 40,459 of the 75,181 TM-linked provenance mentions have
at least one referenced TM row with coordinates. This is enough to support map
and radius features for many specific places, but not for every administrative
district or broad region. Keep geospatial filtering optional and explain when a
place lacks coordinates.

The dump materially helps in four ways:

- It validates all existing HGV TM links locally: no referenced TM ID is missing.
- It supplies canonical and variant names (`name_standard`, `name_latin`,
  ethnicon, Greek/Egyptian/Coptic names) for query resolution.
- It supplies administrative context (`country`, `region`, `nomos_code`,
  `provincia`) and place status for filtering and explanations.
- It supplies date spans and coordinates for authority rows, allowing geographic
  and historical context to be indexed outside the TEI files.

The dump does not by itself solve most unlinked HGV labels. Among 47,252
provenance mentions without TM IDs:

| Exact label-to-dump candidate result | Mentions | Share of no-TM mentions |
|---|---:|---:|
| Any exact candidate | 4,365 | 9.24% |
| Single exact candidate | 2,769 | 5.86% |
| Ambiguous exact candidates | 1,596 | 3.38% |

Useful single-candidate labels include `Oasis Magna` (1,827), `Ghoran` (156),
`Koptos` (114), `Dahshur` (100), and `Kreta` (89). Ambiguous labels include
`Apollonopolis` (767), `Berenike` (505), `Chersonesos` (89), and `Arsinoites`
(45). The most common no-candidate label is `Ägypten` (39,564), followed by
German or composite labels such as `Oberägypten`, `Palästina`, `Nubien`,
`Myos Hormos bzw. Koptos`, and `Berenike bzw. Koptos`.

Therefore exact label matching should create candidate links for review or
low-confidence fallback search. It should not overwrite the primary authority
links during ingestion.

## Recommended PostgreSQL schema

This schema is smaller than TEI but preserves the retrieval-relevant structure.
It assumes an existing `document` table and uses PostGIS for coordinates. If
PostGIS is not available, keep `latitude` and `longitude` columns and omit the
geography index.

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE trismegistos_place (
    tm_place_id        bigint PRIMARY KEY,
    country            text,
    region             text,
    nomos_code         text,
    name_latin         text,
    name_standard      text,
    full_name          text,
    status             text,
    ethnicon           text,
    location_note      text,
    unicode_greek      text,
    unicode_egyptian   text,
    unicode_coptic     text,
    begin_year         integer,
    begin_date_format  text,
    end_year           integer,
    end_date_format    text,
    provincia          text,
    latitude           double precision,
    longitude          double precision,
    geog               geography(Point, 4326),
    source_row         jsonb NOT NULL
);

CREATE TABLE trismegistos_place_alias (
    tm_place_id   bigint NOT NULL REFERENCES trismegistos_place(tm_place_id),
    alias         text NOT NULL,
    alias_kind    text NOT NULL, -- standard, latin, ethnicon, greek, egyptian, coptic
    normalized    text NOT NULL,
    source_field  text NOT NULL,
    PRIMARY KEY (tm_place_id, alias_kind, alias, source_field)
);

CREATE TABLE document_place_statement (
    id                         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id                bigint NOT NULL REFERENCES document(id),
    statement_no               smallint NOT NULL,
    scope                      text NOT NULL CHECK (scope IN (
        'provenance', 'origin_text', 'origin_place_name'
    )),

    provenance_event_no        smallint,
    provenance_type            text,
    provenance_when            text,
    paragraph_xml_id           text,
    paragraph_n                text,
    excluded_paragraph_xml_ids text[] NOT NULL DEFAULT '{}',

    source_path                text NOT NULL,
    source_label               text,
    source_attributes          jsonb NOT NULL,
    source_annotations         jsonb NOT NULL DEFAULT '{}',

    UNIQUE (document_id, scope, statement_no)
);

CREATE TABLE document_place_mention (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    statement_id      bigint NOT NULL REFERENCES document_place_statement(id)
                      ON DELETE CASCADE,
    mention_no        smallint NOT NULL,
    label             text NOT NULL,
    normalized_label  text NOT NULL,
    place_type        text,
    place_subtype     text,
    certainty_code    text,
    tei_n             text,
    tei_key           text,
    raw_ref           text,
    source_attributes jsonb NOT NULL,

    UNIQUE (statement_id, mention_no)
);

CREATE TABLE document_place_tm_link (
    mention_id      bigint NOT NULL REFERENCES document_place_mention(id)
                    ON DELETE CASCADE,
    tm_place_id     bigint NOT NULL REFERENCES trismegistos_place(tm_place_id),
    link_no         smallint NOT NULL,
    source_uri      text NOT NULL,
    PRIMARY KEY (mention_id, tm_place_id, link_no)
);

CREATE TABLE document_place_external_link (
    mention_id       bigint NOT NULL REFERENCES document_place_mention(id)
                     ON DELETE CASCADE,
    authority_system text NOT NULL CHECK (authority_system IN (
        'pleiades', 'wikidata', 'geonames', 'other'
    )),
    authority_id     text NOT NULL,
    link_no          smallint NOT NULL,
    source_uri       text NOT NULL,
    PRIMARY KEY (mention_id, authority_system, authority_id, link_no)
);

CREATE TABLE document_place_candidate (
    mention_id       bigint NOT NULL REFERENCES document_place_mention(id)
                     ON DELETE CASCADE,
    tm_place_id      bigint NOT NULL REFERENCES trismegistos_place(tm_place_id),
    match_method     text NOT NULL, -- exact_label, alias_search, manual
    confidence_code  text NOT NULL CHECK (confidence_code IN (
        'single_exact', 'ambiguous_exact', 'curated'
    )),
    curation_status  text NOT NULL DEFAULT 'candidate' CHECK (
        curation_status IN ('candidate', 'accepted', 'rejected')
    ),
    PRIMARY KEY (mention_id, tm_place_id, match_method)
);

CREATE TABLE document_current_settlement (
    document_id       bigint PRIMARY KEY REFERENCES document(id),
    label             text NOT NULL,
    normalized_label  text NOT NULL,
    source_attributes jsonb NOT NULL
);

CREATE INDEX trismegistos_place_alias_trgm
    ON trismegistos_place_alias USING gin (normalized gin_trgm_ops);

CREATE INDEX trismegistos_place_geog_gist
    ON trismegistos_place USING gist (geog);

CREATE INDEX document_place_mention_label_trgm
    ON document_place_mention USING gin (normalized_label gin_trgm_ops);

CREATE INDEX document_place_mention_type_idx
    ON document_place_mention (place_type, place_subtype);

CREATE INDEX document_place_tm_link_place_idx
    ON document_place_tm_link (tm_place_id, mention_id);

CREATE INDEX document_place_statement_document_idx
    ON document_place_statement (document_id);
```

Load `export_geo.csv` into `trismegistos_place` once per dump version. The
coordinate string is `latitude,longitude`; when loading PostGIS, create the
point as `ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography`.

Why this shape:

- `document_place_statement` preserves the grouped provenance paragraph and its
  `@exclude`, `@xml:id`, event type, and source path.
- `document_place_mention` preserves the individual HGV `placeName` label and
  qualifiers such as `@type`, `@subtype`, `@cert`, `@n`, and `@key`.
- `document_place_tm_link` allows many TM IDs per mention and many mentions per
  TM place.
- `document_place_external_link` keeps Pleiades and future authority links
  without forcing them into the TM table.
- `document_place_candidate` makes automated label matching explicit and
  reviewable.
- `document_current_settlement` keeps modern holding/current location separate
  from ancient provenance.

Do not store only `document.trismegistos_place_id`. It would lose the distinction
between specific place, nome, region, multiple alternatives, low-certainty
mentions, and multi-authority references.

## Normalization rules

Apply these rules during ingestion:

| Source encoding | Database action |
|---|---|
| `provenance/p` | Create one `document_place_statement` with `scope='provenance'` |
| `provenance/@type` | Store as `provenance_type`; do not hard-code only `located` |
| `p/@xml:id`, `p/@exclude`, `p/@n` | Preserve on the statement |
| Each direct `p/placeName` | Create one `document_place_mention` in source order |
| `placeName/@ref` | Split whitespace-separated URIs and create link rows |
| TM URI | Insert into `document_place_tm_link`; require matching dump row |
| Pleiades/other URI | Insert into `document_place_external_link` |
| Multiple TM URIs on one mention | Preserve all with `link_no` order |
| `@type`, `@subtype`, `@cert`, `@n`, `@key` | Store as explicit mention columns and in raw JSON |
| `origPlace` text without child `placeName` | Store as `origin_text` statement or source label only |
| `msIdentifier/placeName/settlement` | Store separately as current settlement |

Normalize labels for search by case-folding and whitespace normalization. Avoid
destructive transliteration in the stored source label; HGV uses German labels,
Latin transliterations, modern Arabic forms, and composite strings.

Treat `@key="Aegyptus"` as a source key, not as a TM ID. In the dump, exact
lookup of `Aegyptus` is not sufficient as a unique authority decision because
the value also appears in broader fields such as `provincia`.

## Query behavior for RAG

### Exact authority filtering

When a user query resolves to a TM place ID, use SQL as the deterministic
candidate filter before semantic retrieval:

```sql
SELECT DISTINCT s.document_id
FROM document_place_statement AS s
JOIN document_place_mention AS m
  ON m.statement_id = s.id
JOIN document_place_tm_link AS l
  ON l.mention_id = m.id
WHERE s.scope = 'provenance'
  AND l.tm_place_id = :tm_place_id;
```

This is the right default for "documents from Oxyrhynchos" after the query
resolver maps the name to TM 1524.

### Name-to-place resolution

Resolve user place text against `trismegistos_place_alias` with exact, prefix,
full-text, and trigram search. If the name has multiple plausible TM rows, keep
the ambiguity visible to the retrieval layer. Names such as `Apollonopolis`,
`Berenike`, `Chersonesos`, and `Arsinoites` can be ambiguous in the dump or in
HGV labels.

For linked HGV mentions, prefer TM IDs over labels. For unlinked mentions, use
label search as recall-oriented fallback and mark the match as label-only or
candidate-derived.

### Administrative and spatial expansion

For "in the Arsinoites" or "in the Oxyrhynchites", first match explicit HGV
mentions whose `place_subtype='nome'` and whose TM link is the requested district
ID. Optionally expand through the dump's `region` and `nomos_code`, but treat
that as a separate query mode because the dump provides administrative context,
not a fully explicit parent-child graph for every HGV mention.

For map or distance queries, join through `trismegistos_place.geog`. Because only
230 of the 544 referenced TM IDs have coordinates, spatial retrieval should
return "coordinate-backed matches" and avoid implying that missing-coordinate
places were excluded for historical reasons.

### RAG pipeline

The recommended flow is:

```text
user question
  -> geographic intent parser: place label, scope, relation, strictness
  -> authority resolver over trismegistos_place_alias and external IDs
  -> SQL filter over document_place_tm_link / label fallback / geospatial index
  -> semantic/vector retrieval within candidates
  -> rerank by authority match strength, scope, specificity, and certainty
  -> answer with source label plus resolved authority name and ID
```

Use ranking penalties rather than hard exclusions for `@cert="low"` and
candidate-derived links. Prefer exact TM-linked mentions over exact label-only
matches, and prefer specific places over broad regions when the user asks for a
city or village.

## Final decisions

- Use provenance `p` as the grouped geographic statement.
- Store one row per `placeName` mention inside each statement.
- Use a many-to-many TM link table; 8,406 provenance mentions contain multiple
  TM IDs.
- Load the full Trismegistos dump as a local authority table and alias index.
- Keep current settlement separate from ancient provenance.
- Preserve plain `origPlace` text for display and fallback search, but do not
  treat it as linked authority data.
- Use TM IDs as deterministic RAG filters before vector search.
- Use exact label matching to generate candidates, not automatic authority
  replacements.
- Preserve source labels and raw attributes because HGV labels, TEI `@type`, and
  TM authority rows can disagree.
