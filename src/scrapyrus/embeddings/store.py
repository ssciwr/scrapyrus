"""A corpus-bound store coordinating the shared embedding lifecycle."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import psycopg
from psycopg import sql
from tqdm import tqdm

from scrapyrus.embeddings.clients import (
    embedding_error_message,
    is_skippable_embedding_error,
)
from scrapyrus.embeddings.corpora import (
    EMBEDDING_CORPORA,
    DocumentMatch,
    EmbeddingInput,
    KeywordMatch,
)
from scrapyrus.embeddings.schema import (
    drop_embedding_index,
    embedding_stats,
    ensure_schema,
    imported_embedding_stats,
    imported_model_names,
    recreate_embedding_index,
)


class Embeddings(Protocol):
    """Client interface shared by ingestion and free-text queries."""

    def embed_documents(self, texts: list[str]) -> Sequence[Sequence[float]]: ...

    def embed_query(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class EmbeddingSpecification:
    """Identify the model used for a store's source and query vectors."""

    model_name: str

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise ValueError("model_name must not be blank")


class EmbeddingStore:
    """Use one corpus, model specification, and reusable client for all operations.

    A client is required for ingestion and querying. File transfer, retrieval,
    and deletion can operate with just the corpus and model specification.
    """

    def __init__(
        self,
        *,
        corpus: str,
        specification: EmbeddingSpecification,
        client: Embeddings | None = None,
    ) -> None:
        try:
            self.corpus = EMBEDDING_CORPORA[corpus]
        except KeyError:
            raise ValueError(
                f"Unknown embedding corpus {corpus!r}. Expected one of: "
                f"{', '.join(EMBEDDING_CORPORA)}"
            ) from None
        self.specification = specification
        self.client = client

    def _require_client(self) -> Embeddings:
        if self.client is None:
            raise ValueError(
                "An embedding client is required for ingestion and querying"
            )
        return self.client

    @staticmethod
    def _validate_vector(
        vector: Sequence[float], dimensions: int | None
    ) -> tuple[float, ...]:
        embedding = tuple(float(value) for value in vector)
        if not embedding or not all(math.isfinite(v) for v in embedding):
            raise ValueError(
                "Embeddings must contain finite values and must not be empty"
            )
        if dimensions is not None and len(embedding) != dimensions:
            raise ValueError(
                f"Embedding has {len(embedding)} dimensions, but expected {dimensions}"
            )
        return embedding

    def ingest(
        self,
        conninfo: str = "",
        *,
        stale_only: bool = False,
        progressbar: bool = True,
        chunk_size: int = 500,
        sample: int | None = None,
        seed: int = 0,
    ) -> int:
        """Prepare inputs, embed changed records, and remove stale source rows.

        Existing vector dimensions constrain new vectors, including incremental
        updates. A sampled XML ingestion cleans up only its selected source IDs.
        """

        client = self._require_client()
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        if sample is not None and sample < 1:
            raise ValueError("sample must be at least 1")
        model_name = self.specification.model_name
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor, EMBEDDING_CORPORA.values())
                inputs = self.corpus.read_inputs(
                    cursor,
                    chunk_size=chunk_size,
                    sample=sample,
                    seed=seed,
                )
                _, dimensions = embedding_stats(cursor, self.corpus, model_name)
                pending = [
                    record
                    for record in inputs.records
                    if not stale_only
                    or not self.corpus.is_current(cursor, model_name, record)
                ]
                embedded: list[tuple[EmbeddingInput, tuple[float, ...]]] = []
                records = (
                    tqdm(pending, unit="input", desc=f"Embedding {self.corpus.name}")
                    if progressbar
                    else pending
                )
                try:
                    for record in records:
                        try:
                            vectors = client.embed_documents([record.text])
                        except Exception as error:
                            if not is_skippable_embedding_error(error):
                                raise
                            key = {
                                name: record.values[name]
                                for name in self.corpus.key_columns
                            }
                            print(
                                f"Skipping {self.corpus.name} embedding {key!r} for model "
                                f"{model_name!r} after context-length validation error: "
                                f"{embedding_error_message(error)}",
                                flush=True,
                            )
                            continue
                        if len(vectors) != 1:
                            raise ValueError(
                                "Embedding client must return one vector per input"
                            )
                        vector = self._validate_vector(vectors[0], dimensions)
                        if dimensions is None:
                            dimensions = len(vector)
                        embedded.append((record, vector))
                finally:
                    if progressbar:
                        records.close()
                self.corpus.write_embeddings(cursor, model_name, embedded)
                self.corpus.remove_stale(cursor, model_name, inputs)
                if dimensions is not None:
                    recreate_embedding_index(
                        cursor, self.corpus.table_name, model_name, dimensions
                    )
        return len(embedded)

    def query(
        self,
        text: str,
        conninfo: str = "",
        *,
        top_k: int = 10,
    ) -> tuple[KeywordMatch, ...] | tuple[DocumentMatch, ...]:
        """Embed free text with the bound client and rank the corpus's records."""

        if not text.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        client = self._require_client()
        model_name = self.specification.model_name
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                count, dimensions = embedding_stats(cursor, self.corpus, model_name)
                if count == 0:
                    raise ValueError(
                        f"No {self.corpus.name} embeddings found for model {model_name!r}. "
                        f"Run 'scrapyrus embeddings ingest {self.corpus.name}' with the same model first."
                    )
                vector = self._validate_vector(client.embed_query(text), dimensions)
                return self.corpus.query_matches(cursor, model_name, vector, top_k)

    def delete(self, conninfo: str = "") -> int:
        """Delete this model's vectors and index from the bound corpus."""

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor, EMBEDDING_CORPORA.values())
                drop_embedding_index(
                    cursor, self.corpus.table_name, self.specification.model_name
                )
                cursor.execute(
                    sql.SQL("DELETE FROM {} WHERE model_name = %s").format(
                        sql.Identifier(self.corpus.table_name)
                    ),
                    (self.specification.model_name,),
                )
                return max(cursor.rowcount, 0)

    def dump(self, target: str | Path, conninfo: str = "") -> int:
        """Export this model's corpus records using PostgreSQL binary COPY."""

        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        corpus = self.corpus
        columns = sql.SQL(", ").join(map(sql.Identifier, corpus.export_columns))
        ordering = sql.SQL(", ").join(map(sql.Identifier, corpus.export_order))
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor, EMBEDDING_CORPORA.values())
                count, _ = embedding_stats(
                    cursor, corpus, self.specification.model_name
                )
                with target.open("wb") as output:
                    with cursor.copy(
                        sql.SQL(
                            "COPY (SELECT {columns} FROM {table} WHERE model_name = {model} "
                            "ORDER BY {ordering}) TO STDOUT WITH (FORMAT binary)"
                        ).format(
                            columns=columns,
                            table=sql.Identifier(corpus.table_name),
                            model=sql.Literal(self.specification.model_name),
                            ordering=ordering,
                        )
                    ) as copy:
                        for chunk in copy:
                            output.write(chunk)
        return count

    def import_dump(self, source: str | Path, conninfo: str = "") -> int:
        """Validate and replace this model's corpus records from a binary dump."""

        corpus = self.corpus
        model_name = self.specification.model_name
        temporary_table = f"{corpus.table_name}_import"
        columns = sql.SQL(", ").join(map(sql.Identifier, corpus.export_columns))
        ordering = sql.SQL(", ").join(map(sql.Identifier, corpus.export_order))
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor, EMBEDDING_CORPORA.values())
                cursor.execute(
                    sql.SQL(
                        "CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP"
                    ).format(
                        sql.Identifier(temporary_table),
                        sql.Identifier(corpus.table_name),
                    )
                )
                with Path(source).open("rb") as input_file:
                    with cursor.copy(
                        sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT binary)").format(
                            sql.Identifier(temporary_table), columns
                        )
                    ) as copy:
                        while chunk := input_file.read(1024 * 1024):
                            copy.write(chunk)
                unexpected = [
                    m
                    for m in imported_model_names(cursor, temporary_table)
                    if m != model_name
                ]
                if unexpected:
                    raise ValueError(
                        f"Imported embeddings contain model names other than {model_name!r}: {', '.join(unexpected)}"
                    )
                count, dimensions = imported_embedding_stats(cursor, temporary_table)
                drop_embedding_index(cursor, corpus.table_name, model_name)
                cursor.execute(
                    sql.SQL("DELETE FROM {} WHERE model_name = %s").format(
                        sql.Identifier(corpus.table_name)
                    ),
                    (model_name,),
                )
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {table} ({columns}) SELECT {columns} FROM {temporary} ORDER BY {ordering}"
                    ).format(
                        table=sql.Identifier(corpus.table_name),
                        columns=columns,
                        temporary=sql.Identifier(temporary_table),
                        ordering=ordering,
                    )
                )
                if dimensions is not None:
                    recreate_embedding_index(
                        cursor, corpus.table_name, model_name, dimensions
                    )
        return count

    def retrieve(
        self, key: dict[str, object], conninfo: str = ""
    ) -> tuple[float, ...] | None:
        """Retrieve one vector using the bound corpus's exact record key."""

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                return self.corpus.retrieve(cursor, self.specification.model_name, key)
