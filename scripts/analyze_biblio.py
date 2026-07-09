# Used to profile standalone TEI `Biblio` XML records for the bibliographic
# retrieval and database-schema analysis documented in `insights/biblio.md`.

"""Print detailed JSON statistics for IDP standalone Biblio XML records."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json
import re
from typing import Any

from saxonche import PySaxonApiError, PySaxonProcessor, PyXdmNode
from scrapyrus.saxon_xml import (
    attribute_value,
    attributes as xml_attributes,
    direct_children as xml_direct_children,
    display_name as local_name,
    document_element,
    iter_elements,
    normalized_text,
    parse_xml_document,
)
from tqdm import tqdm


BIBLIO_TARGET_PATTERN = re.compile(r"https?://papyri\.info/biblio/(?P<id>\d+)\b")
YEAR_PATTERN = re.compile(r"\b(?P<year>[12]\d{3})\b")


def attributes(element: PyXdmNode) -> dict[str, str]:
    return xml_attributes(element)


def direct_children(
    element: PyXdmNode,
    local_tag: str,
) -> list[PyXdmNode]:
    return xml_direct_children(element, local_tag)


def iter_descendants(
    element: PyXdmNode,
    local_tag: str,
) -> list[PyXdmNode]:
    return list(iter_elements(element, local_name=local_tag))


def sorted_counter(counter: Counter[Any]) -> dict[str, int]:
    return {
        str(key): value
        for key, value in sorted(
            counter.items(), key=lambda item: (-item[1], str(item[0]))
        )
    }


def top_counter(counter: Counter[Any], limit: int = 30) -> dict[str, int]:
    return sorted_counter(Counter(dict(counter.most_common(limit))))


def percentage(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


def element_path(root: PyXdmNode, element: PyXdmNode) -> str:
    parts: list[str] = []
    current: PyXdmNode | None = element
    while current is not None and current.node_kind_str == "element":
        parts.append(local_name(current.name))
        if current.equals(root):
            break
        current = current.get_parent()
    return "/" + "/".join(reversed(parts))


def title_signature(element: PyXdmNode) -> str:
    attrs = attributes(element)
    parts = []
    if "level" in attrs:
        parts.append(f"level={attrs['level']}")
    if "type" in attrs:
        parts.append(f"type={attrs['type']}")
    return ", ".join(parts) or "(no level/type)"


def contributor_shape(element: PyXdmNode) -> str:
    child_names = tuple(
        local_name(child.name) for child in xml_direct_children(element)
    )
    if child_names:
        return " + ".join(child_names)
    if normalized_text(element):
        return "text"
    return "empty"


def target_kind(target: str) -> str:
    if BIBLIO_TARGET_PATTERN.search(target):
        return "papyri.info/biblio"
    if "doi.org/" in target or target.lower().startswith("doi:"):
        return "doi"
    if target.startswith(("http://", "https://")):
        return target.split("/", 3)[2].removeprefix("www.")
    if target.startswith("#"):
        return "local_fragment"
    return "other"


def parse_biblio_id(path: Path, root_attrs: dict[str, str]) -> str | None:
    xml_id = root_attrs.get("xml:id")
    if xml_id and xml_id.startswith("b") and xml_id[1:].isdigit():
        return xml_id[1:]
    if path.stem.isdigit():
        return path.stem
    return None


def summarize_cardinality(cardinality: Counter[int]) -> dict[str, int]:
    return {
        str(key): value
        for key, value in sorted(cardinality.items(), key=lambda item: item[0])
    }


def analyze_hgv_references(
    idp_data: Path,
    biblio_ids: set[str],
    *,
    progress: bool,
) -> dict[str, object]:
    metadata_root = idp_data / "HGV_meta_EpiDoc"
    metadata_files = sorted(metadata_root.glob("HGV*/*.xml"))
    iterator = tqdm(
        metadata_files,
        desc="Analyzing HGV Biblio references",
        unit="record",
        disable=not progress,
    )

    pointer_occurrences = 0
    pointer_documents: set[str] = set()
    referenced_ids: Counter[str] = Counter()
    documents_by_biblio_id: defaultdict[str, set[str]] = defaultdict(set)
    context_by_biblio_id: defaultdict[str, Counter[str]] = defaultdict(Counter)
    missing_ids: Counter[str] = Counter()
    nearest_bibl_type: Counter[str] = Counter()

    with PySaxonProcessor(license=False) as proc:
        for metadata in iterator:
            hgv_id = metadata.stem
            root = document_element(parse_xml_document(proc, metadata))

            for ptr in iter_descendants(root, "ptr"):
                target = attribute_value(ptr, "target", "") or ""
                match = BIBLIO_TARGET_PATTERN.search(target)
                if match is None:
                    continue
                biblio_id = match.group("id")
                pointer_occurrences += 1
                pointer_documents.add(hgv_id)
                referenced_ids[biblio_id] += 1
                documents_by_biblio_id[biblio_id].add(hgv_id)
                if biblio_id not in biblio_ids:
                    missing_ids[biblio_id] += 1

                ancestor = ptr.get_parent()
                context = "(none)"
                while ancestor is not None and ancestor.node_kind_str == "element":
                    if local_name(ancestor.name) == "bibl":
                        context = attribute_value(ancestor, "type", "(no type)")
                        break
                    ancestor = ancestor.get_parent()
                nearest_bibl_type[context] += 1
                context_by_biblio_id[biblio_id][context] += 1

    top_referenced = {}
    for biblio_id, count in referenced_ids.most_common(30):
        top_referenced[biblio_id] = {
            "ptr_occurrences": count,
            "hgv_documents": len(documents_by_biblio_id[biblio_id]),
            "nearest_bibl_type": sorted_counter(context_by_biblio_id[biblio_id]),
        }

    return {
        "metadata_files": len(metadata_files),
        "metadata_files_with_biblio_pointer": len(pointer_documents),
        "pointer_occurrences": pointer_occurrences,
        "distinct_referenced_biblio_ids": len(referenced_ids),
        "referenced_biblio_ids_resolved": len(set(referenced_ids) & biblio_ids),
        "referenced_biblio_ids_missing": len(set(referenced_ids) - biblio_ids),
        "biblio_records_referenced_by_hgv": len(biblio_ids & set(referenced_ids)),
        "biblio_records_not_referenced_by_hgv": len(biblio_ids - set(referenced_ids)),
        "nearest_bibl_type": sorted_counter(nearest_bibl_type),
        "missing_ids": top_counter(missing_ids, 30),
        "top_referenced_biblio_ids": top_referenced,
    }


def analyze(
    biblio_root: Path,
    *,
    idp_data: Path | None,
    progress: bool,
) -> dict[str, object]:
    files = sorted(biblio_root.glob("*/*.xml"))
    iterator = tqdm(files, desc="Analyzing Biblio", unit="record", disable=not progress)

    parse_errors: list[dict[str, str]] = []
    root_type: Counter[str] = Counter()
    root_subtype: Counter[str] = Counter()
    root_language: Counter[str] = Counter()
    root_attribute_presence: Counter[str] = Counter()
    root_attribute_combinations: Counter[tuple[str, ...]] = Counter()
    root_child_presence: Counter[str] = Counter()
    root_child_occurrences: Counter[str] = Counter()
    root_child_cardinality: defaultdict[str, Counter[int]] = defaultdict(Counter)
    element_paths: Counter[str] = Counter()
    element_presence: defaultdict[str, set[str]] = defaultdict(set)
    attribute_presence: Counter[str] = Counter()
    attribute_values: defaultdict[str, Counter[str]] = defaultdict(Counter)

    ids: set[str] = set()
    duplicate_ids: Counter[str] = Counter()
    id_consistency: Counter[str] = Counter()
    idno_types: Counter[str] = Counter()
    idno_values_by_type: defaultdict[str, Counter[str]] = defaultdict(Counter)

    title_cardinality: Counter[int] = Counter()
    title_signatures: Counter[str] = Counter()
    title_text_by_signature: defaultdict[str, Counter[str]] = defaultdict(Counter)
    records_with_main_title = 0

    contributor_cardinality: defaultdict[str, Counter[int]] = defaultdict(Counter)
    contributor_shapes: defaultdict[str, Counter[str]] = defaultdict(Counter)
    contributor_attribute_presence: defaultdict[str, Counter[str]] = defaultdict(
        Counter
    )
    contributor_name_values: defaultdict[str, Counter[str]] = defaultdict(Counter)

    date_cardinality: Counter[int] = Counter()
    date_values: Counter[str] = Counter()
    date_attribute_presence: Counter[str] = Counter()
    date_years: Counter[int] = Counter()
    date_unparsed_values: Counter[str] = Counter()

    bibl_scope_cardinality: Counter[int] = Counter()
    bibl_scope_types: Counter[str] = Counter()
    bibl_scope_attribute_presence: Counter[str] = Counter()
    bibl_scope_values_by_type: defaultdict[str, Counter[str]] = defaultdict(Counter)
    bibl_scope_with_from_to: Counter[str] = Counter()

    related_item_cardinality: Counter[int] = Counter()
    related_item_types: Counter[str] = Counter()
    related_item_attribute_presence: Counter[str] = Counter()
    related_item_target_state: Counter[str] = Counter()
    related_item_targets_by_type: defaultdict[str, Counter[str]] = defaultdict(Counter)
    related_item_biblio_targets: defaultdict[str, Counter[str]] = defaultdict(Counter)
    related_item_nested_title_signatures: defaultdict[str, Counter[str]] = defaultdict(
        Counter
    )
    related_item_nested_child_presence: defaultdict[str, Counter[str]] = defaultdict(
        Counter
    )

    ptr_targets: Counter[str] = Counter()
    ptr_target_kinds: Counter[str] = Counter()
    ptr_target_documents: defaultdict[str, set[str]] = defaultdict(set)

    note_cardinality: Counter[int] = Counter()
    note_types: Counter[str] = Counter()
    note_values_by_type: defaultdict[str, Counter[str]] = defaultdict(Counter)

    seg_cardinality: Counter[int] = Counter()
    seg_types: Counter[str] = Counter()
    seg_subtypes: Counter[str] = Counter()
    seg_resp: Counter[str] = Counter()
    seg_text_length_buckets: Counter[str] = Counter()

    def parsed_roots():
        with PySaxonProcessor(license=False) as proc:
            for file in iterator:
                try:
                    yield file, document_element(parse_xml_document(proc, file))
                except PySaxonApiError as error:
                    parse_errors.append({"path": str(file), "error": str(error)})

    for file, root in parsed_roots():
        root_attrs = attributes(root)
        biblio_id = parse_biblio_id(file, root_attrs) or file.stem
        if biblio_id in ids:
            duplicate_ids[biblio_id] += 1
        ids.add(biblio_id)

        pi_values = [
            normalized_text(idno)
            for idno in direct_children(root, "idno")
            if attribute_value(idno, "type") == "pi"
        ]
        root_xml_id = root_attrs.get("xml:id", "")
        expected_xml_id = f"b{file.stem}"
        if root_xml_id == expected_xml_id and pi_values == [file.stem]:
            id_consistency["file_stem_matches_xml_id_and_pi"] += 1
        elif root_xml_id == expected_xml_id:
            id_consistency["file_stem_matches_xml_id"] += 1
        elif pi_values == [file.stem]:
            id_consistency["file_stem_matches_pi"] += 1
        else:
            id_consistency["mismatch"] += 1

        root_type[root_attrs.get("type", "(none)")] += 1
        root_subtype[root_attrs.get("subtype", "(none)")] += 1
        root_language[root_attrs.get("xml:lang", "(none)")] += 1
        root_attribute_combinations[tuple(sorted(root_attrs))] += 1
        for name, value in root_attrs.items():
            root_attribute_presence[name] += 1

        direct_counts = Counter(
            local_name(child.name) for child in xml_direct_children(root)
        )
        for name, count in direct_counts.items():
            root_child_presence[name] += 1
            root_child_occurrences[name] += count
        expected_root_children = (
            "title",
            "author",
            "editor",
            "date",
            "biblScope",
            "relatedItem",
            "idno",
            "note",
            "seg",
        )
        for expected_name in expected_root_children:
            root_child_cardinality[expected_name][direct_counts[expected_name]] += 1
        for extra_name in sorted(set(direct_counts) - set(expected_root_children)):
            root_child_cardinality[extra_name][direct_counts[extra_name]] += 1

        for element in iter_elements(root):
            path = element_path(root, element)
            element_paths[path] += 1
            element_presence[path].add(biblio_id)
            for name, value in attributes(element).items():
                attribute_presence[f"{path}/@{name}"] += 1
                if len(attribute_values[f"{path}/@{name}"]) <= 10000:
                    attribute_values[f"{path}/@{name}"][value] += 1

        titles = direct_children(root, "title")
        title_cardinality[len(titles)] += 1
        has_main_title = False
        for title in titles:
            signature = title_signature(title)
            title_signatures[signature] += 1
            title_text_by_signature[signature][normalized_text(title) or "(empty)"] += 1
            has_main_title |= attribute_value(title, "type") == "main"
        records_with_main_title += has_main_title

        for contributor_tag in ("author", "editor"):
            contributors = direct_children(root, contributor_tag)
            contributor_cardinality[contributor_tag][len(contributors)] += 1
            for contributor in contributors:
                contributor_shapes[contributor_tag][contributor_shape(contributor)] += 1
                for name in attributes(contributor):
                    contributor_attribute_presence[contributor_tag][name] += 1
                value = normalized_text(contributor) or "(empty)"
                contributor_name_values[contributor_tag][value] += 1

        dates = direct_children(root, "date")
        date_cardinality[len(dates)] += 1
        for date in dates:
            value = normalized_text(date) or "(empty)"
            date_values[value] += 1
            for name in attributes(date):
                date_attribute_presence[name] += 1
            match = YEAR_PATTERN.search(value)
            if match is None:
                date_unparsed_values[value] += 1
            else:
                date_years[int(match.group("year"))] += 1

        bibl_scopes = direct_children(root, "biblScope")
        bibl_scope_cardinality[len(bibl_scopes)] += 1
        for scope in bibl_scopes:
            scope_type = attribute_value(scope, "type", "(none)") or "(none)"
            bibl_scope_types[scope_type] += 1
            value = normalized_text(scope) or "(empty)"
            bibl_scope_values_by_type[scope_type][value] += 1
            if attribute_value(scope, "from") or attribute_value(scope, "to"):
                bibl_scope_with_from_to[scope_type] += 1
            for name in attributes(scope):
                bibl_scope_attribute_presence[name] += 1

        related_items = direct_children(root, "relatedItem")
        related_item_cardinality[len(related_items)] += 1
        for related_item in related_items:
            attrs = attributes(related_item)
            relation_type = attrs.get("type", "(none)")
            related_item_types[relation_type] += 1
            for name in attrs:
                related_item_attribute_presence[name] += 1

            nested_ptrs = iter_descendants(related_item, "ptr")
            if not nested_ptrs:
                related_item_target_state["no_ptr"] += 1
            for ptr in nested_ptrs:
                target = attribute_value(ptr, "target", "") or ""
                kind = target_kind(target)
                ptr_targets[target] += 1
                ptr_target_kinds[kind] += 1
                ptr_target_documents[target].add(biblio_id)
                related_item_targets_by_type[relation_type][kind] += 1
                match = BIBLIO_TARGET_PATTERN.search(target)
                if match is None:
                    related_item_target_state["non_biblio_ptr"] += 1
                else:
                    related_item_target_state["biblio_ptr"] += 1
                    related_item_biblio_targets[relation_type][match.group("id")] += 1

            for nested_bibl in iter_descendants(related_item, "bibl"):
                nested_direct_counts = Counter(
                    local_name(child.name) for child in xml_direct_children(nested_bibl)
                )
                for child_name in nested_direct_counts:
                    related_item_nested_child_presence[relation_type][child_name] += 1
                for nested_title in direct_children(nested_bibl, "title"):
                    related_item_nested_title_signatures[relation_type][
                        title_signature(nested_title)
                    ] += 1

        for idno in direct_children(root, "idno"):
            idno_type = attribute_value(idno, "type", "(none)") or "(none)"
            value = normalized_text(idno) or "(empty)"
            idno_types[idno_type] += 1
            idno_values_by_type[idno_type][value] += 1

        notes = direct_children(root, "note")
        note_cardinality[len(notes)] += 1
        for note in notes:
            note_type = attribute_value(note, "type", "(none)") or "(none)"
            note_types[note_type] += 1
            note_values_by_type[note_type][normalized_text(note) or "(empty)"] += 1

        segments = direct_children(root, "seg")
        seg_cardinality[len(segments)] += 1
        for segment in segments:
            attrs = attributes(segment)
            seg_types[attrs.get("type", "(none)")] += 1
            seg_subtypes[attrs.get("subtype", "(none)")] += 1
            seg_resp[attrs.get("resp", "(none)")] += 1
            text_length = len(normalized_text(segment))
            if text_length == 0:
                bucket = "empty"
            elif text_length <= 100:
                bucket = "1-100"
            elif text_length <= 250:
                bucket = "101-250"
            elif text_length <= 500:
                bucket = "251-500"
            else:
                bucket = "more than 500"
            seg_text_length_buckets[bucket] += 1

    path_summary = {
        path: {
            "records": len(element_presence[path]),
            "occurrences": count,
        }
        for path, count in sorted(element_paths.items(), key=lambda item: item[0])
    }
    attribute_summary = {
        path: {
            "occurrences": count,
            "distinct_values": len(attribute_values[path]),
            "top_values": top_counter(attribute_values[path], 20),
        }
        for path, count in sorted(attribute_presence.items(), key=lambda item: item[0])
    }
    date_year_list = sorted(date_years)

    result: dict[str, object] = {
        "corpus": {
            "biblio_root": str(biblio_root),
            "xml_files": len(files),
            "parsed_files": len(files) - len(parse_errors),
            "parse_errors": parse_errors,
            "distinct_biblio_ids": len(ids),
            "duplicate_biblio_ids": sorted_counter(duplicate_ids),
            "directory_buckets": len({path.parent.name for path in files}),
        },
        "identity": {
            "consistency": sorted_counter(id_consistency),
            "idno_types": sorted_counter(idno_types),
            "top_idno_values_by_type": {
                name: top_counter(values, 20)
                for name, values in sorted(idno_values_by_type.items())
            },
        },
        "root": {
            "type": sorted_counter(root_type),
            "subtype": sorted_counter(root_subtype),
            "xml_lang": sorted_counter(root_language),
            "attribute_presence": sorted_counter(root_attribute_presence),
            "attribute_combinations": {
                ", ".join(combination) or "(none)": count
                for combination, count in sorted(
                    root_attribute_combinations.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            },
            "direct_child_presence": sorted_counter(root_child_presence),
            "direct_child_occurrences": sorted_counter(root_child_occurrences),
            "direct_child_cardinality": {
                name: summarize_cardinality(values)
                for name, values in sorted(root_child_cardinality.items())
            },
        },
        "titles": {
            "records_with_main_title": records_with_main_title,
            "cardinality": summarize_cardinality(title_cardinality),
            "signatures": sorted_counter(title_signatures),
            "top_values_by_signature": {
                signature: top_counter(values, 20)
                for signature, values in sorted(title_text_by_signature.items())
            },
        },
        "contributors": {
            tag: {
                "cardinality": summarize_cardinality(contributor_cardinality[tag]),
                "shapes": sorted_counter(contributor_shapes[tag]),
                "attribute_presence": sorted_counter(
                    contributor_attribute_presence[tag]
                ),
                "top_values": top_counter(contributor_name_values[tag], 30),
            }
            for tag in ("author", "editor")
        },
        "dates": {
            "cardinality": summarize_cardinality(date_cardinality),
            "values_top": top_counter(date_values, 30),
            "distinct_values": len(date_values),
            "attribute_presence": sorted_counter(date_attribute_presence),
            "year_min": min(date_year_list) if date_year_list else None,
            "year_max": max(date_year_list) if date_year_list else None,
            "top_years": top_counter(date_years, 30),
            "unparsed_values": top_counter(date_unparsed_values, 30),
        },
        "bibl_scopes": {
            "cardinality": summarize_cardinality(bibl_scope_cardinality),
            "types": sorted_counter(bibl_scope_types),
            "attribute_presence": sorted_counter(bibl_scope_attribute_presence),
            "types_with_from_or_to": sorted_counter(bibl_scope_with_from_to),
            "top_values_by_type": {
                name: top_counter(values, 20)
                for name, values in sorted(bibl_scope_values_by_type.items())
            },
        },
        "related_items": {
            "cardinality": summarize_cardinality(related_item_cardinality),
            "types": sorted_counter(related_item_types),
            "attribute_presence": sorted_counter(related_item_attribute_presence),
            "target_state": sorted_counter(related_item_target_state),
            "target_kinds": sorted_counter(ptr_target_kinds),
            "target_kinds_by_relation_type": {
                name: sorted_counter(values)
                for name, values in sorted(related_item_targets_by_type.items())
            },
            "distinct_targets": len(ptr_targets),
            "top_targets": top_counter(ptr_targets, 30),
            "top_biblio_targets_by_relation_type": {
                name: top_counter(values, 20)
                for name, values in sorted(related_item_biblio_targets.items())
            },
            "nested_child_presence_by_relation_type": {
                name: sorted_counter(values)
                for name, values in sorted(related_item_nested_child_presence.items())
            },
            "nested_title_signatures_by_relation_type": {
                name: sorted_counter(values)
                for name, values in sorted(related_item_nested_title_signatures.items())
            },
            "target_document_counts_top": {
                target: len(ptr_target_documents[target])
                for target, _ in ptr_targets.most_common(30)
            },
        },
        "notes": {
            "cardinality": summarize_cardinality(note_cardinality),
            "types": sorted_counter(note_types),
            "top_values_by_type": {
                name: top_counter(values, 20)
                for name, values in sorted(note_values_by_type.items())
            },
        },
        "segments": {
            "cardinality": summarize_cardinality(seg_cardinality),
            "types": sorted_counter(seg_types),
            "subtypes": sorted_counter(seg_subtypes),
            "resp": sorted_counter(seg_resp),
            "text_length_buckets": sorted_counter(seg_text_length_buckets),
        },
        "element_paths": path_summary,
        "attribute_paths": attribute_summary,
    }

    if idp_data is not None:
        result["hgv_references"] = analyze_hgv_references(
            idp_data,
            ids,
            progress=progress,
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "biblio_root", nargs="?", type=Path, default=Path("idp.data/Biblio")
    )
    parser.add_argument("--idp-data", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-progress", action="store_true")
    arguments = parser.parse_args()

    result = analyze(
        arguments.biblio_root,
        idp_data=arguments.idp_data,
        progress=not arguments.no_progress,
    )
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if arguments.output is None:
        print(text)
    else:
        arguments.output.write_text(f"{text}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
