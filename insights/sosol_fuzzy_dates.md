# SoSOL fuzzy date normalization

This note summarizes how `sosol` normalizes fuzzy date information for HGV and DCLP `<origDate>` metadata. The relevant XML in this repository is under `idp.data/HGV_meta_epidoc` and `idp.data/DCLP`, but the implementation described here is in `sosol`.

## Scope

SoSOL does not implement a standalone temporal indexing model. Its logic is an editor round-trip:

1. Read EpiDoc `<origDate>` into HGV editor fields.
2. Let the editor represent fuzzy dates as century/year/month/day fields plus qualifiers, offsets, precision, and certainty.
3. Convert those fields back into normalized TEI attributes and child elements.

The normalized XML surface is still TEI:

- `@when` for a single normalized date.
- `@notBefore` and `@notAfter` for a bounded fuzzy date or range.
- `@cert` and `@precision` for global certainty/precision.
- child `<offset>`, `<precision>`, and `<certainty>` elements for more targeted metadata.

## Main code paths

The `textDate` configuration maps origin dates to:

`/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate`

It is declared as a multiple field with attributes `xml:id`, `when`, `notBefore`, `notAfter`, `cert`, `precision`, and children `offset`, `precision`, and `certainty`.

References:

- `sosol/config/hgv.yml:195`
- `sosol/config/hgv.yml:203`
- `sosol/config/hgv.yml:206`
- `sosol/config/hgv.yml:209`
- `sosol/config/hgv.yml:212`
- `sosol/config/hgv.yml:215`
- `sosol/config/hgv.yml:219`
- `sosol/config/hgv.yml:229`
- `sosol/config/hgv.yml:239`

The configuration loader reads `config/hgv.yml` and, for DCLP, merges `config/dclp.yml` into the HGV scheme. This means DCLP gets the same HGV origin-date handling while adding DCLP-specific bibliography/work fields.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:23`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:30`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:31`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:33`
- `sosol/app/models/dclp_meta_identifier.rb:1`
- `sosol/app/models/dclp_meta_identifier.rb:12`
- `sosol/app/models/dclp_meta_identifier.rb:13`
- `sosol/app/views/dclp_meta_identifiers/edit.haml:70`
- `sosol/app/views/dclp_meta_identifiers/edit.haml:73`

Existing XML is read with `get_epidoc_attributes_tree`. For `origDate`, SoSOL uses a special case that flattens all text content after stripping embedded tags, rather than relying only on the first text node.

References:

- `sosol/app/models/hgv_meta_identifier.rb:151`
- `sosol/app/models/hgv_meta_identifier.rb:169`

The HGV/DCLP date editor converts the EpiDoc tree into form fields with `HGVDate.epidocToHGV`.

References:

- `sosol/app/views/hgv_meta_identifiers/_date.haml:5`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1240`

On save and on date preview, the controller prunes date parameters and converts each remaining date with `HGVDate.hgvToEpidoc`.

References:

- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:10`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:12`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:119`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:133`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:136`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:142`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:167`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:170`
- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:173`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1511`

## Supported editor fields

The editor exposes two date parts, each with:

- century `c`, `c2`
- year `y`, `y2`
- month `m`, `m2`
- day `d`, `d2`
- century qualifier `cx`, `cx2`
- year qualifier `yx`, `yx2`
- month qualifier `mx`, `mx2`
- offset `offset`, `offset2`
- precision `precision`, `precision2`

There is also global date certainty and an `unknown` checkbox.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1175`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1178`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1180`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1181`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1182`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1183`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:1`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:6`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:10`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:14`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:18`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:21`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:24`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:28`
- `sosol/app/views/hgv_meta_identifiers/_date_form.haml:32`

The legal qualifier options are hard-coded in `HGVDate`:

- month qualifiers: `beginning`, `beginningCirca`, `middle`, `middleCirca`, `end`, `endCirca`
- year qualifiers: `beginning`, `firstHalf`, `firstHalfToMiddle`, `middle`, `middleToSecondHalf`, `secondHalf`, `end`, plus `Circa` variants
- century qualifiers: `beginning`, `beginningToMiddle`, `firstHalf`, `firstHalfToMiddle`, `middle`, `middleToSecondHalf`, `secondHalf`, `middleToEnd`, `end`, plus `Circa` variants
- offsets: `before`, `after`, `beforeUncertain`, `afterUncertain`
- certainty: `low`, `day`, `month`, `year`, `day_month`, `month_year`, `day_year`, `day_month_year`
- precision: only `ca` in the editor

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:747`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:755`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:768`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:789`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:814`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:825`

## Forward conversion: HGV fields to EpiDoc

The core forward converter is `HGVDate.hgvToEpidoc`.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1511`

### Unknown dates

If `date_item[:unknown]` is present, SoSOL writes the element value as `unbekannt` and returns without date attributes.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1517`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1518`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1519`

### Century dates

If `date_item[:c]` is present, SoSOL treats the date as a century or century range. It deletes normal `precision` fields because century precision is represented through qualifiers and child precision nodes.

It then writes:

- `@notBefore = getYearIso(c, cx, :chronMin)`
- `@notAfter = getYearIso(c2, cx2, :chronMax)` if `c2` exists
- otherwise `@notAfter = getYearIso(c, cx, :chronMax)`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1523`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1524`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1525`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1526`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1527`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1528`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1530`

Century endpoint expansion is handled by `getYearIso`.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:845`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:848`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:875`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:893`

Century qualifier endpoint rules:

| Qualifier | CE lower offset | CE upper behavior | Effective CE span |
| --- | ---: | --- | --- |
| none | 0 | full century | 1-100 |
| beginning | 0 | `-75` | 1-25 |
| beginningToMiddle | 0 | `-50` | 1-50 |
| firstHalf | 0 | `-50` | 1-50 |
| firstHalfToMiddle | 25 | `-50` | 26-50 |
| middle | 25 | `-25` | 26-75 |
| middleToSecondHalf | 50 | `-25` | 51-75 |
| secondHalf | 50 | 0 | 51-100 |
| middleToEnd | 25 | 0 | 26-100 |
| end | 75 | 0 | 76-100 |

For BCE centuries, the same logical century parts are mirrored over signed years. For example, tests assert:

- 5th century CE: `0401..0500`
- beginning 5th century CE: `0401..0425`
- middle 5th century CE: `0426..0475`
- end 5th century CE: `0476..0500`
- 5th century BCE: `-0500..-0401`
- beginning 5th century BCE: `-0500..-0476`
- middle 5th century BCE: `-0475..-0426`
- end 5th century BCE: `-0425..-0401`

References:

- `sosol/test/unit/date_test.rb:128`
- `sosol/test/unit/date_test.rb:129`
- `sosol/test/unit/date_test.rb:130`
- `sosol/test/unit/date_test.rb:131`
- `sosol/test/unit/date_test.rb:132`
- `sosol/test/unit/date_test.rb:134`
- `sosol/test/unit/date_test.rb:135`
- `sosol/test/unit/date_test.rb:136`
- `sosol/test/unit/date_test.rb:137`
- `sosol/test/unit/date_test.rb:139`
- `sosol/test/unit/date_test.rb:140`
- `sosol/test/unit/date_test.rb:141`
- `sosol/test/unit/date_test.rb:142`
- `sosol/test/unit/date_test.rb:144`
- `sosol/test/unit/date_test.rb:145`
- `sosol/test/unit/date_test.rb:146`
- `sosol/test/unit/date_test.rb:147`

### Year, month, and day dates

If the date is not a century date, SoSOL builds an ISO-like date string from year, optional month, and optional day:

- years are zero-padded to four digits
- BCE years keep a leading `-`
- months are zero-padded
- days are zero-padded

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1547`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1548`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1549`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1550`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1552`

If there is exactly one non-vague, non-offset date, SoSOL writes `@when`.

If an offset is present:

- `before` or `beforeUncertain` writes the date to `@notAfter`
- `after` or `afterUncertain` writes the date to `@notBefore`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1558`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1559`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1560`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1561`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1563`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1565`

If there is a second date or a year/month qualifier, SoSOL writes a range:

- `@notBefore` from the first date with lower-bound expansion
- `@notAfter` from the second date, or from the first year if only a qualifier expands it, with upper-bound expansion

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1566`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1567`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1569`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1575`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1577`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1580`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1586`

### Year qualifier expansion

`getMonthIso` maps year-level fuzzy qualifiers to month endpoints.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:904`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:908`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:919`

Endpoint rules:

| Qualifier | Lower month | Upper month |
| --- | --- | --- |
| none | none | none |
| beginning | `01` | `03` |
| firstHalf | `01` | `06` |
| firstHalfToMiddle | `04` | `06` |
| middle | `04` | `09` |
| middleToSecondHalf | `07` | `09` |
| secondHalf | `07` | `12` |
| end | `10` | `12` |

Tests cover these in `test_year_qualifier`.

References:

- `sosol/test/unit/date_test.rb:815`

### Month qualifier expansion

`getDayIso` maps month-level fuzzy qualifiers to day endpoints.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:943`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:949`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:961`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:968`

Endpoint rules:

| Qualifier | Lower day | Upper day |
| --- | --- | --- |
| none | none | none |
| beginning | `01` | `10` |
| middle | `11` | `20` |
| end | `21` | calendar month end |

Month end is computed using Gregorian leap-year logic:

- February has 29 days if `year % 4 == 0` and either `year % 100 != 0` or `year % 400 == 0`.
- Months before August alternate odd 31/even 30.
- Months from August onward alternate even 31/odd 30.

Tests cover this in `test_month_qualifier` and `test_leap_year`.

References:

- `sosol/test/unit/date_test.rb:889`
- `sosol/test/unit/date_test.rb:942`

## Precision and circa

SoSOL distinguishes:

- plain `ca.` precision
- vague qualifiers such as beginning/middle/end
- combinations of `ca.` and vague qualifiers

`getPrecision` maps these to internal symbols:

- no precision and no qualifier -> `nil`
- plain `ca` -> `:medium`
- vague qualifier without `ca` -> `:low`
- vague qualifier plus `ca` -> `:lowlow`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1220`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1221`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1222`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1223`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1226`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1229`
- `sosol/test/unit/date_test.rb:8`

For non-century dates:

- if both endpoints have the same precision, or only one normalized date attribute is written, `:low` or `:medium` becomes `@precision="low|medium"`
- `:lowlow` becomes a child `<precision degree="0.1">`
- endpoint-specific precision becomes child `<precision>` with `@match="../@when"`, `../@notBefore`, or `../@notAfter`
- `:medium` endpoint precision is encoded with `degree="0.5"`
- `:lowlow` endpoint precision is encoded with `degree="0.1"`
- `:low` endpoint precision has no degree

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1589`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1590`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1591`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1593`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1595`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1598`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1600`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1602`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1605`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1607`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1609`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1611`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1614`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1615`

For century dates:

- no circa qualifier writes `@precision="low"`
- circa on both endpoints writes one child `<precision degree="0.1">`
- circa only on lower endpoint writes `degree="0.1"` targeting `@notBefore` and `degree="0.3"` targeting `@notAfter`
- circa only on upper endpoint writes `degree="0.3"` targeting `@notBefore` and `degree="0.1"` targeting `@notAfter`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1533`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1536`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1537`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1538`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1539`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1540`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1541`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1542`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1543`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1545`

## Offsets

Offsets are represented both structurally and in the display label.

`getOffsetItem` creates child `<offset>` nodes:

- value `vor`, type `before`
- value `nach`, type `after`
- value `vor (?)`, type `before`
- value `nach (?)`, type `after`
- position `1` or `2` to attach the offset to the first or second date part

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1492`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1495`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1499`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1500`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1620`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1621`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1625`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1626`

Uncertain offsets add targeted child certainty:

`<certainty match="../offset[@type='before|after']">`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1629`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1630`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1632`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1635`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1637`

The model later reorders `<offset>` elements relative to the human-readable date text. It strips `vor`/`nach` from the text and reinserts the `<offset>` element before the corresponding date part.

References:

- `sosol/app/models/hgv_meta_identifier.rb:620`
- `sosol/app/models/hgv_meta_identifier.rb:657`
- `sosol/app/models/hgv_meta_identifier.rb:661`
- `sosol/app/models/hgv_meta_identifier.rb:666`
- `sosol/app/models/hgv_meta_identifier.rb:668`
- `sosol/app/models/hgv_meta_identifier.rb:674`
- `sosol/app/models/hgv_meta_identifier.rb:679`
- `sosol/app/models/hgv_meta_identifier.rb:682`

## Certainty

Global low certainty becomes `@cert="low"`.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1640`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1641`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1642`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1643`

Component uncertainty, such as `day`, `month_year`, or `day_month_year`, is split on `_` and written as child certainty elements targeting date components:

- `../day-from-date(@when)` or `../day-from-date(@notBefore)`
- `../month-from-date(@when)` or `../month-from-date(@notBefore)`
- `../year-from-date(@when)` or `../year-from-date(@notBefore)`

The target uses `@when` when a single `@when` exists; otherwise it targets `@notBefore`. The code comment says plural support would go there, so targeted uncertainty is not separately attached to `@notAfter` in this forward conversion path.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1644`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1645`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1646`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1647`

## Display string

After attributes and children are generated, SoSOL regenerates the human-readable German HGV date string with `HGVFormat.formatDate`.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1652`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1653`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1766`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1812`

Formatting is display-only. It renders examples such as:

- `1884`
- `vor 1884`
- `nach 1884`
- `Aug. 1884`
- `28. Aug. 1884`
- `1884 v.Chr.`
- `Mitte III - Anfang (?) V`
- `ca. vor Ende V`

References:

- `sosol/test/unit/date_test.rb:19`
- `sosol/test/unit/date_test.rb:29`
- `sosol/test/unit/date_test.rb:36`
- `sosol/test/unit/date_test.rb:43`
- `sosol/test/unit/date_test.rb:50`
- `sosol/test/unit/date_test.rb:71`
- `sosol/test/unit/date_test.rb:92`
- `sosol/test/unit/date_test.rb:514`

## Reverse conversion: EpiDoc to HGV fields

`HGVDate.epidocToHGV` converts normalized XML back into editor fields.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1240`

It chooses the first date as:

`@when || @notBefore || @notAfter`

It always treats `@notAfter` as the second date endpoint if present.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1257`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1258`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1260`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1261`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1262`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1265`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1266`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1267`

It reconstructs circa flags from:

- `@precision="medium"`
- child `<precision>` with degree `0.1` or `0.5`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1270`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1271`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1273`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1275`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1277`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1284`

It decides whether a date is vague from:

- `@precision="low"`
- child `<precision>` with no degree
- child `<precision>` with degree `0.1` or `0.3`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1290`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1291`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1292`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1294`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1296`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1299`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1300`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1302`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1306`

If vague, it tries to collapse exact endpoint ranges back to editor qualifiers:

- year-only ranges become century plus `cx` / `cx2`
- month ranges become year qualifiers `yx` / `yx2`
- day ranges become month qualifiers `mx` / `mx2`

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1312`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1315`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1317`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1323`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1334`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1338`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1341`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1344`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1345`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1358`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1361`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1364`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1365`

The reverse lookup tables are:

- `getCentury` at `sosol/app/helpers/hgv_meta_identifier_helper.rb:984`
- `getCenturyQualifier` at `sosol/app/helpers/hgv_meta_identifier_helper.rb:997`
- `getYearQualifier` at `sosol/app/helpers/hgv_meta_identifier_helper.rb:1062`
- `getMonthQualifier` at `sosol/app/helpers/hgv_meta_identifier_helper.rb:1110`

If a qualifier has a circa flag, it appends `Circa` to the qualifier symbol.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1377`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1378`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1381`

Offsets and uncertain offsets are reconstructed from child `<offset>` plus child `<certainty>` targeting that offset.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1397`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1398`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1399`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1400`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1401`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1403`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1407`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1408`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1409`

Certainty is reconstructed from `@cert`, or from child `<certainty>` matches containing day/month/year.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1414`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1416`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1417`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1418`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1419`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1420`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1423`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1424`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1428`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1431`

Finally, duplicate second endpoints are removed when they match the first endpoint.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1436`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1438`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1439`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1440`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:1441`

## `HGVFuzzy`

`HGVFuzzy` is a related helper that turns fuzzy HGV date parts into concrete chronology strings for `:chron`, `:chronMin`, and `:chronMax`.

References:

- `sosol/app/helpers/hgv_meta_identifier_helper.rb:2013`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:2027`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:2057`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:2216`
- `sosol/app/helpers/hgv_meta_identifier_helper.rb:2231`

Its endpoint mappings are similar to `HGVDate`:

- century qualifiers use year modifiers at `sosol/app/helpers/hgv_meta_identifier_helper.rb:2065`
- year qualifiers use month modifiers at `sosol/app/helpers/hgv_meta_identifier_helper.rb:2098`
- month qualifiers use day modifiers at `sosol/app/helpers/hgv_meta_identifier_helper.rb:2143`

Unlike `HGVDate.hgvToEpidoc`, `HGVFuzzy` also defines a central `:chron` point:

- century: roughly 13, 38, 63, or 87 years into the century depending on qualifier
- year: month `02`, `03`, `05`, `06`, `08`, `09`, or `11`
- month: day `04`, `15`, or `26`

Tests cover `HGVFuzzy` heavily.

References:

- `sosol/test/unit/date_test.rb:702`
- `sosol/test/unit/date_test.rb:739`
- `sosol/test/unit/date_test.rb:815`
- `sosol/test/unit/date_test.rb:889`
- `sosol/test/unit/date_test.rb:942`
- `sosol/test/unit/date_test.rb:988`
- `sosol/test/unit/date_test.rb:1004`

I did not find a production call to `HGVFuzzy` outside `hgv_meta_identifier_helper.rb` and `test/unit/date_test.rb`. The active save path for `<origDate>` uses `HGVDate.hgvToEpidoc`.

Reference:

- `sosol/app/controllers/hgv_meta_identifiers_controller.rb:173`

## Practical implications for `idp.data` ingestion

For retrieval/indexing in this project, the SoSOL logic is useful as a description of how many current HGV/DCLP `@when`, `@notBefore`, `@notAfter`, precision, certainty, and offset structures were probably produced.

However, it should not be copied directly as a retrieval model:

- SoSOL is optimized for editor round-tripping and German HGV display labels.
- It collapses and expands dates according to fixed quarter/half/end buckets.
- It encodes circa and vague precision symbolically rather than probabilistically.
- It keeps alternatives as separate `origDate` elements, usually identified by `dateAlternativeX/Y/Z`.
- It does not turn `@precision` or `<certainty>` into widened query intervals beyond the explicit normalized endpoints.

For the retrieval design in `insights/origdate.md`, the direct machine-queryable fields remain the explicit date attributes:

- exact `@when`
- inclusive `@notBefore` / `@notAfter`
- open lower or upper bound where only one exists
- retained precision/certainty/offset metadata for display and explanation
