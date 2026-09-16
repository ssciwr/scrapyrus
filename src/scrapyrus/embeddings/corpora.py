"""Source adapters and the single registry of supported embedding corpora.

Adapters own record shape and source-specific SQL. The store owns the model
client and coordinates ingestion, queries, indexing, and export for every corpus.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Any, Callable

import psycopg
from psycopg import sql

from scrapyrus.embeddings.schema import (
    SourceUnavailableError,
    cosine_distance,
    row_value,
    vector_literal,
)
from scrapyrus.embeddings.semantics import (
    KEYWORD_EMBEDDINGS_SEMANTICS,
    TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
    TRANSLATION_EMBEDDINGS_SEMANTICS,
)
from scrapyrus.semantics import TableSemantics
from scrapyrus.transcriptions.core import (
    MAXIMUM_TRANSCRIPTION_OPTIONS,
    TRANSCRIPTIONS_TABLE,
    epidoc_xml_to_text,
    transcription_language,
    translation_epidoc_xml_to_text,
)


@dataclass(frozen=True)
class KeywordMatch:
    """A keyword and optional qualifier ranked by cosine similarity."""

    keyword: str
    similarity: float


@dataclass(frozen=True)
class DocumentMatch:
    """A source document represented by its closest embedding chunk."""

    source_path: str
    tm_id: str
    language: str | None
    document_text: str
    similarity: float


@dataclass(frozen=True)
class EmbeddingInput:
    """Text to embed and the source fields stored alongside its vector."""

    text: str
    values: dict[str, Any]


@dataclass(frozen=True)
class CorpusInputs:
    """Prepared inputs and the source IDs defining a sampled cleanup scope."""

    records: tuple[EmbeddingInput, ...]
    scope_ids: tuple[int, ...] | None = None


@dataclass(frozen=True)
class EmbeddingCorpus(ABC):
    """Describe a corpus's table and implement its source-specific operations."""

    name: str
    table_name: str
    semantics: TableSemantics

    @property
    @abstractmethod
    def record_columns(self) -> tuple[str, ...]:
        """Source columns written with each embedding."""

    @property
    @abstractmethod
    def key_columns(self) -> tuple[str, ...]:
        """Columns identifying a record within the corpus table."""

    @property
    def export_columns(self) -> tuple[str, ...]:
        return (*self.record_columns, "embedding", "updated_at")

    @property
    def export_order(self) -> tuple[str, ...]:
        return self.key_columns

    @abstractmethod
    def create_schema(self, cursor: Any) -> None:
        """Create this corpus's embedding table."""

    @abstractmethod
    def read_inputs(
        self, cursor: Any, *, chunk_size: int, sample: int | None, seed: int
    ) -> CorpusInputs:
        """Prepare source records, including any corpus-specific chunking."""

    @abstractmethod
    def is_current(self, cursor: Any, record: EmbeddingInput) -> bool:
        """Compare a prepared input against its stored source fields."""

    def write_embeddings(
        self,
        cursor: Any,
        records: list[tuple[EmbeddingInput, tuple[float, ...]]],
    ) -> None:
        """Upsert source fields and vectors using this corpus's record keys."""

        columns = (*self.record_columns, "embedding")
        keys = self.key_columns
        assignments = [
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
            for c in columns
            if c not in keys
        ]
        statement = sql.SQL(
            "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}, "
            "updated_at = now()"
        ).format(
            sql.Identifier(self.table_name),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(
                sql.SQL("{}::vector").format(sql.Placeholder(c))
                if c == "embedding"
                else sql.Placeholder(c)
                for c in columns
            ),
            sql.SQL(", ").join(map(sql.Identifier, keys)),
            sql.SQL(", ").join(assignments),
        )
        for record, embedding in records:
            cursor.execute(
                statement,
                {
                    **record.values,
                    "embedding": vector_literal(embedding),
                },
            )

    @abstractmethod
    def remove_stale(self, cursor: Any, inputs: CorpusInputs) -> None:
        """Remove missing source records and surplus chunks."""

    @abstractmethod
    def query_matches(
        self, cursor: Any, embedding: tuple[float, ...], top_k: int
    ) -> tuple[KeywordMatch, ...] | tuple[DocumentMatch, ...]:
        """Rank vectors and shape this corpus's public query results."""

    @abstractmethod
    def validate_import(self, cursor: Any, temporary_table: str) -> None:
        """Require imported identities to belong to this corpus's source data."""


@dataclass(frozen=True)
class KeywordCorpus(EmbeddingCorpus):
    """Embed one distinct keyword/qualifier string."""

    @property
    def record_columns(self) -> tuple[str, ...]:
        return ("keyword",)

    @property
    def key_columns(self) -> tuple[str, ...]:
        return ("keyword",)

    def create_schema(self, cursor: Any) -> None:
        cursor.execute(
            sql.SQL("""
CREATE TABLE IF NOT EXISTS {} (
    keyword text NOT NULL,
    embedding vector NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword)
)
""").format(sql.Identifier(self.table_name))
        )

    def read_inputs(
        self, cursor: Any, *, chunk_size: int, sample: int | None, seed: int
    ) -> CorpusInputs:
        if sample is not None:
            raise ValueError("Keyword embeddings do not support XML record sampling")
        try:
            cursor.execute("""
SELECT DISTINCT CASE WHEN qualifier IS NULL THEN keyword
                     ELSE keyword || ', ' || qualifier END AS embedding_keyword
FROM keywords WHERE keyword IS NOT NULL ORDER BY embedding_keyword
""")
        except psycopg.errors.UndefinedTable as error:
            raise SourceUnavailableError(
                "PostgreSQL table 'keywords' does not exist. Run "
                "'scrapyrus metadata ingest' before creating keyword embeddings."
            ) from error
        terms = tuple(
            str(row_value(r, "embedding_keyword", 0)) for r in cursor.fetchall()
        )
        return CorpusInputs(
            tuple(EmbeddingInput(term, {"keyword": term}) for term in terms)
        )

    def validate_import(self, cursor: Any, temporary_table: str) -> None:
        cursor.execute(
            sql.SQL(
                "SELECT count(*) FROM {} AS imported WHERE NOT EXISTS ("
                "SELECT 1 FROM keywords AS source WHERE "
                "CASE WHEN source.qualifier IS NULL THEN source.keyword ELSE "
                "source.keyword || ', ' || source.qualifier END = imported.keyword)"
            ).format(sql.Identifier(temporary_table))
        )
        if int(row_value(cursor.fetchone(), "count", 0)):
            raise ValueError(
                "Embedding dump contains rows without matching keyword source data"
            )

    def is_current(self, cursor: Any, record: EmbeddingInput) -> bool:
        cursor.execute(
            sql.SQL("SELECT 1 FROM {} WHERE keyword = %s").format(
                sql.Identifier(self.table_name)
            ),
            (record.values["keyword"],),
        )
        return cursor.fetchone() is not None

    def remove_stale(self, cursor: Any, inputs: CorpusInputs) -> None:
        cursor.execute(
            sql.SQL("DELETE FROM {} WHERE NOT (keyword = ANY(%s))").format(
                sql.Identifier(self.table_name)
            ),
            ([r.values["keyword"] for r in inputs.records],),
        )

    def query_matches(
        self, cursor: Any, embedding: tuple[float, ...], top_k: int
    ) -> tuple[KeywordMatch, ...]:
        cursor.execute(
            sql.SQL(
                "SELECT keyword, 1 - ({distance}) AS similarity FROM {table} "
                "ORDER BY {distance}, keyword LIMIT {limit}"
            ).format(
                distance=cosine_distance(len(embedding)),
                table=sql.Identifier(self.table_name),
                limit=sql.Placeholder("top_k"),
            ),
            {
                "embedding": vector_literal(embedding),
                "top_k": top_k,
            },
        )
        return tuple(
            KeywordMatch(
                str(row_value(r, "keyword", 0)), float(row_value(r, "similarity", 1))
            )
            for r in cursor.fetchall()
        )


@dataclass(frozen=True)
class XmlCorpus(EmbeddingCorpus):
    """Convert one XML source type into chunks and rank whole documents."""

    source_type: str
    text_converter: Callable[[str], str]
    language_reader: Callable[[str], str | None] | None = None

    @property
    def record_columns(self) -> tuple[str, ...]:
        return (
            "chunk_id",
            "xml_id",
            "chunk_index",
            "source_path",
            "tm_id",
            "language",
            "document_text",
            "input_hash",
        )

    @property
    def key_columns(self) -> tuple[str, ...]:
        return ("xml_id", "chunk_index")

    def create_schema(self, cursor: Any) -> None:
        cursor.execute(
            sql.SQL("""
CREATE TABLE IF NOT EXISTS {} (
    chunk_id text NOT NULL UNIQUE,
    xml_id bigint NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    source_path text NOT NULL,
    tm_id text NOT NULL,
    language text,
    document_text text NOT NULL,
    input_hash text NOT NULL,
    embedding vector NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (xml_id, chunk_index),
    CHECK (chunk_id = {} || ':' || xml_id::text || ':' || chunk_index::text)
)
""").format(sql.Identifier(self.table_name), sql.Literal(self.name))
        )

    def read_inputs(
        self, cursor: Any, *, chunk_size: int, sample: int | None, seed: int
    ) -> CorpusInputs:
        try:
            sources = self.read_sources(cursor, sample=sample, seed=seed)
        except psycopg.errors.UndefinedTable as error:
            raise SourceUnavailableError(
                f"PostgreSQL table {TRANSCRIPTIONS_TABLE!r} does not exist. Run "
                "'scrapyrus transcriptions ingest' before creating XML embeddings."
            ) from error
        records = []
        for source in sources:
            xml = str(source["xml_content"])
            text = self.text_converter(xml)
            if not text.strip():
                continue
            language = (
                self.language_reader(xml)
                if self.language_reader
                else source["language"]
            )
            for index, chunk in enumerate(chunk_text(text, chunk_size)):
                records.append(
                    EmbeddingInput(
                        chunk,
                        {
                            "chunk_id": f"{self.name}:{int(source['transcription_id'])}:{index}",
                            "xml_id": int(source["transcription_id"]),
                            "chunk_index": index,
                            "source_path": str(source["source_path"]),
                            "tm_id": str(source["tm_id"]),
                            "language": language,
                            "document_text": chunk,
                            "input_hash": hashlib.sha256(
                                chunk.encode("utf-8")
                            ).hexdigest(),
                        },
                    )
                )
        return CorpusInputs(
            tuple(records),
            tuple(int(s["transcription_id"]) for s in sources)
            if sample is not None
            else None,
        )

    def read_sources(
        self, cursor: Any, *, sample: int | None = None, seed: int = 0
    ) -> tuple[dict[str, Any], ...]:
        """Read all XML rows, or sample records having both XML source types."""

        if sample is None:
            cursor.execute(
                f"""
SELECT transcription_id, source_path, tm_id, xml_content::text, type, language
FROM {TRANSCRIPTIONS_TABLE} WHERE type = %s ORDER BY transcription_id
""",
                (self.source_type,),
            )
        else:
            cursor.execute(
                f"""
WITH sampled_records AS (
    SELECT tm_id FROM {TRANSCRIPTIONS_TABLE} GROUP BY tm_id
    HAVING bool_or(type = 'transcription') AND bool_or(type = 'translation')
    ORDER BY md5(tm_id::text || ':' || (%s)::text), tm_id LIMIT %s
)
SELECT transcription_id, source_path, tm_id, xml_content::text, type, language
FROM {TRANSCRIPTIONS_TABLE} JOIN sampled_records USING (tm_id)
WHERE type = %s ORDER BY transcription_id
""",
                (seed, sample, self.source_type),
            )
        keys = (
            "transcription_id",
            "source_path",
            "tm_id",
            "xml_content",
            "type",
            "language",
        )
        return tuple(
            r if isinstance(r, dict) else dict(zip(keys, r, strict=True))
            for r in cursor.fetchall()
        )

    def validate_import(self, cursor: Any, temporary_table: str) -> None:
        cursor.execute(
            sql.SQL(
                "SELECT count(*) FROM {} AS imported WHERE NOT EXISTS ("
                "SELECT 1 FROM transcriptions AS source WHERE "
                "source.transcription_id = imported.xml_id AND source.type = %s "
                "AND source.source_path = imported.source_path "
                "AND source.tm_id::text = imported.tm_id) "
                "OR imported.input_hash <> encode(sha256(convert_to(imported.document_text, 'UTF8')), 'hex')"
            ).format(sql.Identifier(temporary_table)),
            (self.source_type,),
        )
        if int(row_value(cursor.fetchone(), "count", 0)):
            raise ValueError(
                "Embedding dump contains invalid chunks or rows without matching XML source data"
            )

    def is_current(self, cursor: Any, record: EmbeddingInput) -> bool:
        cursor.execute(
            sql.SQL(
                "SELECT input_hash, source_path, tm_id, language FROM {} "
                "WHERE xml_id = %s AND chunk_index = %s"
            ).format(sql.Identifier(self.table_name)),
            (record.values["xml_id"], record.values["chunk_index"]),
        )
        row = cursor.fetchone()
        columns = ("input_hash", "source_path", "tm_id", "language")
        return row is not None and tuple(
            row_value(row, c, i) for i, c in enumerate(columns)
        ) == tuple(record.values[c] for c in columns)

    def remove_stale(self, cursor: Any, inputs: CorpusInputs) -> None:
        chunk_counts: dict[int, int] = {}
        for record in inputs.records:
            xml_id = record.values["xml_id"]
            chunk_counts[xml_id] = max(
                chunk_counts.get(xml_id, 0), record.values["chunk_index"] + 1
            )
        scope = (
            sql.SQL(" AND xml_id = ANY(%s)")
            if inputs.scope_ids is not None
            else sql.SQL("")
        )
        cursor.execute(
            sql.SQL("DELETE FROM {} WHERE NOT (xml_id = ANY(%s)){}").format(
                sql.Identifier(self.table_name), scope
            ),
            (sorted(chunk_counts), list(inputs.scope_ids))
            if inputs.scope_ids is not None
            else (sorted(chunk_counts),),
        )
        for xml_id, count in chunk_counts.items():
            cursor.execute(
                sql.SQL(
                    "DELETE FROM {} WHERE xml_id = %s AND chunk_index >= %s"
                ).format(sql.Identifier(self.table_name)),
                (xml_id, count),
            )

    def query_matches(
        self, cursor: Any, embedding: tuple[float, ...], top_k: int
    ) -> tuple[DocumentMatch, ...]:
        cursor.execute(
            sql.SQL(
                "WITH ranked_chunks AS ("
                "SELECT xml_id, source_path, tm_id, language, document_text, chunk_index, "
                "1 - ({distance}) AS similarity, "
                "row_number() OVER (PARTITION BY xml_id ORDER BY {distance}, chunk_index) "
                "AS chunk_rank FROM {table}"
                ") SELECT source_path, tm_id, language, document_text, similarity "
                "FROM ranked_chunks WHERE chunk_rank = 1 "
                "ORDER BY similarity DESC, source_path, tm_id, xml_id LIMIT {limit}"
            ).format(
                distance=cosine_distance(len(embedding)),
                table=sql.Identifier(self.table_name),
                limit=sql.Placeholder("top_k"),
            ),
            {
                "embedding": vector_literal(embedding),
                "top_k": top_k,
            },
        )
        return tuple(
            DocumentMatch(
                str(row_value(r, "source_path", 0)),
                str(row_value(r, "tm_id", 1)),
                row_value(r, "language", 2),
                str(row_value(r, "document_text", 3)),
                float(row_value(r, "similarity", 4)),
            )
            for r in cursor.fetchall()
        )


def chunk_text(text: str, chunk_size: int = 500) -> tuple[str, ...]:
    """Split text into deterministic word chunks with ten-percent overlap."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    words = text.split()
    if len(words) <= chunk_size:
        return (text,)
    chunks = []
    start = 0
    while True:
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            return tuple(chunks)
        start += chunk_size - chunk_size // 10


EMBEDDING_CORPORA = MappingProxyType(
    {
        "transcriptions": XmlCorpus(
            "transcriptions",
            "transcription_embeddings",
            TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
            source_type="transcription",
            text_converter=partial(epidoc_xml_to_text, **MAXIMUM_TRANSCRIPTION_OPTIONS),
            language_reader=transcription_language,
        ),
        "translations": XmlCorpus(
            "translations",
            "translation_embeddings",
            TRANSLATION_EMBEDDINGS_SEMANTICS,
            source_type="translation",
            text_converter=translation_epidoc_xml_to_text,
        ),
        "keywords": KeywordCorpus(
            "keywords", "keyword_embeddings", KEYWORD_EMBEDDINGS_SEMANTICS
        ),
    }
)
