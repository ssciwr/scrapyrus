# Used to scan every HGV metadata XML returned by `iterate_hgv_triples` for
# `idp.data` and generate `metadata.md` with linkage, element-path, attribute,
# value, and cardinality frequencies for database-schema design.

"""Inventory the HGV metadata TEI XML returned for every HGV record.

The report is intended to inform a smaller, database-oriented schema.  It
counts XML files, element paths, attributes, controlled values, and per-file
cardinalities for the metadata documents returned by
:func:`scrapyrus.hgv.iterate_hgv_triples`. It also counts links to associated
transcription and translation documents without profiling their contents.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Iterable
from xml.etree import ElementTree

from scrapyrus.hgv import iterate_hgv_triples
from tqdm import tqdm


XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
VALUE_LIMIT = 10_000
PROFILE_ATTRIBUTE_TAGS = {
    "bibl",
    "biblScope",
    "div",
    "idno",
    "keywords",
    "language",
    "placeName",
    "provenance",
}
PROFILE_TEXT_TAGS = {"material", "origPlace", "settlement", "term"}


def local_name(name: str) -> str:
    """Return a readable local name for an element or attribute QName."""

    if name.startswith(f"{{{XML_NAMESPACE}}}"):
        return f"xml:{name.rpartition('}')[2]}"
    return name.rpartition("}")[2]


def normalized_text(element: ElementTree.Element) -> str:
    """Return normalized text from a leaf element."""

    return " ".join((element.text or "").split())


def markdown_code(value: str, limit: int = 90) -> str:
    """Render a compact value safely in a Markdown table."""

    value = " ".join(value.split())
    if len(value) > limit:
        value = f"{value[: limit - 1]}…"
    value = value.replace("|", "\\|").replace("`", "\N{MODIFIER LETTER GRAVE ACCENT}")
    return f"`{value}`"


@dataclass
class Frequency:
    """Occurrence and per-document cardinality of an XML construct."""

    documents: int = 0
    occurrences: int = 0
    minimum: int = 0
    maximum: int = 0

    def add_document(self, count: int) -> None:
        if count <= 0:
            return
        self.documents += 1
        self.occurrences += count
        self.minimum = count if self.documents == 1 else min(self.minimum, count)
        self.maximum = max(self.maximum, count)


@dataclass
class ValueDistribution:
    """Frequency of values, with a memory bound for free-text fields."""

    occurrences: Counter[str] = field(default_factory=Counter)
    documents: Counter[str] = field(default_factory=Counter)
    truncated: bool = False

    def add_document(self, values: Counter[str]) -> None:
        for value, count in values.items():
            if value in self.occurrences or len(self.occurrences) < VALUE_LIMIT:
                self.occurrences[value] += count
                self.documents[value] += 1
            else:
                self.truncated = True


@dataclass
class ValuedFrequency:
    frequency: Frequency = field(default_factory=Frequency)
    values: ValueDistribution = field(default_factory=ValueDistribution)

    def add_document(self, values: Counter[str]) -> None:
        self.frequency.add_document(sum(values.values()))
        self.values.add_document(values)


@dataclass
class XmlInventory:
    """Aggregates structural statistics for one class of TEI document."""

    files: int = 0
    parse_errors: list[tuple[Path, str]] = field(default_factory=list)
    paths: defaultdict[str, Frequency] = field(
        default_factory=lambda: defaultdict(Frequency)
    )
    tags: defaultdict[str, Frequency] = field(
        default_factory=lambda: defaultdict(Frequency)
    )
    path_attributes: defaultdict[tuple[str, str], ValuedFrequency] = field(
        default_factory=lambda: defaultdict(ValuedFrequency)
    )
    tag_attributes: defaultdict[tuple[str, str], ValuedFrequency] = field(
        default_factory=lambda: defaultdict(ValuedFrequency)
    )
    tag_text: defaultdict[str, ValuedFrequency] = field(
        default_factory=lambda: defaultdict(ValuedFrequency)
    )
    attribute_sets: defaultdict[str, Counter[tuple[str, ...]]] = field(
        default_factory=lambda: defaultdict(Counter)
    )

    def add(self, path: Path) -> None:
        try:
            root = ElementTree.parse(path).getroot()
        except (ElementTree.ParseError, OSError) as error:
            self.parse_errors.append((path, str(error)))
            return

        self.files += 1
        path_counts: Counter[str] = Counter()
        tag_counts: Counter[str] = Counter()
        path_attribute_values: defaultdict[tuple[str, str], Counter[str]] = defaultdict(
            Counter
        )
        tag_attribute_values: defaultdict[tuple[str, str], Counter[str]] = defaultdict(
            Counter
        )
        tag_text_values: defaultdict[str, Counter[str]] = defaultdict(Counter)
        attribute_sets: Counter[tuple[str, ...]] = Counter()

        def visit(element: ElementTree.Element, ancestors: tuple[str, ...]) -> None:
            tag = local_name(element.tag)
            element_path = (*ancestors, tag)
            rendered_path = "/" + "/".join(element_path)

            path_counts[rendered_path] += 1
            tag_counts[tag] += 1

            if tag == "origDate":
                attributes = tuple(sorted(local_name(name) for name in element.attrib))
                attribute_sets[attributes] += 1
            for raw_name, value in element.attrib.items():
                name = local_name(raw_name)
                path_attribute_values[(rendered_path, name)][value] += 1
                if tag in PROFILE_ATTRIBUTE_TAGS:
                    tag_attribute_values[(tag, name)][value] += 1

            if tag in PROFILE_TEXT_TAGS and not list(element):
                text = normalized_text(element)
                if text:
                    tag_text_values[tag][text] += 1

            for child in element:
                visit(child, element_path)

        visit(root, ())

        for key, count in path_counts.items():
            self.paths[key].add_document(count)
        for key, count in tag_counts.items():
            self.tags[key].add_document(count)
        for key, values in path_attribute_values.items():
            self.path_attributes[key].add_document(values)
        for key, values in tag_attribute_values.items():
            self.tag_attributes[key].add_document(values)
        for key, values in tag_text_values.items():
            self.tag_text[key].add_document(values)
        self.attribute_sets["origDate"].update(attribute_sets)


def percentage(count: int, total: int) -> str:
    return f"{100 * count / total:.2f}%" if total else "n/a"


def cardinality(frequency: Frequency) -> str:
    if frequency.minimum == frequency.maximum:
        return str(frequency.maximum)
    return f"{frequency.minimum}–{frequency.maximum}"


def frequency_row(label: str, frequency: Frequency, total: int) -> str:
    return (
        f"| {label} | {frequency.documents:,} | "
        f"{percentage(frequency.documents, total)} | {frequency.occurrences:,} | "
        f"{cardinality(frequency)} |"
    )


def top_values(distribution: ValueDistribution, limit: int = 12) -> str:
    values = sorted(
        distribution.occurrences.items(), key=lambda item: (-item[1], item[0])
    )
    shown = ", ".join(
        f"{markdown_code(value)} ({count:,})" for value, count in values[:limit]
    )
    distinct = f">{VALUE_LIMIT:,}" if distribution.truncated else f"{len(values):,}"
    if not shown:
        return f"{distinct} distinct"
    return f"{distinct} distinct; {shown}"


def value_table(
    title: str,
    profile: ValuedFrequency | None,
    total: int,
    *,
    limit: int = 30,
) -> list[str]:
    lines = [f"### {title}", ""]
    if profile is None:
        return [*lines, "Not present.", ""]

    lines.extend(
        [
            "| Value | XML files | Coverage | Occurrences |",
            "|---|---:|---:|---:|",
        ]
    )
    values = sorted(
        profile.values.occurrences.items(), key=lambda item: (-item[1], item[0])
    )
    for value, count in values[:limit]:
        documents = profile.values.documents[value]
        lines.append(
            f"| {markdown_code(value)} | {documents:,} | "
            f"{percentage(documents, total)} | {count:,} |"
        )
    if len(values) > limit or profile.values.truncated:
        distinct = (
            f">{VALUE_LIMIT:,}" if profile.values.truncated else f"{len(values):,}"
        )
        lines.append(f"| … |  | {distinct} distinct values |  |")
    lines.append("")
    return lines


def element_path_table(inventory: XmlInventory) -> list[str]:
    lines = [
        "| Element path | XML files | Coverage | Occurrences | Per present file |",
        "|---|---:|---:|---:|---:|",
    ]
    for path, frequency in sorted(inventory.paths.items()):
        lines.append(
            frequency_row(markdown_code(path, 130), frequency, inventory.files)
        )
    lines.append("")
    return lines


def path_attribute_table(inventory: XmlInventory) -> list[str]:
    lines = [
        "| Element path | Attribute | XML files | Coverage | Occurrences | Values |",
        "|---|---|---:|---:|---:|---|",
    ]
    for (path, attribute), profile in sorted(inventory.path_attributes.items()):
        frequency = profile.frequency
        lines.append(
            f"| {markdown_code(path, 110)} | {markdown_code('@' + attribute)} | "
            f"{frequency.documents:,} | {percentage(frequency.documents, inventory.files)} | "
            f"{frequency.occurrences:,} | {top_values(profile.values)} |"
        )
    lines.append("")
    return lines


def attribute_set_table(inventory: XmlInventory, tag: str) -> list[str]:
    counts = inventory.attribute_sets.get(tag, Counter())
    lines = [
        f"### `{tag}` attribute combinations",
        "",
        "| Attributes present together | Elements |",
        "|---|---:|",
    ]
    for attributes, count in sorted(
        counts.items(), key=lambda item: (-item[1], item[0])
    ):
        rendered = ", ".join(markdown_code(f"@{name}") for name in attributes)
        rendered = rendered or "*(none)*"
        lines.append(f"| {rendered} | {count:,} |")
    lines.append("")
    return lines


def git_revision(directory: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def selected_field_table(inventory: XmlInventory) -> list[str]:
    """Return coverage for database-relevant HGV metadata paths."""

    fields = [
        ("Document title", "/TEI/teiHeader/fileDesc/titleStmt/title"),
        ("Publication identifier", "/TEI/teiHeader/fileDesc/publicationStmt/idno"),
        (
            "Holding institution",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/institution",
        ),
        (
            "Collection",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/collection",
        ),
        (
            "Current settlement",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/placeName/settlement",
        ),
        (
            "Inventory identifier",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/msIdentifier/idno",
        ),
        (
            "Material",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/physDesc/objectDesc/supportDesc/support/material",
        ),
        (
            "Origin place",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origPlace",
        ),
        (
            "Origin date",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/origin/origDate",
        ),
        (
            "Provenance event",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance",
        ),
        (
            "Provenance place",
            "/TEI/teiHeader/fileDesc/sourceDesc/msDesc/history/provenance/p/placeName",
        ),
        ("Keyword", "/TEI/teiHeader/profileDesc/textClass/keywords/term"),
        ("Revision event", "/TEI/teiHeader/revisionDesc/change"),
        ("Typed body division", "/TEI/text/body/div"),
        ("Division paragraph", "/TEI/text/body/div/p"),
        ("Structured bibliography entry", "/TEI/text/body/div/listBibl/bibl"),
        ("Inline illustration reference", "/TEI/text/body/div/p/bibl"),
        ("Image link", "/TEI/text/body/div/p/figure/graphic"),
        ("Mentioned date", "/TEI/text/body/div/list/item/date"),
    ]
    lines = [
        "| Candidate field | TEI path | XML files | Coverage | Occurrences | Per present file |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for label, path in fields:
        frequency = inventory.paths.get(path, Frequency())
        lines.append(
            f"| {label} | {markdown_code(path, 100)} | {frequency.documents:,} | "
            f"{percentage(frequency.documents, inventory.files)} | "
            f"{frequency.occurrences:,} | {cardinality(frequency)} |"
        )
    lines.append("")
    return lines


def render_report(
    idp_data: Path,
    triples: int,
    transcription_links: int,
    translation_links: int,
    unique_transcriptions: int,
    unique_translations: int,
    metadata: XmlInventory,
) -> str:
    revision = git_revision(idp_data)
    lines = [
        "# HGV TEI metadata inventory",
        "",
        "This report inventories the HGV metadata XML for every record returned by "
        "`iterate_hgv_triples`. Associated transcription and translation files are counted "
        "for linkage coverage but their contents are outside this metadata profile. It is a "
        "data profile for designing a practical database schema, not a replacement for the "
        "EpiDoc/TEI schema.",
        "",
        "## Scope and method",
        "",
        f"- Corpus: `idp.data` at Git revision `{revision}`.",
        "- Generator: `python scripts/aggregate_hgv_metadata.py idp.data metadata.md`.",
        "- HGV metadata XML files are counted once; associated XML paths are deduplicated for linkage counts.",
        "- “Coverage” is the percentage of successfully parsed HGV metadata XML files.",
        "- “Per present file” is the minimum–maximum cardinality, excluding files where the construct is absent.",
        "- Element presence is structural; empty elements count as present. Attribute value counts are exact up to "
        f"{VALUE_LIMIT:,} distinct values per field and are marked as truncated beyond that limit.",
        "- Text-value profiles are limited to selected controlled or schema-relevant fields; all element and attribute "
        "presence counts cover the complete metadata XML tree, including its body.",
        "",
        "## Corpus linkage",
        "",
        "| Item | Count | HGV record coverage |",
        "|---|---:|---:|",
        f"| HGV records / metadata XML files | {triples:,} | 100.00% |",
        f"| Records linked to a transcription | {transcription_links:,} | {percentage(transcription_links, triples)} |",
        f"| Unique linked transcription XML files | {unique_transcriptions:,} | {percentage(unique_transcriptions, triples)} |",
        f"| Records linked to a translation | {translation_links:,} | {percentage(translation_links, triples)} |",
        f"| Unique linked translation XML files | {unique_translations:,} | {percentage(unique_translations, triples)} |",
        "",
    ]

    errors = metadata.parse_errors
    if errors:
        lines.extend(
            [
                "### Parse failures",
                "",
                f"{len(errors):,} XML files could not be parsed and are excluded from coverage denominators:",
                "",
            ]
        )
        lines.extend(f"- `{path}`: {error}" for path, error in errors)
        lines.append("")

    lines.extend(
        [
            "## Database-design takeaways",
            "",
            "- Keep the HGV record, transcription, and translation as separate entities. Their coverage differs, and the "
            "same transcription can be linked from multiple HGV records.",
            "- Model identifiers, provenance places, keywords, bibliography entries, languages, revision events, and "
            "typed text divisions as child tables: they are repeatable and carry type/subtype or authority attributes.",
            "- Preserve normalized core columns alongside the source XML. TEI permits mixed content, nested bibliography, "
            "open-ended attributes, and uncommon structures that a compact relational schema will otherwise lose.",
            "- Treat dates as an interval-capable value object. The `origDate` inventory below shows exact dates, bounds, "
            "ranges, and human-readable labels in the corpus.",
            "- Treat place labels and authority references separately. A place may have multiple space-separated `@ref` "
            "URIs and may be classified with `@type`, `@subtype`, and `@n`.",
            "- Do not interpret `langUsage` as the language of the ancient document. Seven language declarations occur "
            "in essentially every file and describe the metadata environment; content language belongs to the linked "
            "transcription or another explicit field.",
            "- Normalize display labels without discarding them. Material values vary by case and language, the current "
            "settlement is `unbekannt` in most populated records, and the keyword vocabulary has more than 10,000 forms.",
            "- Use the high-coverage fields as first-class columns and the long-tail element/attribute inventory as an "
            "extension table or retained XML, rather than creating one nullable column for every TEI construct.",
            "",
            "## HGV metadata XML",
            "",
            f"Successfully parsed: {metadata.files:,} files.",
            "",
            "### Selected schema-relevant fields",
            "",
        ]
    )
    lines.extend(selected_field_table(metadata))

    semantic_profiles = [
        ("Identifier types (`idno/@type`)", ("idno", "type"), 40),
        ("Language identifiers (`language/@ident`)", ("language", "ident"), 40),
        ("Division types (`div/@type`)", ("div", "type"), 40),
        ("Division subtypes (`div/@subtype`)", ("div", "subtype"), 40),
        ("Bibliography types (`bibl/@type`)", ("bibl", "type"), 40),
        ("Bibliography subtypes (`bibl/@subtype`)", ("bibl", "subtype"), 40),
        ("Bibliographic scope types (`biblScope/@type`)", ("biblScope", "type"), 40),
        ("Provenance types (`provenance/@type`)", ("provenance", "type"), 40),
        ("Place types (`placeName/@type`)", ("placeName", "type"), 40),
        ("Place subtypes (`placeName/@subtype`)", ("placeName", "subtype"), 40),
        ("Keyword schemes (`keywords/@scheme`)", ("keywords", "scheme"), 40),
    ]
    for title, key, limit in semantic_profiles:
        lines.extend(
            value_table(
                title, metadata.tag_attributes.get(key), metadata.files, limit=limit
            )
        )

    text_profiles = [
        ("Material values", "material", 30),
        ("Current settlement values", "settlement", 30),
        ("Origin place values", "origPlace", 30),
        ("Keyword values", "term", 50),
    ]
    for title, key, limit in text_profiles:
        lines.extend(
            value_table(title, metadata.tag_text.get(key), metadata.files, limit=limit)
        )

    lines.extend(attribute_set_table(metadata, "origDate"))
    lines.extend(
        [
            "### Complete element-path inventory",
            "",
            "Paths distinguish semantically different uses of the same TEI element.",
            "",
        ]
    )
    lines.extend(element_path_table(metadata))
    lines.extend(["### Complete path/attribute inventory", ""])
    lines.extend(path_attribute_table(metadata))

    return "\n".join(lines).rstrip() + "\n"


def unique_paths(paths: Iterable[Path | None]) -> list[Path]:
    return sorted({path for path in paths if path is not None})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("idp_data", nargs="?", type=Path, default=Path("idp.data"))
    parser.add_argument("output", nargs="?", type=Path, default=Path("metadata.md"))
    parser.add_argument(
        "--no-progress", action="store_true", help="hide the HGV iteration progress bar"
    )
    arguments = parser.parse_args()

    triples = list(
        iterate_hgv_triples(arguments.idp_data, progressbar=not arguments.no_progress)
    )
    metadata_paths = [metadata for _, metadata, _, _ in triples]
    transcription_paths = [transcription for _, _, transcription, _ in triples]
    translation_paths = [translation for _, _, _, translation in triples]
    transcriptions = unique_paths(transcription_paths)
    translations = unique_paths(translation_paths)

    metadata_inventory = XmlInventory()
    metadata_iterator = tqdm(
        metadata_paths,
        total=len(metadata_paths),
        unit="metadata file",
        disable=arguments.no_progress,
    )
    for path in metadata_iterator:
        metadata_inventory.add(path)

    report = render_report(
        arguments.idp_data,
        len(triples),
        sum(path is not None for path in transcription_paths),
        sum(path is not None for path in translation_paths),
        len(transcriptions),
        len(translations),
        metadata_inventory,
    )
    arguments.output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
