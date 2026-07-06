# Non-numeric LDAB identifiers in DCLP

Checked the DCLP XML corpus with a script that parsed every `DCLP/**/*.xml`
file using Python's `xml.etree.ElementTree` and inspected `idno` elements with
`type="LDAB"`.

## Summary

- Files scanned: 14,842
- XML parse errors: 0
- `idno type="LDAB"` elements found: 14,744
- Files with an LDAB identifier: 14,744
- Files without an LDAB identifier: 98
- Files with more than one LDAB identifier: 0
- Non-numeric LDAB values, after stripping whitespace: 6

All LDAB identifiers found by the script occur at:

```text
TEI/teiHeader/fileDesc/publicationStmt/idno
```

All LDAB identifier elements have only one attribute:

```xml
type="LDAB"
```

## Non-numeric cases

| File | LDAB value | Note |
| --- | --- | --- |
| `DCLP/103/102270.xml` | empty | Element is present as `<idno type="LDAB"/>`. |
| `DCLP/108/108000.xml` | `108000 108349` | Contains two space-separated numeric-looking identifiers. |
| `DCLP/144/143264.xml` | `143264 = 121918` | Contains an equality expression. |
| `DCLP/66/65689.xml` | `6942hec` | Numeric prefix followed by letters. |
| `DCLP/67/66305.xml` | `7555 7349` | Contains two space-separated numeric-looking identifiers. |
| `DCLP/67/66844.xml` | `8094l` | Numeric prefix followed by a letter. |

## Other observed constraints

For the numeric LDAB values in this checkout:

- no leading zeroes were found;
- no leading or trailing whitespace was found;
- numeric values range from `1` to `1000611`;
- values are not globally unique.

Eight LDAB values are reused across multiple files. The most frequent duplicate
is `6308`, which appears in nine files.

## Conclusion

The current DCLP corpus does not support validating LDAB identifiers as strictly
numeric. A practical validation rule would need to allow either missing LDAB
identifiers or known non-numeric legacy forms, unless those records are cleaned
up first.
