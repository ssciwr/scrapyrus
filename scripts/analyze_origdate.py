# Used to profile every HGV `origDate` encoding in `idp.data` for the temporal
# retrieval and database-schema analysis documented in `insights/origdate.md`.

"""Print detailed JSON statistics for HGV ``origDate`` metadata."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import json
import re
from xml.etree import ElementTree

from scrapyrus.hgv import iterate_hgv_triples
from tqdm import tqdm


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
ORIG_DATE_PATH = f".//{{{TEI_NAMESPACE}}}origin/{{{TEI_NAMESPACE}}}origDate"
DATE_PATTERN = re.compile(
    r"^(?P<year>-?\d{4,})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?$"
)
DATE_ATTRIBUTES = ("when", "notBefore", "notAfter", "when-custom")


@dataclass(frozen=True)
class ParsedDate:
    raw: str
    year: int | None
    month: int | None
    day: int | None
    granularity: str
    status: str


def local_name(name: str) -> str:
    if name.startswith(f"{{{XML_NAMESPACE}}}"):
        return f"xml:{name.rpartition('}')[2]}"
    return name.rpartition("}")[2]


def normalized_text(element: ElementTree.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def gregorian_month_length(historical_year: int, month: int) -> int:
    astronomical_year = historical_year if historical_year > 0 else historical_year + 1
    leap = astronomical_year % 4 == 0 and (
        astronomical_year % 100 != 0 or astronomical_year % 400 == 0
    )
    return (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]


def parse_date(value: str, *, gregorian: bool = True) -> ParsedDate:
    match = DATE_PATTERN.fullmatch(value)
    if match is None:
        return ParsedDate(value, None, None, None, "invalid", "invalid_lexical")

    year = int(match.group("year"))
    month_text = match.group("month")
    day_text = match.group("day")
    month = int(month_text) if month_text is not None else None
    day = int(day_text) if day_text is not None else None
    granularity = "day" if day is not None else "month" if month is not None else "year"

    if year == 0:
        status = "year_zero"
    elif month is not None and not 1 <= month <= 12:
        status = "invalid_month"
    elif day is not None and not 1 <= day <= 31:
        status = "invalid_day"
    elif (
        gregorian
        and day is not None
        and month is not None
        and day > gregorian_month_length(year, month)
    ):
        status = "invalid_gregorian_day"
    else:
        status = "valid"
    return ParsedDate(value, year, month, day, granularity, status)


def date_shape(attributes: dict[str, str]) -> str:
    present = {name for name in DATE_ATTRIBUTES if name in attributes}
    if present == {"when"}:
        return "exact/when"
    if present == {"notBefore", "notAfter"}:
        return "closed range"
    if present == {"notBefore"}:
        return "open upper bound (notBefore only)"
    if present == {"notAfter"}:
        return "open lower bound (notAfter only)"
    if present == {"when-custom"}:
        return "custom exact date"
    if not present:
        return "text only"
    return "mixed"


def inclusive_year_width(start: int, end: int) -> int:
    """Count historical years inclusively, omitting nonexistent year zero."""

    return end - start + 1 - int(start < 0 < end)


def width_bucket(width: int | None, shape: str) -> str:
    if width is None:
        return "open/unparsed" if shape != "text only" else "text only"
    if width == 1:
        return "1 year"
    if width <= 5:
        return "2–5 years"
    if width <= 25:
        return "6–25 years"
    if width <= 50:
        return "26–50 years"
    if width <= 100:
        return "51–100 years"
    return "more than 100 years"


def interval_for(
    attributes: dict[str, str], parsed: dict[str, ParsedDate]
) -> tuple[int | None, int | None]:
    if "when" in attributes:
        year = parsed["when"].year
        return year, year
    if "when-custom" in attributes:
        year = parsed["when-custom"].year
        return year, year
    start = parsed["notBefore"].year if "notBefore" in attributes else None
    end = parsed["notAfter"].year if "notAfter" in attributes else None
    return start, end


def overlaps(interval: tuple[int | None, int | None], query: tuple[int, int]) -> bool:
    start, end = interval
    if start is None and end is None:
        return False
    query_start, query_end = query
    return (start is None or start <= query_end) and (end is None or end >= query_start)


def sorted_counter(counter: Counter[object]) -> dict[str, int]:
    return {
        str(key): value
        for key, value in sorted(
            counter.items(), key=lambda item: (-item[1], str(item[0]))
        )
    }


def analyze(idp_data: Path, *, progress: bool) -> dict[str, object]:
    triples = list(iterate_hgv_triples(idp_data, progressbar=progress))
    iterator = tqdm(
        triples,
        desc="Analyzing origDate",
        unit="record",
        disable=not progress,
    )

    document_cardinality: Counter[int] = Counter()
    attribute_presence: Counter[str] = Counter()
    attribute_combinations: Counter[tuple[str, ...]] = Counter()
    attribute_values: defaultdict[str, Counter[str]] = defaultdict(Counter)
    shapes: Counter[str] = Counter()
    granularity: defaultdict[str, Counter[str]] = defaultdict(Counter)
    parse_status: defaultdict[str, Counter[str]] = defaultdict(Counter)
    era: defaultdict[str, Counter[str]] = defaultdict(Counter)
    year_values: defaultdict[str, list[int]] = defaultdict(list)
    anomaly_examples: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    child_tags: Counter[str] = Counter()
    child_documents: Counter[str] = Counter()
    child_attribute_values: defaultdict[str, Counter[str]] = defaultdict(Counter)
    child_text: defaultdict[str, Counter[str]] = defaultdict(Counter)
    child_combinations: Counter[tuple[str, ...]] = Counter()
    labels: Counter[str] = Counter()
    labels_by_shape: defaultdict[str, Counter[str]] = defaultdict(Counter)
    precision_by_shape: Counter[str] = Counter()
    certainty_by_shape: Counter[str] = Counter()
    width_buckets: Counter[str] = Counter()
    alternative_ids: Counter[str] = Counter()
    queryable_documents = 0
    invalid_order = 0
    duplicate_raw_alternative_documents = 0
    duplicate_year_range_documents = 0
    multiple_all_identified = 0
    multiple_some_identified = 0
    multiple_none_identified = 0
    records_with_children = 0
    records_with_low_certainty = 0
    records_with_low_precision = 0
    records_with_only_text_dates = 0
    records_with_alternatives = 0
    all_intervals: list[tuple[int | None, int | None]] = []
    document_intervals: dict[str, list[tuple[int | None, int | None]]] = {}

    for hgv_id, metadata, _, _ in iterator:
        root = ElementTree.parse(metadata).getroot()
        elements = root.findall(ORIG_DATE_PATH)
        document_cardinality[len(elements)] += 1
        intervals: list[tuple[int | None, int | None]] = []
        raw_date_keys: list[tuple[str | None, ...]] = []
        document_child_tags: set[str] = set()
        identified = 0
        has_low_certainty = False
        has_low_precision = False

        for element in elements:
            attributes = {
                local_name(name): value for name, value in element.attrib.items()
            }
            combination = tuple(sorted(attributes))
            attribute_combinations[combination] += 1
            for name, value in attributes.items():
                attribute_presence[name] += 1
                attribute_values[name][value] += 1

            shape = date_shape(attributes)
            shapes[shape] += 1
            if "precision" in attributes:
                precision_by_shape[f"{shape}: {attributes['precision']}"] += 1
            if "cert" in attributes:
                certainty_by_shape[f"{shape}: {attributes['cert']}"] += 1
            parsed: dict[str, ParsedDate] = {}
            for name in DATE_ATTRIBUTES:
                if name not in attributes:
                    continue
                result = parse_date(attributes[name], gregorian=name != "when-custom")
                parsed[name] = result
                granularity[name][result.granularity] += 1
                parse_status[name][result.status] += 1
                if result.year is not None:
                    year_values[name].append(result.year)
                    if result.year < 0:
                        era[name]["BCE"] += 1
                    elif result.year > 0:
                        era[name]["CE"] += 1
                    else:
                        era[name]["year zero"] += 1
                if (
                    result.status != "valid"
                    and len(anomaly_examples[result.status]) < 20
                ):
                    anomaly_examples[result.status].append(
                        {"hgv_id": hgv_id, "attribute": name, "value": attributes[name]}
                    )

            interval = interval_for(attributes, parsed)
            intervals.append(interval)
            raw_date_keys.append(
                tuple(attributes.get(name) for name in DATE_ATTRIBUTES)
            )
            all_intervals.append(interval)
            start, end = interval
            if start is not None and end is not None and start > end:
                invalid_order += 1
                if len(anomaly_examples["reversed_range"]) < 20:
                    anomaly_examples["reversed_range"].append(
                        {
                            "hgv_id": hgv_id,
                            "notBefore": attributes.get("notBefore", ""),
                            "notAfter": attributes.get("notAfter", ""),
                        }
                    )
            width = (
                inclusive_year_width(start, end)
                if start is not None and end is not None and start <= end
                else None
            )
            width_buckets[width_bucket(width, shape)] += 1

            label = normalized_text(element)
            labels[label or "(empty)"] += 1
            labels_by_shape[shape][label or "(empty)"] += 1
            alternative_id = attributes.get("xml:id")
            if alternative_id is not None:
                identified += 1
                alternative_ids[alternative_id] += 1
            has_low_certainty |= attributes.get("cert") == "low"
            has_low_precision |= attributes.get("precision") in {"low", "medium"}

            direct_children = [local_name(child.tag) for child in element]
            child_combinations[tuple(sorted(direct_children))] += 1
            for child in element:
                child_tag = local_name(child.tag)
                child_tags[child_tag] += 1
                document_child_tags.add(child_tag)
                child_value = normalized_text(child)
                child_text[child_tag][child_value or "(empty)"] += 1
                for raw_name, value in child.attrib.items():
                    child_attribute_values[f"{child_tag}/@{local_name(raw_name)}"][
                        value
                    ] += 1

        for child_tag in document_child_tags:
            child_documents[child_tag] += 1
        records_with_children += bool(document_child_tags)
        records_with_low_certainty += has_low_certainty
        records_with_low_precision += has_low_precision
        document_intervals[hgv_id] = intervals
        valid_intervals = [
            interval
            for interval in intervals
            if interval[0] is not None or interval[1] is not None
        ]
        queryable_documents += bool(valid_intervals)
        records_with_only_text_dates += not valid_intervals

        if len(elements) > 1:
            records_with_alternatives += 1
            if identified == len(elements):
                multiple_all_identified += 1
            elif identified:
                multiple_some_identified += 1
            else:
                multiple_none_identified += 1
            duplicate_raw_alternative_documents += len(set(raw_date_keys)) < len(
                raw_date_keys
            )
            duplicate_year_range_documents += len(set(intervals)) < len(intervals)

    query_windows = {
        "2nd century CE (101–200)": (101, 200),
        "2nd century BCE (200–101 BCE)": (-200, -101),
    }
    query_matches: dict[str, dict[str, int]] = {}
    for label, query in query_windows.items():
        element_matches = sum(overlaps(interval, query) for interval in all_intervals)
        document_matches = sum(
            any(overlaps(interval, query) for interval in intervals)
            for intervals in document_intervals.values()
        )
        documents_with_contained_alternative = sum(
            any(
                start is not None
                and end is not None
                and start >= query[0]
                and end <= query[1]
                for start, end in intervals
            )
            for intervals in document_intervals.values()
        )
        documents_all_alternatives_overlap = sum(
            bool(intervals) and all(overlaps(interval, query) for interval in intervals)
            for intervals in document_intervals.values()
        )
        documents_all_alternatives_contained = sum(
            bool(intervals)
            and all(
                start is not None
                and end is not None
                and start >= query[0]
                and end <= query[1]
                for start, end in intervals
            )
            for intervals in document_intervals.values()
        )
        contained = sum(
            start is not None
            and end is not None
            and start >= query[0]
            and end <= query[1]
            for start, end in all_intervals
        )
        query_matches[label] = {
            "documents_with_any_overlapping_alternative": document_matches,
            "documents_with_any_fully_contained_alternative": documents_with_contained_alternative,
            "documents_where_all_alternatives_overlap": documents_all_alternatives_overlap,
            "documents_where_all_alternatives_are_contained": documents_all_alternatives_contained,
            "overlapping_origDate_elements": element_matches,
            "origDate_elements_fully_contained": contained,
        }

    value_summaries: dict[str, object] = {}
    for name, values in attribute_values.items():
        if name in {"cert", "precision", "n", "xml:id", "datingMethod", "type"}:
            value_summaries[name] = sorted_counter(values)

    child_value_summaries = {
        key: sorted_counter(values)
        for key, values in sorted(child_attribute_values.items())
    }
    child_text_summaries = {
        key: sorted_counter(values) for key, values in sorted(child_text.items())
    }
    date_summaries: dict[str, object] = {}
    for name in DATE_ATTRIBUTES:
        years = year_values[name]
        date_summaries[name] = {
            "count": sum(granularity[name].values()),
            "granularity": sorted_counter(granularity[name]),
            "parse_status": sorted_counter(parse_status[name]),
            "era": sorted_counter(era[name]),
            "minimum_year": min(years) if years else None,
            "maximum_year": max(years) if years else None,
        }

    return {
        "corpus": {
            "records": len(triples),
            "origDate_elements": sum(
                count * cardinality
                for cardinality, count in document_cardinality.items()
            ),
            "queryable_records": queryable_documents,
            "text_only_records": records_with_only_text_dates,
        },
        "document_cardinality": sorted_counter(document_cardinality),
        "alternatives": {
            "records_with_multiple_origDate": records_with_alternatives,
            "all_elements_have_xml_id": multiple_all_identified,
            "some_elements_have_xml_id": multiple_some_identified,
            "no_elements_have_xml_id": multiple_none_identified,
            "records_with_duplicate_raw_date_attributes": duplicate_raw_alternative_documents,
            "records_whose_alternatives_share_a_year_range": duplicate_year_range_documents,
            "xml_id_values": sorted_counter(alternative_ids),
        },
        "attribute_presence": sorted_counter(attribute_presence),
        "attribute_combinations": {
            ", ".join(combination) or "(none)": count
            for combination, count in sorted(
                attribute_combinations.items(), key=lambda item: (-item[1], item[0])
            )
        },
        "attribute_value_summaries": value_summaries,
        "date_shapes": sorted_counter(shapes),
        "precision_by_shape": sorted_counter(precision_by_shape),
        "certainty_by_shape": sorted_counter(certainty_by_shape),
        "date_fields": date_summaries,
        "interval_widths": sorted_counter(width_buckets),
        "reversed_closed_ranges": invalid_order,
        "annotations": {
            "records_with_direct_child_annotations": records_with_children,
            "records_with_cert_low": records_with_low_certainty,
            "records_with_precision_low_or_medium": records_with_low_precision,
            "child_elements": sorted_counter(child_tags),
            "records_by_child_element": sorted_counter(child_documents),
            "child_combinations": {
                ", ".join(combination) or "(none)": count
                for combination, count in sorted(
                    child_combinations.items(), key=lambda item: (-item[1], item[0])
                )
            },
            "child_attribute_values": child_value_summaries,
            "child_text_values": child_text_summaries,
        },
        "label_values": {
            "distinct": len(labels),
            "most_common": sorted_counter(Counter(dict(labels.most_common(30)))),
            "text_only_distinct": len(labels_by_shape["text only"]),
            "text_only_most_common": sorted_counter(
                Counter(dict(labels_by_shape["text only"].most_common(30)))
            ),
        },
        "query_examples": query_matches,
        "anomaly_examples": anomaly_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("idp_data", nargs="?", type=Path, default=Path("idp.data"))
    parser.add_argument("--no-progress", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            analyze(arguments.idp_data, progress=not arguments.no_progress), indent=2
        )
    )


if __name__ == "__main__":
    main()
