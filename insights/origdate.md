# `origDate` analysis for temporal retrieval

## Executive recommendation

Store one database row per `<origDate>` element, not one date column per papyrus. Normalize each row to an inclusive lower and upper temporal bound while retaining its original label, attributes, annotations, precision, certainty, calendar, and alternative identifier.

For the expected RAG questions, index a half-open integer range of historical years and use it as a deterministic metadata filter before semantic/vector retrieval. Do not embed a date and expect vector similarity to implement chronology.

The minimum useful model is:

- a document has zero or more date assertions;
- each assertion has a lower bound, an upper bound, or both;
- multiple assertions on one document are alternatives, not a single continuous range;
- precision and certainty qualify an assertion but do not replace its bounds;
- the source label and raw TEI data remain available for display and audit.

This model directly supports “2nd century”, “same time”, BCE dates, open-ended dates, and alternate chronologies without reproducing the full TEI schema.

## Scope and method

The profile covers every metadata XML returned by `iterate_hgv_triples` from `idp.data` revision `1fa45b6d755efdc90707816ed8c2c1d9c6609e1a`:

- 66,261 HGV metadata records;
- 69,224 `<origDate>` elements under `msDesc/history/origin`;
- element attributes, visible labels, direct `<certainty>`, `<precision>`, and `<offset>` children;
- lexical form, calendar validity, interval direction, alternatives, and example century queries.

It is reproducible with:

```console
python scripts/analyze_origdate.py idp.data
```

The terms “record” and “document” below refer to one HGV metadata record. A “date assertion” is one `<origDate>` element. This distinction matters because a record can carry several alternative assertions.

The TEI definitions establish the intended semantics:

- `@when` is a normalized date value;
- `@notBefore` is the earliest possible date;
- `@notAfter` is the latest possible date;
- the standard attributes use Gregorian W3C date forms, including `-0056` for 56 BCE, and do not permit year zero.

See the official [TEI `att.datable.w3c` reference](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ref-att.datable.w3c.html) and [TEI `att.datable` reference](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ref-att.datable.html).

## What is present

### Coverage and cardinality

65,342 records (98.61%) have at least one machine-queryable year bound. The remaining 919 records (1.39%) have text-only dates.

| `<origDate>` elements per record | Records | Share |
|---:|---:|---:|
| 1 | 63,772 | 96.24% |
| 2 | 2,018 | 3.05% |
| 3 | 469 | 0.71% |
| 4 | 1 | <0.01% |
| 5 | 1 | <0.01% |

The 2,489 records with multiple elements are the main reason a single `document.date` or `document.date_range` column is insufficient.

### Temporal shapes

| Encoding | Elements | Share | Normalized meaning |
|---|---:|---:|---|
| `@notBefore` + `@notAfter` | 46,913 | 67.77% | Closed inclusive interval |
| `@when` | 19,482 | 28.14% | A value at year, month, or day granularity |
| `@notBefore` only | 1,419 | 2.05% | Lower-bounded, no known upper bound |
| Text only | 919 | 1.33% | Not machine-queryable without interpretation |
| `@notAfter` only | 488 | 0.70% | Upper-bounded, no known lower bound |
| `@when-custom` + `@datingMethod` | 3 | <0.01% | Julian date requiring calendar-aware handling |

No `<origDate>` uses `@from` or `@to`. The concise schema does not need first-class columns for them at present; raw attributes should still be retained for forward compatibility.

### Attribute frequency

| Attribute | Elements | Share | Observed values or role |
|---|---:|---:|---|
| `@notBefore` | 48,332 | 69.82% | Earliest possible date |
| `@notAfter` | 47,401 | 68.47% | Latest possible date |
| `@precision` | 32,826 | 47.42% | `low` 31,570; `medium` 1,256 |
| `@when` | 19,482 | 28.14% | Normalized date value |
| `@xml:id` | 5,427 | 7.84% | `dateAlternativeX`, `Y`, or `Z` |
| `@cert` | 4,257 | 6.15% | Always `low` |
| `@n` | 501 | 0.72% | `1`, `2`, or `3` |
| `@when-custom` | 3 | <0.01% | `0300-02-29` |
| `@datingMethod` | 3 | <0.01% | Always `#julian` |
| `@type` | 1 | <0.01% | `textDate` |

The dominant combinations are:

| Attribute combination | Elements |
|---|---:|
| `notBefore`, `notAfter`, `precision` | 29,948 |
| `when` | 15,120 |
| `notBefore`, `notAfter` | 12,153 |
| `when`, `xml:id` | 2,578 |
| `cert`, `notBefore`, `notAfter`, `precision` | 1,458 |
| `notBefore` | 1,186 |
| `cert`, `notBefore`, `notAfter`, `xml:id` | 1,097 |
| `precision`, `when` | 1,091 |
| `cert`, `notBefore`, `notAfter` | 1,063 |
| no attributes | 915 |
| `notBefore`, `notAfter`, `xml:id` | 869 |
| `notAfter` | 419 |

All other combinations occur fewer than 250 times each. They are mostly permutations involving `@cert`, `@precision`, `@n`, and alternative IDs. This is a good case for explicit normalized columns plus a `source_attributes` JSON/XML field rather than a nullable database column for every rare TEI attribute.

### Granularity and temporal extent

All 115,215 standard date attribute values passed the profiler’s checks for:

- `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` lexical shape;
- no year zero;
- valid month and Gregorian day-of-month;
- the corpus convention for negative/BCE years.

| Attribute | Year values | Month values | Day values | Observed year span |
|---|---:|---:|---:|---|
| `@when` | 2,286 | 84 | 17,112 | 331 BCE–1093 CE |
| `@notBefore` | 43,360 | 548 | 4,424 | 400 BCE–1050 CE |
| `@notAfter` | 43,068 | 507 | 3,826 | 310 BCE–1200 CE |
| `@when-custom` | 0 | 0 | 3 | 300 CE, Julian |

The three custom dates are Julian `0300-02-29`. They are valid in their declared calendar but not a standard Gregorian `@when` value. Year-level retrieval can safely index them as 300 CE; day-level retrieval must convert them with a calendar-aware library while retaining the original value.

The normalized year spans are often broad:

| Width | Elements | Share |
|---|---:|---:|
| 1 year | 23,161 | 33.46% |
| 2–5 years | 6,321 | 9.13% |
| 6–25 years | 5,727 | 8.27% |
| 26–50 years | 7,618 | 11.00% |
| 51–100 years | 12,553 | 18.13% |
| More than 100 years | 11,016 | 15.91% |
| Open or invalid range | 1,909 | 2.76% |
| Text only | 919 | 1.33% |

More than one third of assertions span at least 51 years. Consequently, overlap alone is suitable for high-recall candidate generation but not for final ranking: a 300-year interval should not automatically rank alongside a precise date merely because both overlap the same century.

### Precision, certainty, and inline annotations

Precision and certainty describe different things:

- `@cert="low"` says the assertion is uncertain. It occurs on 4,257 elements in 3,551 records.
- `@precision="low"` occurs on 31,570 elements, almost entirely closed ranges (31,564). It usually accompanies coarse periods such as centuries or century portions.
- `@precision="medium"` occurs on 1,256 elements, mostly `@when` values (1,214) whose labels say “ca.”.

Do not convert these symbolic values into invented probabilities or fixed numbers of years. They are useful as ranking and display qualifiers; the explicit bounds remain the temporal filter. TEI defines `@cert` as the degree of certainty associated with an assertion and `<precision>` as accuracy/precision metadata; neither definition supplies a universal conversion to a date interval. See [TEI responsibility/certainty attributes](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ref-att.global.responsibility.html) and [TEI `<precision>`](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ref-precision.html).

8,300 records (12.53%) contain direct annotation children inside `<origDate>`:

| Child | Elements | Records | Meaning in this corpus |
|---|---:|---:|---|
| `<certainty>` | 5,691 | 3,478 | Points to an uncertain year/month/day or offset using `@match` |
| `<precision>` | 3,394 | 3,311 | Qualifies a bound, mostly with `@degree="0.5"` |
| `<offset>` | 2,757 | 2,607 | Textual “after” or “before” qualifier |

Observed details include:

- `<offset type="after">`: 1,798; `<offset type="before">`: 959;
- offset labels: `nach` 1,627, `vor` 559, `vor (?)` 400, `nach (?)` 171;
- `<precision @degree>`: `0.5` 3,128, `0.1` 205, `0.3` 22;
- precision targets `@notBefore` 3,154 times and `@notAfter` 71 times;
- certainty targets year, month, day, or offset components rather than defining another interval.

The corpus uses the older TEI `<precision @degree>` form, where degree ranges from zero to one; the [archived TEI documentation for that form](https://www.tei-c.org/Vault/P5/2.2.0/doc/tei-p5-doc/en/html/ref-precision.html) describes it as degree of precision. It still does not define a transformation such as “0.5 means ±50 years”. Preserve these children in structured JSON/XML and expose them in explanations, but do not make them part of the core range calculation.

### Alternatives

2,489 records (3.76%) have multiple `<origDate>` assertions:

- 2,475 give every assertion an `@xml:id`;
- 2 identify only some assertions;
- 12 have no `@xml:id` on the assertions;
- only 501 elements use `@n`, so it is not a reliable universal sequence;
- 8 records repeat identical raw date attributes across alternatives;
- 176 records have alternatives that collapse to the same year interval, often because their month or day differs.

Store every alternative as its own row and assign an ingestion-order `assertion_no`. Retain `@xml:id` as `tei_xml_id`, but do not rely on it as the primary key. Never replace alternatives with their convex hull: alternatives at 155 and 210 CE do not imply that the document may date to every year between 155 and 210.

### Labels and records without bounds

There are 25,491 distinct visible labels. Labels are useful for display—examples include `II`, `1. Hälfte VII`, `ca. 350 - 370`, and fully written German dates—but they are not a stable query representation.

Of the 919 text-only records:

| Label | Records |
|---|---:|
| `unbekannt` | 837 |
| Empty | 40 |
| `unbestimmbar` | 37 |
| Other | 5 |

Thus 914 of 919 text-only records contain no recoverable date. Parsing labels would add at most five candidates without manual correction, so it should be an offline curation task rather than query-time behavior. Note also that 909 labels are empty across the entire corpus while their attributes may still be perfectly queryable; label presence must not control indexing.

### Data-quality exceptions

Two closed ranges are reversed:

- HGV 19007: `notBefore="0554"`, `notAfter="0545"`;
- HGV 957826: `notBefore="0408"`, `notAfter="0407"`.

Both records also have other valid alternatives. Mark these two assertions `invalid_range` and exclude them from temporal filtering until curated. Do not silently swap their endpoints: the source may intend alternatives rather than a typographical reversal.

No other lexical, year-zero, month, day, or Gregorian-calendar errors were found in standard date attributes.

## Recommended concise schema

The following PostgreSQL-oriented schema is deliberately smaller than TEI while preserving everything needed for retrieval and audit. Equivalent scalar fields can be used in another SQL database or a vector database’s metadata payload.

```sql
CREATE FUNCTION historical_year_ordinal(y integer)
RETURNS integer
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    -- There is no year zero: 2 BCE=-2, 1 BCE=-1, 1 CE=0, 2 CE=1.
    SELECT CASE WHEN y < 0 THEN y ELSE y - 1 END
$$;

CREATE TABLE document_date (
    document_id          bigint   NOT NULL REFERENCES document(id),
    assertion_no         smallint NOT NULL,
    tei_xml_id           text,

    mode                 text     NOT NULL CHECK (mode IN (
        'when', 'closed_range', 'not_before', 'not_after',
        'custom_when', 'text_only'
    )),
    label                text,

    lower_year           integer,
    lower_month          smallint,
    lower_day            smallint,
    upper_year           integer,
    upper_month          smallint,
    upper_day            smallint,

    calendar_code        text NOT NULL,  -- gregorian, julian, unknown
    precision_code       text,           -- low, medium, or future TEI value
    certainty_code       text,           -- low, or future TEI value
    normalization_status text NOT NULL CHECK (normalization_status IN (
        'ok', 'text_only', 'invalid_range', 'unsupported'
    )),

    -- Half-open range over contiguous historical-year ordinals.
    year_ordinal_span int4range GENERATED ALWAYS AS (
        CASE WHEN normalization_status = 'ok' THEN
            int4range(
                CASE WHEN lower_year IS NULL THEN NULL
                     ELSE historical_year_ordinal(lower_year) END,
                CASE WHEN upper_year IS NULL THEN NULL
                     ELSE historical_year_ordinal(upper_year) + 1 END,
                '[)'
            )
        END
    ) STORED,

    source_attributes    jsonb NOT NULL,
    source_annotations   jsonb NOT NULL,

    PRIMARY KEY (document_id, assertion_no),
    CHECK (lower_year IS NULL OR lower_year <> 0),
    CHECK (upper_year IS NULL OR upper_year <> 0),
    CHECK (lower_month IS NULL OR lower_month BETWEEN 1 AND 12),
    CHECK (upper_month IS NULL OR upper_month BETWEEN 1 AND 12),
    CHECK (lower_day IS NULL OR lower_day BETWEEN 1 AND 31),
    CHECK (upper_day IS NULL OR upper_day BETWEEN 1 AND 31),
    CHECK (
        normalization_status <> 'ok'
        OR lower_year IS NOT NULL
        OR upper_year IS NOT NULL
    ),
    CHECK (
        normalization_status <> 'ok'
        OR lower_year IS NULL
        OR upper_year IS NULL
        OR historical_year_ordinal(lower_year)
           <= historical_year_ordinal(upper_year)
    )
);

CREATE INDEX document_date_year_gist
    ON document_date USING gist (year_ordinal_span);

CREATE INDEX document_date_document_idx
    ON document_date (document_id);
```

The generated `year_ordinal_span` is populated only when `normalization_status = 'ok'`:

```text
lower endpoint = ordinal(lower_year), or unbounded
upper endpoint = ordinal(upper_year) + 1, or unbounded
range bounds   = [lower, upper)
```

Using ordinals makes 1 BCE adjacent to 1 CE and avoids a fictitious year zero in distance calculations. Keep the signed historical `lower_year` and `upper_year` columns for display and API responses.

Why retain both components and a year range:

- `year_ordinal_span` makes century overlap and nearest-time filtering fast;
- year/month/day components preserve the source granularity and allow later day-level indexing;
- native SQL `DATE` handling of BCE dates and custom calendars varies by database;
- raw attributes and annotations preserve uncommon TEI details without expanding the core schema.

Do not add a document-level union range. A union represented as one minimum-to-maximum range creates false dates between alternatives. If a cached document summary becomes necessary, use a multirange or an array of assertion ranges.

## Normalization rules

Apply these rules during ingestion, not during a user query:

| TEI encoding | Database bounds | Mode |
|---|---|---|
| `when="YYYY"` | Same lower/upper year; month/day null | `when` |
| `when="YYYY-MM"` | Same lower/upper year and month; day null | `when` |
| `when="YYYY-MM-DD"` | Same lower/upper components | `when` |
| `notBefore=A`, `notAfter=B` | Lower from A, upper from B, both inclusive | `closed_range` |
| `notBefore=A` | Lower from A, unbounded upper | `not_before` |
| `notAfter=B` | Unbounded lower, upper from B | `not_after` |
| `when-custom`, `datingMethod` | Parsed components plus declared calendar | `custom_when` |
| No machine date | Null bounds and null range | `text_only` |

For year-level indexing, any date within a year maps to that year’s ordinal bucket. For future day-level retrieval:

- expand a year-granularity lower bound to January 1 and an upper bound to December 31;
- expand a month-granularity lower bound to its first day and an upper bound to its calendar-aware last day;
- convert custom calendars to a common day ordinal while retaining the original calendar and value;
- never infer missing bounds from a label when normalized attributes are present.

Preserve `precision_code` and `certainty_code` as qualifiers. Do not widen `@when="0150" precision="medium"` to an arbitrary interval during ingestion. If an application wants “circa” tolerance, make that a documented query policy so it can be changed and tested.

## Query behavior for RAG

### Century parsing

Use conventional historical centuries with no year zero:

- 2nd century CE = 101 through 200 CE;
- 2nd century BCE = 200 through 101 BCE, represented as signed years -200 through -101.

Convert those endpoints with `historical_year_ordinal` and construct a half-open query range. For example:

```sql
-- 2nd century CE: historical years 101..200 inclusive
SELECT int4range(
    historical_year_ordinal(101),
    historical_year_ordinal(200) + 1,
    '[)'
);

-- 2nd century BCE: historical years -200..-101 inclusive
SELECT int4range(
    historical_year_ordinal(-200),
    historical_year_ordinal(-101) + 1,
    '[)'
);
```

### Recall-oriented “possibly from this period”

Return a document when any valid alternative overlaps the requested period:

```sql
SELECT DISTINCT dd.document_id
FROM document_date AS dd
WHERE dd.normalization_status = 'ok'
  AND dd.year_ordinal_span && :query_span;
```

This should be the default RAG candidate filter because it does not discard uncertain or broad dates. The answer should describe broad matches as “possibly within/overlapping the period”, not as exact dates.

On this corpus, overlap returns:

| Query | Documents with any overlapping alternative |
|---|---:|
| 2nd century CE | 20,121 |
| 2nd century BCE | 4,562 |

### Strict “dated wholly within this period”

Require one assertion to be fully contained:

```sql
SELECT DISTINCT dd.document_id
FROM document_date AS dd
WHERE dd.normalization_status = 'ok'
  AND dd.year_ordinal_span <@ :query_span;
```

This returns 13,495 documents for the 2nd century CE and 3,296 for the 2nd century BCE. Requiring every alternative to be contained is stricter still: 13,185 and 3,161 documents respectively.

Expose the difference between “overlaps”, “has an alternative fully within”, and “all alternatives are within” in the retrieval API. A language model should select a mode explicitly rather than quietly changing temporal semantics.

### “Same time” retrieval

For “show me papyri from the same time as document X”:

1. Load every valid assertion range for X.
2. Retrieve candidates that overlap any assertion; do not merge alternatives into one span.
3. If overlap produces too few results, widen the search by a configured number of years or order non-overlapping candidates by interval gap.
4. Prefer narrower candidate ranges when temporal distance is equal.
5. Apply certainty and precision as transparent ranking penalties, not hard exclusions.
6. Run semantic/vector retrieval within the temporal candidate set, then combine temporal and semantic ranks.

A useful deterministic temporal ordering is:

1. overlapping before non-overlapping;
2. smaller interval gap;
3. larger fraction of the candidate interval inside the query;
4. narrower candidate interval;
5. stronger precision/certainty metadata.

Open-ended intervals can participate in overlap filtering but have no stable midpoint or finite width. Rank them below bounded intervals unless the user explicitly asks for “after” or “before” a date.

### RAG pipeline

The recommended flow is:

```text
user question
  -> temporal intent parser: era, lower year, upper year, query mode
  -> indexed SQL/range filter over document_date
  -> semantic/vector retrieval within candidates
  -> temporal reranking and explanation
  -> answer with source label and normalized interval
```

The temporal parser should produce a validated structured object, for example:

```json
{
  "lower_year": 101,
  "upper_year": 200,
  "era": "CE",
  "mode": "overlap"
}
```

The database layer—not the language model—should turn that object into range predicates. This makes BCE handling, century boundaries, alternatives, and open bounds deterministic and testable.

## Final decisions

- Use a child table with one row per `<origDate>` assertion.
- Use signed historical years in the API and a no-year-zero ordinal range for indexing.
- Preserve year/month/day granularity; start with a year-range GiST index.
- Treat alternatives as separate rows and query them with `EXISTS`/`DISTINCT` semantics.
- Use overlap for recall, containment for strict queries, and interval distance for “same time”.
- Preserve but do not numerically reinterpret TEI precision/certainty annotations.
- Keep labels and raw TEI-derived JSON for display, provenance, and future migration.
- Quarantine the two reversed ranges; leave 919 text-only records unindexed temporally unless curated.
- Apply temporal filtering before vector retrieval and explain the match mode in generated answers.
