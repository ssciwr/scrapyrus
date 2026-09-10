import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    optional_string,
    publication_idno_string,
)
from scrapyrus.semantics import ColumnSemantics, RelationshipSemantics, TableSemantics


KEYWORD_TERMS_XPATH = ".//tei:profileDesc/tei:textClass/tei:keywords/tei:term"
UNCERTAINTY_MARKER_RE = re.compile(r"\(\s*\?\s*\)|\?")
QUALIFIER_GROUP_RE = re.compile(r"^(?P<keyword>.*?)\s*\((?P<qualifiers>[^()]*)\)\s*$")


def _keyword_value(value: str) -> tuple[Optional[str], bool]:
    uncertain = "?" in value
    if uncertain:
        value = " ".join(UNCERTAINTY_MARKER_RE.sub("", value).split())

    value = value.strip()
    if value == "":
        return None, uncertain

    return value, uncertain


def _keyword_values(
    value: str,
) -> tuple[tuple[str, bool, Optional[str], bool], ...]:
    """Split a keyword and its final parenthesized qualifier list into rows."""

    value = " ".join(value.split())
    qualifier_group = QUALIFIER_GROUP_RE.fullmatch(value)
    if qualifier_group is None:
        keyword, uncertain = _keyword_value(value)
        if keyword is None:
            return ()
        return ((keyword, uncertain, None, False),)

    keyword, uncertain = _keyword_value(qualifier_group.group("keyword"))
    if keyword is None:
        return ()

    qualifiers: list[tuple[str, bool]] = []
    for value in qualifier_group.group("qualifiers").split(","):
        qualifier, qualifier_uncertain = _keyword_value(value.strip())
        if qualifier is None:
            uncertain = uncertain or qualifier_uncertain
        else:
            qualifiers.append((qualifier, qualifier_uncertain))

    if not qualifiers:
        return ((keyword, uncertain, None, False),)

    return tuple(
        (keyword, uncertain, qualifier, qualifier_uncertain)
        for qualifier, qualifier_uncertain in qualifiers
    )


class KeywordModel(BaseModel):
    keyword_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    scheme: Optional[str] = None
    keyword_type: Optional[str] = None
    keyword: Optional[str] = None
    uncertain: bool
    qualifier: Optional[str] = None
    qualifier_uncertain: bool = False


KEYWORDS_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS keywords (
    keyword_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    scheme text,
    keyword_type text,
    keyword text,
    uncertain boolean NOT NULL,
    qualifier text,
    qualifier_uncertain boolean NOT NULL
);"""

KEYWORDS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS keywords_tm_id_idx ON keywords (tm_id);"
)

KEYWORDS_SEMANTICS = TableSemantics(
    table_name="keywords",
    description=(
        "The keywords table contains normalized keyword and qualifier assignments "
        "with their source classification and uncertainty metadata."
    ),
    row_grain=(
        "One normalized keyword-qualifier assignment, or one keyword assignment "
        "when the source provides no qualifier."
    ),
    useful_for=("topics, genres, subjects, languages, and classifications",),
    columns={
        "keyword_id": ColumnSemantics(
            description="Synthetic extracted-keyword row identifier, not a stable external term ID."
        ),
        "tm_id": ColumnSemantics(
            description="Trismegistos document ID of the record assigned this keyword."
        ),
        "scheme": ColumnSemantics(
            description="Source keyword vocabulary or classification scheme from the TEI keywords element."
        ),
        "keyword_type": ColumnSemantics(
            description="Category or type of the keyword term from the source metadata."
        ),
        "keyword": ColumnSemantics(
            description="Cleaned keyword text after uncertainty markers are removed."
        ),
        "uncertain": ColumnSemantics(
            description="Whether the source marked the keyword with a question mark.",
            value_meanings={
                "true": "the keyword is uncertain",
                "false": "the source did not mark the keyword uncertain",
            },
        ),
        "qualifier": ColumnSemantics(
            description=(
                "One qualifier extracted from the keyword's final parenthesized "
                "comma-separated qualifier list."
            ),
            null_means="The keyword has no qualifier.",
        ),
        "qualifier_uncertain": ColumnSemantics(
            description="Whether the source marked this qualifier with a question mark.",
            value_meanings={
                "true": "the qualifier is uncertain",
                "false": "the source did not mark the qualifier uncertain",
            },
        ),
    },
    relationships=(
        RelationshipSemantics(
            target_table="papyri",
            source_columns=("tm_id",),
            target_columns=("tm_id",),
            cardinality="many-to-many",
            description="Logical, unenforced Trismegistos document-key join.",
        ),
    ),
)


class KeywordModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_keyword_id = 1

        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.term_nodes_proc = proc.new_xpath_processor()
        self.term_nodes_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        self.term_value_proc = proc.new_xpath_processor()

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)
        tm_id = self.tm_id_proc(data)

        self.term_nodes_proc.set_context(xdm_item=data)
        term_nodes = self.term_nodes_proc.evaluate(KEYWORD_TERMS_XPATH)
        if term_nodes is None:
            return []

        return [
            model
            for term_node in term_nodes
            for model in self._parse_term(tm_id, term_node)
        ]

    def _parse_term(self, tm_id, term_node):
        self.term_value_proc.set_context(xdm_item=term_node)
        keyword = optional_string(
            self.term_value_proc.evaluate_single("normalize-space(.)")
        )
        if keyword is None:
            return []
        scheme = optional_string(
            self.term_value_proc.evaluate_single("string((../@scheme)[1])")
        )
        keyword_type = optional_string(
            self.term_value_proc.evaluate_single("string((@type)[1])")
        )

        return [
            KeywordModel(
                keyword_id=self.next_keyword_id(),
                tm_id=tm_id,
                scheme=scheme,
                keyword_type=keyword_type,
                keyword=keyword,
                uncertain=uncertain,
                qualifier=qualifier,
                qualifier_uncertain=qualifier_uncertain,
            )
            for keyword, uncertain, qualifier, qualifier_uncertain in _keyword_values(
                keyword
            )
        ]

    def next_keyword_id(self):
        keyword_id = self._next_keyword_id
        self._next_keyword_id += 1
        return keyword_id


class KeywordMetadataTable(MetadataTable):
    name = "keywords"
    order_by = ("keyword_id",)
    schema_sql = KEYWORDS_SCHEMA_SQL
    semantics = KEYWORDS_SEMANTICS

    def index_sql(self) -> str:
        return KEYWORDS_INDEX_SQL

    @property
    def model_class(self) -> type[KeywordModel]:
        return KeywordModel

    def create_factory(self, proc):
        return KeywordModelFactory(proc)

    def build_rows(
        self, factory: KeywordModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
