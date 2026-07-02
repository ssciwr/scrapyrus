# Used to profile HGV `placeName` metadata and the Trismegistos Places dump for
# the geographic retrieval and database-schema analysis documented in
# `insights/places.md`.

"""Print detailed JSON statistics for HGV ``placeName`` metadata."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree

from scrapyrus.idpdata import iterate_hgv_triples
from tqdm import tqdm


TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

MS_IDENTIFIER_PATH = (
    f".//{{{TEI_NAMESPACE}}}msDesc/"
    f"{{{TEI_NAMESPACE}}}msIdentifier/"
    f"{{{TEI_NAMESPACE}}}placeName/"
    f"{{{TEI_NAMESPACE}}}settlement"
)
ORIG_PLACE_PATH = (
    f".//{{{TEI_NAMESPACE}}}msDesc/"
    f"{{{TEI_NAMESPACE}}}history/"
    f"{{{TEI_NAMESPACE}}}origin/"
    f"{{{TEI_NAMESPACE}}}origPlace"
)
PROVENANCE_PATH = (
    f".//{{{TEI_NAMESPACE}}}msDesc/"
    f"{{{TEI_NAMESPACE}}}history/"
    f"{{{TEI_NAMESPACE}}}provenance"
)
PLACE_NAME = f"{{{TEI_NAMESPACE}}}placeName"
P = f"{{{TEI_NAMESPACE}}}p"

TM_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?trismegistos\.org/place/(?P<id>\d+)\b"
)
PLEIADES_PATTERN = re.compile(r"(?:https?://)?pleiades\.stoa\.org/places/(?P<id>\d+)\b")
WIKIDATA_PATTERN = re.compile(r"(?:https?://)?www\.wikidata\.org/wiki/(?P<id>Q\d+)\b")
GEONAMES_PATTERN = re.compile(r"(?:https?://)?www\.geonames\.org/(?P<id>\d+)\b")


@dataclass(frozen=True)
class GeoPlace:
    id: int
    country: str
    region: str
    nomos_code: str
    name_latin: str
    name_standard: str
    full_name: str
    status: str
    ethnicon: str
    location: str
    unicode_greek: str
    unicode_egyptian: str
    unicode_coptic: str
    begin_date: int | None
    begin_date_format: str
    end_date: int | None
    end_date_format: str
    provincia: str
    coordinates: str

    @property
    def has_coordinates(self) -> bool:
        return bool(self.coordinates.strip())


def local_name(name: str) -> str:
    if name.startswith(f"{{{XML_NAMESPACE}}}"):
        return f"xml:{name.rpartition('}')[2]}"
    return name.rpartition("}")[2]


def normalized_text(element: ElementTree.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def normalize_lookup(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.casefold().split())


def parse_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    return int(value)


def csv_value(row: dict[str, str], name: str) -> str:
    if name in row:
        return row[name]
    return row[f"{name};"].removesuffix(";")


def load_geo_places(path: Path) -> dict[int, GeoPlace]:
    places: dict[int, GeoPlace] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            place = GeoPlace(
                id=int(csv_value(row, "id")),
                country=csv_value(row, "country"),
                region=csv_value(row, "region"),
                nomos_code=csv_value(row, "nomos_code"),
                name_latin=csv_value(row, "name_latin"),
                name_standard=csv_value(row, "name_standard"),
                full_name=csv_value(row, "full_name"),
                status=csv_value(row, "status"),
                ethnicon=csv_value(row, "ethnicon"),
                location=csv_value(row, "location"),
                unicode_greek=csv_value(row, "unicode_greek"),
                unicode_egyptian=csv_value(row, "unicode_egyptian"),
                unicode_coptic=csv_value(row, "unicode_coptic"),
                begin_date=parse_int(csv_value(row, "begin_date")),
                begin_date_format=csv_value(row, "begin_date_format"),
                end_date=parse_int(csv_value(row, "end_date")),
                end_date_format=csv_value(row, "end_date_format"),
                provincia=csv_value(row, "provincia"),
                coordinates=csv_value(row, "coordinates"),
            )
            places[place.id] = place
    return places


def split_variants(value: str) -> set[str]:
    variants: set[str] = set()
    value = value.strip()
    if not value:
        return variants
    variants.add(value)
    for separator in (" - ", ";"):
        for part in value.split(separator):
            part = part.strip()
            if part:
                variants.add(part)
    return variants


def geo_name_index(places: dict[int, GeoPlace]) -> dict[str, set[int]]:
    index: defaultdict[str, set[int]] = defaultdict(set)
    for place in places.values():
        fields = (
            place.name_standard,
            place.name_latin,
            place.full_name,
            place.ethnicon,
            place.unicode_greek,
            place.unicode_egyptian,
            place.unicode_coptic,
        )
        for field in fields:
            for variant in split_variants(field):
                index[normalize_lookup(variant)].add(place.id)
    return dict(index)


def attributes(element: ElementTree.Element) -> dict[str, str]:
    return {local_name(name): value for name, value in element.attrib.items()}


def extract_authorities(ref: str) -> dict[str, tuple[str, ...]]:
    return {
        "trismegistos": tuple(TM_PATTERN.findall(ref)),
        "pleiades": tuple(PLEIADES_PATTERN.findall(ref)),
        "wikidata": tuple(WIKIDATA_PATTERN.findall(ref)),
        "geonames": tuple(GEONAMES_PATTERN.findall(ref)),
    }


def sorted_counter(counter: Counter[object]) -> dict[str, int]:
    return {
        str(key): value
        for key, value in sorted(
            counter.items(), key=lambda item: (-item[1], str(item[0]))
        )
    }


def top_counter(counter: Counter[object], limit: int = 30) -> dict[str, int]:
    return sorted_counter(Counter(dict(counter.most_common(limit))))


def percentage(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


class PlaceAccumulator:
    def __init__(
        self,
        places: dict[int, GeoPlace],
        name_index: dict[str, set[int]],
    ) -> None:
        self.places = places
        self.name_index = name_index
        self.occurrences: Counter[str] = Counter()
        self.documents: defaultdict[str, set[str]] = defaultdict(set)
        self.documents_with_ref: defaultdict[str, set[str]] = defaultdict(set)
        self.documents_with_tm: defaultdict[str, set[str]] = defaultdict(set)
        self.documents_with_pleiades: defaultdict[str, set[str]] = defaultdict(set)
        self.documents_with_key: defaultdict[str, set[str]] = defaultdict(set)
        self.labels: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.type_values: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.subtype_values: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.attribute_presence: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.attribute_combinations: defaultdict[str, Counter[tuple[str, ...]]] = (
            defaultdict(Counter)
        )
        self.authority_state: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self.authority_occurrences: defaultdict[str, Counter[str]] = defaultdict(
            Counter
        )
        self.tm_occurrences: Counter[int] = Counter()
        self.tm_label_values: defaultdict[int, Counter[str]] = defaultdict(Counter)
        self.tm_scope_values: defaultdict[int, Counter[str]] = defaultdict(Counter)
        self.tm_type_values: defaultdict[int, Counter[str]] = defaultdict(Counter)
        self.tm_documents: defaultdict[int, set[str]] = defaultdict(set)
        self.pleiades_occurrences: Counter[str] = Counter()
        self.unmatched_tm_ids: Counter[int] = Counter()
        self.no_tm_label_candidates: Counter[str] = Counter()
        self.no_tm_single_candidate_labels: Counter[str] = Counter()
        self.no_tm_ambiguous_candidate_labels: Counter[str] = Counter()
        self.no_tm_no_candidate_labels: Counter[str] = Counter()
        self.no_tm_label_candidates_by_scope: defaultdict[str, Counter[str]] = (
            defaultdict(Counter)
        )
        self.no_tm_single_candidate_labels_by_scope: defaultdict[str, Counter[str]] = (
            defaultdict(Counter)
        )
        self.no_tm_ambiguous_candidate_labels_by_scope: defaultdict[
            str, Counter[str]
        ] = defaultdict(Counter)
        self.no_tm_no_candidate_labels_by_scope: defaultdict[str, Counter[str]] = (
            defaultdict(Counter)
        )
        self.key_candidates: defaultdict[str, set[int]] = defaultdict(set)
        self.elements_with_multiple_tm_ids: Counter[str] = Counter()
        self.elements_with_resolved_tm: Counter[str] = Counter()
        self.elements_with_tm_coordinates: Counter[str] = Counter()
        self.elements_with_any_tm_date_span: Counter[str] = Counter()

    def add(
        self,
        *,
        scope: str,
        document_tm_id: str,
        element: ElementTree.Element,
    ) -> dict[str, object]:
        attrs = attributes(element)
        label = normalized_text(element) or "(empty)"
        ref = attrs.get("ref", "")
        authorities = extract_authorities(ref)
        tm_ids = tuple(int(value) for value in authorities["trismegistos"])
        pleiades_ids = authorities["pleiades"]

        self.occurrences[scope] += 1
        self.documents[scope].add(document_tm_id)
        self.labels[scope][label] += 1
        self.attribute_combinations[scope][tuple(sorted(attrs))] += 1

        for name, value in attrs.items():
            self.attribute_presence[scope][name] += 1
            if name == "type":
                self.type_values[scope][value] += 1
            elif name == "subtype":
                self.subtype_values[scope][value] += 1

        if ref:
            self.authority_state[scope]["has_ref"] += 1
            self.documents_with_ref[scope].add(document_tm_id)
        else:
            self.authority_state[scope]["no_ref"] += 1
        if tm_ids:
            self.authority_state[scope]["has_tm"] += 1
            self.documents_with_tm[scope].add(document_tm_id)
        else:
            self.authority_state[scope]["no_tm"] += 1
        if pleiades_ids:
            self.authority_state[scope]["has_pleiades"] += 1
            self.documents_with_pleiades[scope].add(document_tm_id)
        if attrs.get("key"):
            self.authority_state[scope]["has_key"] += 1
            self.documents_with_key[scope].add(document_tm_id)

        for authority, values in authorities.items():
            if values:
                self.authority_occurrences[scope][authority] += 1

        if len(tm_ids) > 1:
            self.elements_with_multiple_tm_ids[scope] += 1

        resolved_tm = False
        has_coordinates = False
        has_date_span = False
        for tm_id in tm_ids:
            self.tm_occurrences[tm_id] += 1
            self.tm_label_values[tm_id][label] += 1
            self.tm_scope_values[tm_id][scope] += 1
            self.tm_type_values[tm_id][
                ":".join(
                    part
                    for part in (attrs.get("type", ""), attrs.get("subtype", ""))
                    if part
                )
                or "(none)"
            ] += 1
            self.tm_documents[tm_id].add(document_tm_id)
            place = self.places.get(tm_id)
            if place is None:
                self.unmatched_tm_ids[tm_id] += 1
                continue
            resolved_tm = True
            has_coordinates |= place.has_coordinates
            has_date_span |= place.begin_date is not None or place.end_date is not None

        for pleiades_id in pleiades_ids:
            self.pleiades_occurrences[pleiades_id] += 1

        if resolved_tm:
            self.elements_with_resolved_tm[scope] += 1
        if has_coordinates:
            self.elements_with_tm_coordinates[scope] += 1
        if has_date_span:
            self.elements_with_any_tm_date_span[scope] += 1

        if not tm_ids:
            candidates = self.name_index.get(normalize_lookup(label), set())
            if candidates:
                self.no_tm_label_candidates[label] += 1
                self.no_tm_label_candidates_by_scope[scope][label] += 1
                if len(candidates) == 1:
                    self.no_tm_single_candidate_labels[label] += 1
                    self.no_tm_single_candidate_labels_by_scope[scope][label] += 1
                else:
                    self.no_tm_ambiguous_candidate_labels[label] += 1
                    self.no_tm_ambiguous_candidate_labels_by_scope[scope][label] += 1
            else:
                self.no_tm_no_candidate_labels[label] += 1
                self.no_tm_no_candidate_labels_by_scope[scope][label] += 1

        key = attrs.get("key")
        if key:
            self.key_candidates[key].update(
                self.name_index.get(normalize_lookup(key), set())
            )

        return {
            "label": label,
            "attributes": attrs,
            "tm_ids": tm_ids,
            "pleiades_ids": pleiades_ids,
        }

    def summary(self) -> dict[str, object]:
        scopes = sorted(self.occurrences)
        scope_summary = {}
        for scope in scopes:
            total = self.occurrences[scope]
            no_tm = self.authority_state[scope]["no_tm"]
            with_ref = self.authority_state[scope]["has_ref"]
            with_tm = self.authority_state[scope]["has_tm"]
            with_pleiades = self.authority_state[scope]["has_pleiades"]
            with_key = self.authority_state[scope]["has_key"]
            resolved = self.elements_with_resolved_tm[scope]
            with_coordinates = self.elements_with_tm_coordinates[scope]
            with_date_span = self.elements_with_any_tm_date_span[scope]
            scope_summary[scope] = {
                "documents": len(self.documents[scope]),
                "documents_with_ref": len(self.documents_with_ref[scope]),
                "documents_with_ref_share": percentage(
                    len(self.documents_with_ref[scope]), len(self.documents[scope])
                ),
                "documents_with_trismegistos_id": len(self.documents_with_tm[scope]),
                "documents_with_trismegistos_id_share": percentage(
                    len(self.documents_with_tm[scope]), len(self.documents[scope])
                ),
                "documents_with_pleiades_id": len(self.documents_with_pleiades[scope]),
                "documents_with_pleiades_id_share": percentage(
                    len(self.documents_with_pleiades[scope]),
                    len(self.documents[scope]),
                ),
                "documents_with_key": len(self.documents_with_key[scope]),
                "documents_with_key_share": percentage(
                    len(self.documents_with_key[scope]), len(self.documents[scope])
                ),
                "occurrences": total,
                "with_ref": with_ref,
                "with_ref_share": percentage(with_ref, total),
                "with_trismegistos_id": with_tm,
                "with_trismegistos_id_share": percentage(with_tm, total),
                "with_pleiades_id": with_pleiades,
                "with_pleiades_id_share": percentage(with_pleiades, total),
                "with_key": with_key,
                "with_key_share": percentage(with_key, total),
                "without_trismegistos_id": no_tm,
                "without_trismegistos_id_share": percentage(no_tm, total),
                "multiple_trismegistos_ids": self.elements_with_multiple_tm_ids[scope],
                "resolved_in_export_geo": resolved,
                "with_export_geo_coordinates": with_coordinates,
                "with_export_geo_date_span": with_date_span,
                "no_tm_exact_label_candidate_total": sum(
                    self.no_tm_label_candidates_by_scope[scope].values()
                ),
                "no_tm_single_exact_label_candidate_total": sum(
                    self.no_tm_single_candidate_labels_by_scope[scope].values()
                ),
                "no_tm_ambiguous_exact_label_candidate_total": sum(
                    self.no_tm_ambiguous_candidate_labels_by_scope[scope].values()
                ),
                "no_tm_top_single_candidate_labels": top_counter(
                    self.no_tm_single_candidate_labels_by_scope[scope], 20
                ),
                "no_tm_top_ambiguous_candidate_labels": top_counter(
                    self.no_tm_ambiguous_candidate_labels_by_scope[scope], 20
                ),
                "no_tm_top_no_candidate_labels": top_counter(
                    self.no_tm_no_candidate_labels_by_scope[scope], 20
                ),
                "attribute_presence": sorted_counter(self.attribute_presence[scope]),
                "attribute_combinations": {
                    ", ".join(combination) or "(none)": count
                    for combination, count in sorted(
                        self.attribute_combinations[scope].items(),
                        key=lambda item: (-item[1], item[0]),
                    )[:20]
                },
                "authority_occurrences": sorted_counter(
                    self.authority_occurrences[scope]
                ),
                "type_values": sorted_counter(self.type_values[scope]),
                "subtype_values": sorted_counter(self.subtype_values[scope]),
                "top_labels": top_counter(self.labels[scope], 30),
            }

        return {
            "scopes": scope_summary,
            "trismegistos": self.tm_summary(),
            "pleiades": {
                "distinct_ids": len(self.pleiades_occurrences),
                "top_ids": top_counter(self.pleiades_occurrences, 20),
            },
            "no_trismegistos_label_matching": {
                "elements_with_any_exact_geo_name_candidate": sum(
                    self.no_tm_label_candidates.values()
                ),
                "elements_with_single_exact_geo_name_candidate": sum(
                    self.no_tm_single_candidate_labels.values()
                ),
                "elements_with_ambiguous_exact_geo_name_candidate": sum(
                    self.no_tm_ambiguous_candidate_labels.values()
                ),
                "top_single_candidate_labels": top_counter(
                    self.no_tm_single_candidate_labels, 30
                ),
                "top_ambiguous_candidate_labels": top_counter(
                    self.no_tm_ambiguous_candidate_labels, 30
                ),
                "top_no_candidate_labels": top_counter(
                    self.no_tm_no_candidate_labels, 30
                ),
                "key_candidates": {
                    key: sorted(values)
                    for key, values in sorted(self.key_candidates.items())
                },
            },
        }

    def tm_summary(self) -> dict[str, object]:
        top = {}
        for tm_id, count in self.tm_occurrences.most_common(30):
            place = self.places.get(tm_id)
            top[str(tm_id)] = {
                "occurrences": count,
                "documents": len(self.tm_documents[tm_id]),
                "labels": top_counter(self.tm_label_values[tm_id], 10),
                "scopes": sorted_counter(self.tm_scope_values[tm_id]),
                "place_types": sorted_counter(self.tm_type_values[tm_id]),
                "export_geo": None
                if place is None
                else {
                    "name_standard": place.name_standard,
                    "name_latin": place.name_latin,
                    "full_name": place.full_name,
                    "status": place.status,
                    "country": place.country,
                    "region": place.region,
                    "nomos_code": place.nomos_code,
                    "begin_date": place.begin_date,
                    "end_date": place.end_date,
                    "provincia": place.provincia,
                    "coordinates": place.coordinates,
                },
            }

        distinct = set(self.tm_occurrences)
        resolved = {tm_id for tm_id in distinct if tm_id in self.places}
        with_coordinates = {
            tm_id for tm_id in resolved if self.places[tm_id].has_coordinates
        }
        with_date_span = {
            tm_id
            for tm_id in resolved
            if self.places[tm_id].begin_date is not None
            or self.places[tm_id].end_date is not None
        }

        return {
            "distinct_referenced_ids": len(distinct),
            "distinct_referenced_ids_resolved_in_export_geo": len(resolved),
            "distinct_referenced_ids_missing_from_export_geo": sorted(
                distinct - resolved
            ),
            "distinct_referenced_ids_with_coordinates": len(with_coordinates),
            "distinct_referenced_ids_with_date_span": len(with_date_span),
            "total_id_occurrences": sum(self.tm_occurrences.values()),
            "unmatched_id_occurrences": sorted_counter(self.unmatched_tm_ids),
            "top_referenced_ids": top,
        }


def direct_children(
    element: ElementTree.Element, tag: str
) -> list[ElementTree.Element]:
    return [child for child in element if child.tag == tag]


def place_signature(element: ElementTree.Element) -> str:
    attrs = attributes(element)
    parts = [attrs.get("type", "(no type)")]
    if attrs.get("subtype"):
        parts.append(attrs["subtype"])
    if attrs.get("cert"):
        parts.append(f"cert={attrs['cert']}")
    if attrs.get("ref"):
        parts.append("ref")
    return ":".join(parts)


def analyze(
    idp_data: Path,
    geo_csv: Path,
    *,
    progress: bool,
) -> dict[str, object]:
    places = load_geo_places(geo_csv)
    name_index = geo_name_index(places)
    triples = list(iterate_hgv_triples(idp_data, progressbar=progress))
    accumulator = PlaceAccumulator(places, name_index)

    provenance_events = 0
    provenance_event_documents: set[str] = set()
    provenance_event_types: Counter[str] = Counter()
    provenance_event_attribute_presence: Counter[str] = Counter()
    provenance_p_elements = 0
    provenance_p_with_place_names = 0
    provenance_p_place_counts: Counter[int] = Counter()
    provenance_p_signatures: Counter[tuple[str, ...]] = Counter()
    provenance_p_tm_coverage: Counter[str] = Counter()
    provenance_p_exclude = 0
    provenance_p_with_offset = 0
    provenance_p_xml_ids: Counter[str] = Counter()
    provenance_place_cardinality_by_document: Counter[int] = Counter()
    provenance_p_cardinality_by_document: Counter[int] = Counter()
    origin_place_texts: Counter[str] = Counter()
    origin_place_attributes: Counter[str] = Counter()
    origin_place_documents = 0
    origin_place_name_documents: set[str] = set()

    iterator = tqdm(
        triples,
        desc="Analyzing placeName",
        unit="record",
        disable=not progress,
    )
    for document_tm_id, metadata, _, _ in iterator:
        root = ElementTree.parse(metadata).getroot()

        current_settlements = root.findall(MS_IDENTIFIER_PATH)
        for settlement in current_settlements:
            accumulator.add(
                scope="current_settlement",
                document_tm_id=document_tm_id,
                element=settlement,
            )

        orig_places = root.findall(ORIG_PLACE_PATH)
        if orig_places:
            origin_place_documents += 1
        for orig_place in orig_places:
            label = normalized_text(orig_place) or "(empty)"
            origin_place_texts[label] += 1
            for name in attributes(orig_place):
                origin_place_attributes[name] += 1
            for place_name in orig_place.iter(PLACE_NAME):
                origin_place_name_documents.add(document_tm_id)
                accumulator.add(
                    scope="origin_place_name",
                    document_tm_id=document_tm_id,
                    element=place_name,
                )

        document_provenance_place_count = 0
        document_provenance_p_count = 0
        for provenance in root.findall(PROVENANCE_PATH):
            provenance_events += 1
            provenance_event_documents.add(document_tm_id)
            event_attrs = attributes(provenance)
            provenance_event_types[event_attrs.get("type", "(none)")] += 1
            for name in event_attrs:
                provenance_event_attribute_presence[name] += 1

            direct_place_names = direct_children(provenance, PLACE_NAME)
            for place_name in direct_place_names:
                accumulator.add(
                    scope="provenance_place",
                    document_tm_id=document_tm_id,
                    element=place_name,
                )
                document_provenance_place_count += 1

            for paragraph in direct_children(provenance, P):
                paragraph_attrs = attributes(paragraph)
                provenance_p_elements += 1
                document_provenance_p_count += 1
                if paragraph_attrs.get("exclude"):
                    provenance_p_exclude += 1
                if paragraph_attrs.get("xml:id"):
                    provenance_p_xml_ids[paragraph_attrs["xml:id"]] += 1
                if direct_children(paragraph, f"{{{TEI_NAMESPACE}}}offset"):
                    provenance_p_with_offset += 1

                place_names = direct_children(paragraph, PLACE_NAME)
                if not place_names:
                    continue
                provenance_p_with_place_names += 1
                provenance_p_place_counts[len(place_names)] += 1
                provenance_p_signatures[
                    tuple(place_signature(place_name) for place_name in place_names)
                ] += 1

                tm_present = 0
                for place_name in place_names:
                    result = accumulator.add(
                        scope="provenance_place",
                        document_tm_id=document_tm_id,
                        element=place_name,
                    )
                    document_provenance_place_count += 1
                    tm_present += bool(result["tm_ids"])

                if tm_present == len(place_names):
                    provenance_p_tm_coverage["all_place_names_have_tm"] += 1
                elif tm_present:
                    provenance_p_tm_coverage["some_place_names_have_tm"] += 1
                else:
                    provenance_p_tm_coverage["no_place_names_have_tm"] += 1

        provenance_place_cardinality_by_document[document_provenance_place_count] += 1
        provenance_p_cardinality_by_document[document_provenance_p_count] += 1

    geo_country = Counter(place.country or "(empty)" for place in places.values())
    geo_provincia = Counter(place.provincia or "(empty)" for place in places.values())
    geo_status = Counter(place.status or "(empty)" for place in places.values())
    geo_rows_with_coordinates = sum(place.has_coordinates for place in places.values())
    geo_rows_with_date_span = sum(
        place.begin_date is not None or place.end_date is not None
        for place in places.values()
    )

    place_summary = accumulator.summary()

    return {
        "corpus": {
            "records": len(triples),
            "idp_data_revision": git_revision(idp_data),
        },
        "export_geo": {
            "path": str(geo_csv),
            "rows": len(places),
            "rows_with_coordinates": geo_rows_with_coordinates,
            "rows_with_coordinates_share": percentage(
                geo_rows_with_coordinates, len(places)
            ),
            "rows_with_date_span": geo_rows_with_date_span,
            "rows_with_date_span_share": percentage(
                geo_rows_with_date_span, len(places)
            ),
            "countries": top_counter(geo_country, 20),
            "provincia": top_counter(geo_provincia, 20),
            "status": top_counter(geo_status, 30),
        },
        "place_names": place_summary,
        "provenance": {
            "events": provenance_events,
            "documents": len(provenance_event_documents),
            "event_types": sorted_counter(provenance_event_types),
            "event_attribute_presence": sorted_counter(
                provenance_event_attribute_presence
            ),
            "paragraphs": provenance_p_elements,
            "paragraphs_with_place_names": provenance_p_with_place_names,
            "paragraphs_with_exclude": provenance_p_exclude,
            "paragraphs_with_offset": provenance_p_with_offset,
            "paragraph_place_name_counts": sorted_counter(provenance_p_place_counts),
            "paragraph_tm_coverage": sorted_counter(provenance_p_tm_coverage),
            "top_paragraph_signatures": {
                " + ".join(signature): count
                for signature, count in sorted(
                    provenance_p_signatures.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:30]
            },
            "top_paragraph_xml_ids": top_counter(provenance_p_xml_ids, 20),
            "place_names_per_document": sorted_counter(
                provenance_place_cardinality_by_document
            ),
            "paragraphs_per_document": sorted_counter(
                provenance_p_cardinality_by_document
            ),
        },
        "origin_place": {
            "documents_with_origPlace": origin_place_documents,
            "top_texts": top_counter(origin_place_texts, 30),
            "attribute_presence": sorted_counter(origin_place_attributes),
            "documents_with_structured_placeName": len(origin_place_name_documents),
        },
    }


def git_revision(path: Path) -> str | None:
    git = path / ".git"
    if not git.exists():
        return None
    head = git / "HEAD"
    try:
        value = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if value.startswith("ref: "):
        ref_path = git / value.removeprefix("ref: ")
        try:
            return ref_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("idp_data", nargs="?", type=Path, default=Path("idp.data"))
    parser.add_argument(
        "--geo-csv",
        type=Path,
        default=Path("export_geo.csv"),
        help="Trismegistos Places export CSV.",
    )
    parser.add_argument("--no-progress", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            analyze(
                arguments.idp_data,
                arguments.geo_csv,
                progress=not arguments.no_progress,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
