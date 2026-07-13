import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    optional_string,
    publication_idno_string,
)


ORIG_DATE_NODES_XPATH = ".//tei:origDate"
DATE_ATTRIBUTE_RE = re.compile(
    r"^(?P<year>-?\d{4,})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?$"
)


def _date_parts(value: str) -> tuple[int, int | None, int | None]:
    match = DATE_ATTRIBUTE_RE.match(value)
    if match is None:
        raise ValueError(f"Unsupported origDate attribute value: {value!r}")

    return (
        int(match.group("year")),
        int(match.group("month")) if match.group("month") is not None else None,
        int(match.group("day")) if match.group("day") is not None else None,
    )


def _is_alternative(xml_id: str | None) -> bool:
    return xml_id is not None and xml_id.startswith("dateAlternative")


class OrigDateModel(BaseModel):
    date_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    date_text: str
    certainty: Optional[Literal["low", "medium"]] = None
    precision: Optional[Literal["low", "medium"]] = None
    not_before_year: Optional[int] = Field(gt=-10000, lt=2500, default=None)
    not_before_month: Optional[int] = Field(ge=1, le=12, default=None)
    not_before_day: Optional[int] = Field(ge=1, le=31, default=None)
    not_after_year: Optional[int] = Field(gt=-10000, lt=2500, default=None)
    not_after_month: Optional[int] = Field(ge=1, le=12, default=None)
    not_after_day: Optional[int] = Field(ge=1, le=31, default=None)
    alternative: bool = False


ORIG_DATES_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS orig_dates (
    date_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    date_text text NOT NULL,
    certainty text,
    precision text,
    not_before_year integer,
    not_before_month integer,
    not_before_day integer,
    not_after_year integer,
    not_after_month integer,
    not_after_day integer,
    alternative boolean NOT NULL
);"""

ORIG_DATES_DESCRIPTION = """The orig_dates table contains one row for each original-date element with a
machine-readable date or date range. It stores the source date text, parsed
not-before and not-after bounds, certainty and precision markers, and whether
the row represents an alternative dating."""

ORIG_DATES_SEMANTIC_CATALOG = """Table: orig_dates
Use this table for chronological queries about when a papyrus was written, composed, or dated. Join to papyri on tm_id.
date_id: Synthetic row identifier for an extracted date statement; not an external date ID.
tm_id: Trismegistos document ID for the papyrus record with this date.
date_text: Human-readable date expression from the source metadata, such as a century, reign, or exact date label.
certainty: Source confidence marker for the date assignment; low or medium values mean the date is less certain.
precision: Source precision marker for how exact the date assignment is; low or medium values mean broader or less precise dating.
not_before_year: Earliest possible year for the date range; negative values encode BCE years from TEI date attributes.
not_before_month: Earliest possible month when the lower bound includes month precision.
not_before_day: Earliest possible day when the lower bound includes day precision.
not_after_year: Latest possible year for the date range; use together with not_before_year for interval queries.
not_after_month: Latest possible month when the upper bound includes month precision.
not_after_day: Latest possible day when the upper bound includes day precision.
alternative: True when the source marks this as an alternative date; prefer alternative = false for primary dating unless alternatives are requested."""


class OrigDateModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_date_id = 1

        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.date_nodes_proc = proc.new_xpath_processor()
        self.date_nodes_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        self.date_value_proc = proc.new_xpath_processor()
        self.date_value_proc.declare_namespace(
            "xml", "http://www.w3.org/XML/1998/namespace"
        )

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)
        tm_id = self.tm_id_proc(data)

        self.date_nodes_proc.set_context(xdm_item=data)
        date_nodes = self.date_nodes_proc.evaluate(ORIG_DATE_NODES_XPATH)
        if date_nodes is None:
            return []

        return [
            model
            for date_node in date_nodes
            if (model := self._parse_date(tm_id, date_node)) is not None
        ]

    def _parse_date(self, tm_id, date_node):
        self.date_value_proc.set_context(xdm_item=date_node)

        when = self._date_attribute("when", "when-custom")
        if when is not None:
            not_before = when
            not_after = when
        else:
            not_before = self._date_attribute("notBefore")
            not_after = self._date_attribute("notAfter")

        if not_before is None and not_after is None:
            return None

        if not_before is None:
            not_before = (None, None, None)
        if not_after is None:
            not_after = (None, None, None)

        return OrigDateModel(
            date_id=self.next_date_id(),
            tm_id=tm_id,
            date_text=self._node_string("normalize-space(.)") or "",
            certainty=self._node_string("string((@cert)[1])"),
            precision=self._node_string("string((@precision)[1])"),
            not_before_year=not_before[0],
            not_before_month=not_before[1],
            not_before_day=not_before[2],
            not_after_year=not_after[0],
            not_after_month=not_after[1],
            not_after_day=not_after[2],
            alternative=_is_alternative(self._node_string("string((@xml:id)[1])")),
        )

    def _node_string(self, expression):
        return optional_string(self.date_value_proc.evaluate_single(expression))

    def _date_attribute(self, *attribute_names):
        for attribute_name in attribute_names:
            value = self._node_string(f"string((@{attribute_name})[1])")
            if value is not None:
                return _date_parts(value)

        return None

    def next_date_id(self):
        date_id = self._next_date_id
        self._next_date_id += 1
        return date_id


class OrigDateMetadataTable(MetadataTable):
    name = "orig_dates"
    order_by = ("date_id",)
    schema_sql = ORIG_DATES_SCHEMA_SQL

    def description(self) -> str:
        return ORIG_DATES_DESCRIPTION

    def semantic_catalog(self) -> str:
        return ORIG_DATES_SEMANTIC_CATALOG

    @property
    def model_class(self) -> type[OrigDateModel]:
        return OrigDateModel

    def create_factory(self, proc):
        return OrigDateModelFactory(proc)

    def build_rows(
        self, factory: OrigDateModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
