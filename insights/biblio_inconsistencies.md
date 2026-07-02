# Biblio identifier inconsistencies

## Scope and method

This note follows up on the duplicate Biblio IDs found in the standalone
`Biblio` XML profile. The current repository checkout does not contain
`./idp.data/Biblio`, so the checks used the sibling local checkout at
`/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio`.

The checks compared three record identifiers:

- the filename stem, for example `95869` in `95869.xml`;
- the root TEI `bibl/@xml:id`, for example `b95869`;
- the direct `<idno type="pi">` value.

Incoming-reference checks scanned local `Biblio` and `HGV_meta_EpiDoc` XML for
`https://papyri.info/biblio/{id}` pointers to the affected IDs, and also looked
for XML-ID style references such as `#b95869`.

## Duplicate `xml:id` groups

Five parsed Biblio IDs occur twice when records are keyed by root `@xml:id`.

| Duplicate ID | Files |
|---|---|
| `95689` | `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/96/95689.xml`; `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/96/95869.xml` |
| `96520` | `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/97/96520.xml`; `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/97/96521.xml` |
| `97533` | `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97533.xml`; `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97733.xml` |
| `97685` | `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97653.xml`; `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97685.xml` |
| `97688` | `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97688.xml`; `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97689.xml` |

## Likely curation edits

Most duplicate groups look like root `@xml:id` typos where the filename and
`idno type="pi"` already agree.

| File | Current internal state | Likely edit |
|---|---|---|
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/96/95869.xml` | `xml:id="b95689"`, `idno type="pi"` is `95869` | Change root `xml:id` to `b95869`. |
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/97/96521.xml` | `xml:id="b96520"`, `idno type="pi"` is `96521` | Change root `xml:id` to `b96521`. |
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97733.xml` | `xml:id="b97533"`, `idno type="pi"` is `97733` | Change root `xml:id` to `b97733`. |
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97689.xml` | `xml:id="b97688"`, `idno type="pi"` is `97689` | Change root `xml:id` to `b97689`. |

`97653.xml` is different. It is not just an `xml:id` typo:

- `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97653.xml` has
  `xml:id="b97685"` and `<idno type="pi">97685</idno>`;
- `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97685.xml` has the
  same title, date, PI identifier, BP identifier, DOI, and container pointer;
- the two files differ only by trailing blank lines in a byte-level diff.

This looks like a duplicate file rather than a record whose identifiers should
be changed to `97653`. It should be investigated before any automatic
filename-matching correction is applied.

## Other identifier mismatches

The broader filename/root-ID/PI consistency scan found three additional records
that are not part of the duplicate `xml:id` groups above but are relevant if the
curation rule is "internal identifiers should match the filename."

| File | Inconsistency |
|---|---|
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/97/96145.xml` | Root `xml:id` is `b2022-0014`, while filename and `idno type="pi"` are `96145`. |
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/97/96643.xml` | Root `xml:id` is `b2023-0085`, while filename and `idno type="pi"` are `96643`. |
| `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/97/96420.xml` | Root `xml:id` matches filename `96420`, but `idno type="pi"` is `96640`, duplicating `96640.xml`. |

The first two may reflect a mistaken `xml:id` value copied from a BP identifier
or another workflow identifier. The `96420.xml` case is a PI identifier problem,
not an `xml:id` problem.

## Incoming reference check

The local pointer scan found no incoming `https://papyri.info/biblio/{id}` links
to the affected duplicate IDs, except one intentional-looking relation:

- `/home/caro/dominic-arbeit/scrapyrus/idp.data/Biblio/98/97689.xml` points to
  `https://papyri.info/biblio/97688` via `relatedItem type="appearsIn"`.

That exception appears correct: `97689` is an article/chapter record that
appears in the edited book record `97688`.

The XML-ID style scan found no `#b...` references to the affected IDs outside
the root `xml:id` attributes themselves.

## Risk assessment

Within the local `idp.data` corpus, there is no evidence that these duplicate
root `xml:id` values currently cause another Biblio or HGV record to reference
the wrong target. The local Biblio graph uses `https://papyri.info/biblio/{id}`
targets for Biblio-to-Biblio relations, and those targets are keyed by numeric
Biblio IDs rather than by TEI `xml:id`.

The practical risk is for importers, APIs, validation jobs, or external systems
that key Biblio records by root `@xml:id`. Such systems would collapse distinct
records like `95689.xml` and `95869.xml` unless the duplicate `xml:id` values
are corrected.

For ingestion into a database, use a surrogate primary key plus `source_path`
uniqueness until these records are curated. Treat filename stem, root
`xml:id`, and `idno type="pi"` as separate source facts with validation status,
not as interchangeable identifiers.
