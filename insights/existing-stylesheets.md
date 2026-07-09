# Existing EpiDoc Stylesheets

This is an inventory of the XSLT transformations in `./Stylesheets` for EpiDoc-style TEI transcriptions such as the files under `./idp.data/DDB_EpiDoc_XML`.

Examples were generated with `saxonche` 13.0.0 from:

- `idp.data/DDB_EpiDoc_XML/p.customs/p.customs.20.xml`
- `idp.data/DDB_EpiDoc_XML/o.deiss/o.deiss.59.xml`

The stylesheets are XSLT 2.0. Most files are not standalone transforms: the `start-*.xsl` files are the runnable entry points, and they include many small TEI element modules.

## Runnable Entry Points

| Entry point | Implemented transformation | Example |
| --- | --- | --- |
| `start-txt.xsl` | EpiDoc TEI to plain-text Leiden-style transcription. It includes the `txt-*` wrappers plus shared `tei*.xsl` Leiden rules. | `p.customs.20` becomes a text transcription with metadata and numbered lines: `AD 113 Tebtynis ... πάρες δ̣ι̣(ὰ) [π]ύ̣[λ(ης) Τεπτ(ύνεως) ...] ... 5\t\tκιθῶνος ὀκτ[ώ] .` |
| `start-edition.xsl` | EpiDoc TEI to HTML. The output method is XML, but the result is an HTML document or HTML fragment depending on `edn-structure`. | Default output begins: `<html><head><title>p.customs.20</title>...<body><h1>p.customs.20</h1>...<div id="edition" lang="grc">...<br id="al5"/><span class="linenumber">5</span>κιθῶνος ὀκτ[ώ] .` |
| `start-fo.xsl` | EpiDoc TEI to an XSL-FO fragment, specifically a `fo:block-container` using the CRETA-oriented FO structure templates. | Output begins: `<fo:block-container ...><fo:block ...>Text</fo:block><fo:block-container id="body-p.customs.20">...<fo:table>...` |
| `start-pdf.xsl` | EpiDoc TEI to a complete XSL-FO document that can be passed to a formatter such as Apache FOP. It does not itself emit a binary PDF. | Output begins: `<fo:root ...><fo:layout-master-set>...<fo:page-sequence master-reference="EpiDoc-master">...<fo:flow flow-name="xsl-region-body">...` |
| `start-odf.xsl` | Intended EpiDoc TEI to OpenDocument content XML (`office:document-content`), using plain-text-style Leiden rendering inside ODF paragraphs. | Intended shape: `<office:document-content ...><office:body><office:text>...<text:p text:style-name="Sammelbuch-Textzeile">...</text:p>`. Current status: this entry point fails to compile under SaxonC because `odf-tpl-linenumberingtab.xsl` has `exclude-result-prefixes="t"` without declaring prefix `t`. |

## Format-Specific Module Families

The modules are grouped by output format and generally implement the same TEI elements for different targets.

| Family | Role | Example behavior |
| --- | --- | --- |
| `txt-*.xsl` | Plain text wrappers for TEI blocks, lines, lists, apparatus, notes, paragraphs, references, spaces, supplied text, and square-bracket cleanup. | `txt-teilb.xsl` renders line breaks as carriage returns and emits the line number every `line-inc` lines, so `<lb n="5"/>` becomes a new line prefixed with `5` and a tab. |
| `htm-*.xsl` | HTML wrappers for the same TEI constructs, usually adding `div`, `span`, `br`, `a`, CSS classes, IDs, and titles. | `htm-teilb.xsl` renders `<lb n="5"/>` as `<br id="al5"/><span class="linenumber">5</span>`. `htm-teinum.xsl` renders `<num value="17">ιζ</num>` as `<span title="number: 17">ιζ</span>`. |
| `fo-*.xsl` | XSL-FO wrappers for page-oriented rendering. These turn text blocks into `fo:block`, `fo:inline`, and `fo:table` structures. | `fo-teiab.xsl` lays an `<ab>` out as a two-column FO table: one column for line numbers and one for the line text. |
| `odf-*.xsl` | ODF helper templates for metadata and line-number tabs. | `odf-tpl-metadata.xsl` emits named metadata sections; `odf-tpl-linenumberingtab.xsl` should emit `<text:tab/>`, but currently has the namespace error noted above. |
| `tei*.xsl` | Shared, format-neutral Leiden logic imported by the output families. | `teiabbrandexpan.xsl`, `teisupplied.xsl`, `teiunclear.xsl`, `teigap.xsl`, `teiaddanddel.xsl`, and related files decide the textual Leiden symbols before the format wrapper serializes them. |
| `tpl-*.xsl`, `*-tpl-*.xsl` | Named templates used by entry points and modules: apparatus generation, square-bracket normalization, metadata, language attributes, CSS/script links, and project-specific structures. | `txt-tpl-sqbrackets.xsl`, `htm-tpl-sqbrackets.xsl`, and `fo-tpl-sqbrackets.xsl` post-process adjacent bracketed restorations so multiple nearby `<supplied>` and `<gap>` nodes print as readable Leiden brackets. |

## Shared TEI-to-Leiden Rules

These examples are the main textual transformations implemented by the shared `tei*.xsl` modules and reused by text, HTML, and FO output.

| Input pattern | Implementing files | Example output |
| --- | --- | --- |
| `<expan>Τεπτ<ex>ύνεως</ex></expan>` | `teiabbrandexpan.xsl` | `Τεπτ(ύνεως)` |
| `<supplied reason="lost">π</supplied>` | `teisupplied.xsl` plus `*-tpl-sqbrackets.xsl` | `[π]` |
| `<unclear>δι</unclear>` | `teiunclear.xsl` | `δ̣ι̣` in interpretive output; diplomatic output uses dotted placeholders instead of the letters. |
| `<choice><reg>παιδικοὺς</reg><orig>πεδικα</orig></choice>` | `teichoice.xsl`, `teiorigandreg.xsl`, apparatus templates | Default text prints `πεδικα`. With `internal-app-style=ddbdp`, an apparatus line is also generated: `3.  l. παιδικοὺς`. |
| `<subst><add place="inline">ἀπὸ</add><del rend="corrected">εκ</del></subst>` | `teiaddanddel.xsl`, apparatus templates | Default text prints `ἀπὸ`; with `internal-app-style=ddbdp`, the text has an apparatus marker and the apparatus includes `1.  corr. ex εκ`. |
| `<gap reason="lost" quantity="1" unit="line"/>` | `teigap.xsl`; wrapped by `txt-teigap.xsl`, `htm-teigap.xsl`, `fo-teigap.xsl` | `o.deiss.59` prints `[1 line missing]`. |
| `<num value="1/4" rend="tick">δ</num>` | `teinum.xsl`; wrapped by `htm-teinum.xsl`, `fo-teinum.xsl` | `δ´` in text output. |
| `<lb n="5"/>` | `teilb.xsl` plus `txt-teilb.xsl`, `htm-teilb.xsl`, `fo-teilb.xsl` | Text emits `5` at the configured interval; HTML emits `<span class="linenumber">5</span>`; FO puts the number in a line-number table column. |
| Plain text nodes in diplomatic edition | `tpl-text.xsl` | Greek transcription text is uppercased, spaces and most punctuation are stripped, and diacritics are removed. For example `κιθῶνος ὀκτ[ώ]` becomes `ΚΙΘΩΝΟΣΟΚΤ[  ̣]`. |

## Parameters That Change Output

Parameters are declared in `global-varsandparams.xsl` and defaulted by `global-parameters.xml`.

| Parameter | Implemented values observed in the stylesheets | Example |
| --- | --- | --- |
| `edition-type` | `interpretive` default, `diplomatic` | `start-txt.xsl` with `edition-type=diplomatic` turns the first line of `p.customs.20` into uppercase diplomatic text with spaces/punctuation removed and restorations reduced to dotted placeholders. |
| `leiden-style` | Many local conventions: `ddbdp`, `dclp`, `dohnicht`, `edh-*`, `ila`, `iospe`, `london`, `panciera`, `petrae`, `rib`, `seg`, `sammelbuch`, `eagletxt`. | With `leiden-style=iospe`, numeric output for `<num value="17">ιζ</num>` in the HTML example is `ιζ´` rather than the default wrapped HTML span. |
| `internal-app-style` | `none` default, plus `ddbdp`, `iospe`, `fullex`, `minex` in HTML/FO; text only generates the `ddbdp` apparatus. | `start-txt.xsl` with `internal-app-style=ddbdp` appends an `Apparatus` section containing correction and regularization notes. |
| `external-app-style` | `default`, `iospe` | Used when processing explicit `div[@type='apparatus']` sections. `htm-teidivapparatus.xsl` and `fo-teidivapparatus.xsl` contain richer bibliography/source handling for apparatus divisions. |
| `line-inc` | Numeric interval, default `5` | Line 5 and 10 are numbered in the examples; other lines get indentation or line-break elements without visible marginal numbers. |
| `verse-lines` | `off` default, `on` | When on, `<lg>` and `<l>` can be numbered as verse lines rather than ordinary epigraphic lines. |
| `edn-structure` | Active in `start-edition.xsl`: `default`, `london`, `ddbdp`, `edak`, `inslib`, `dol`, `iospe`, `sigidoc`, `ecg`, `creta`. | `edn-structure=ddbdp` emits an HTML fragment rooted in `<div>...`; `edn-structure=creta` emits CRETA sections such as `descriptive_lemma`, `bibliography`, `edition`, `apparato`, `traduzione`, and `commento`. |

## Active HTML Structures

`start-edition.xsl` is the only entry point with multiple top-level layout structures. Its active `edn-structure` branches are:

- `default` and `london`: full HTML page using `htm-tpl-structure.xsl`; includes title, CSS link, body output, and license.
- `ddbdp`: an HTML fragment wrapped in `<div>`, useful when the caller supplies the surrounding page.
- `edak`, `inslib`, `dol`: full HTML pages with project-specific metadata sections, dimensions, places, edition, translation, apparatus, commentary, and bibliography handling.
- `iospe` and `sigidoc`: full HTML pages with IOSPE/SigiDoc-style title and body structure.
- `ecg`: ECG-oriented body structure; currently wrapped by an outer `<div>` in the entry point.
- `creta`: CRETA-oriented full HTML structure; currently also wrapped by an outer `<div>` in the entry point.

The directory also contains `htm-tpl-struct-eagle.xsl`, `htm-tpl-struct-edh.xsl`, `htm-tpl-struct-hgv.xsl`, `htm-tpl-struct-igcyr.xsl`, `htm-tpl-struct-rib.xsl`, and `htm-tpl-struct-spes.xsl`. These define named structure templates, but they are not included or selected by the current `start-edition.xsl`; setting those `edn-structure` values falls through to the default output unless a custom entry point includes and calls them.

## Apparatus Output

There are two apparatus paths:

1. Internal apparatus generation from inline TEI such as `choice`, `subst`, `app`, selected `hi`, and selected `del` markup.
2. External apparatus rendering from explicit `div[@type='apparatus']`.

Example with `o.deiss.59` and `internal-app-style=ddbdp`:

```text
(ἀρούρης) 𐅵 ἀπὸ(*) (ἀρουρῶν) η δ´ κλήρου Πια-

Apparatus

1.  corr. ex εκ
6.  l. ἀρταβῶν
6.  l. τεσσάρων
6.  l. ἡμίσους
```

The HTML equivalent creates anchors linking the in-text marker to apparatus entries, for example:

```html
<h2>Apparatus</h2>
<div id="apparatus">
  <a id="to-app-choice01" href="#from-app-choice01">^</a> 3.
  <span title="Scribe wrote πεδικα, for which read παιδικοὺς"> l. παιδικοὺς</span>
</div>
```

## Important Limitations

- Only `start-txt.xsl` emits literal plain text. HTML, FO, PDF-oriented FO, and ODF are XML serializations of non-TEI target formats.
- `start-pdf.xsl` does not produce a PDF file; it produces complete XSL-FO. A separate FO processor such as Apache FOP is still needed.
- `start-fo.xsl` and `start-pdf.xsl` are CRETA-oriented in their top-level structure. They do not expose the same broad `edn-structure` selection as `start-edition.xsl`.
- `start-odf.xsl` is currently non-runnable under SaxonC 13.0.0 because `Stylesheets/odf-tpl-linenumberingtab.xsl` references prefix `t` in `exclude-result-prefixes` without declaring it.
- Several older or project-specific HTML structure modules exist on disk but are not wired into `start-edition.xsl`.
- No direct Markdown, JSON, CSV, or normalized plain diplomatic/interpretive export beyond `start-txt.xsl` is implemented in the current stylesheet set.
