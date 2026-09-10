"""A corpus-bound store coordinating the shared embedding lifecycle."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

from langchain_core.embeddings import Embeddings

import psycopg
from psycopg import sql
from tqdm import tqdm

from scrapyrus.embeddings.clients import (
    embed_documents_with_backoff,
    embed_query_with_backoff,
    embedding_error_message,
    embedding_request_batches,
    is_skippable_embedding_error,
)
from scrapyrus.embeddings.corpora import (
    EMBEDDING_CORPORA,
    DocumentMatch,
    EmbeddingInput,
    KeywordMatch,
)
from scrapyrus.embeddings.schema import (
    associate_embedding_specification,
    embedding_table_metadata,
    EmbeddingModelMismatchError,
    SourceUnavailableError,
    drop_embedding_index,
    embedding_stats,
    ensure_schema,
    imported_embedding_stats,
    recreate_embedding_index,
    require_embedding_specification,
    reset_embedding_columns,
    set_embedding_size,
)

from scrapyrus.embeddings.specification import EmbeddingSpecification
from scrapyrus.embeddings.manifest import load_manifest, write_manifest


class EmbeddingStore:
    """Use one corpus, model specification, and reusable client for all operations.

    A client is required for ingestion and querying. File transfer and deletion
    can operate with just the corpus and model specification.
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

    @classmethod
    def from_database(
        cls, *, corpus: str, model_name: str, conninfo: str = ""
    ) -> EmbeddingStore:
        """Bind transfer/deletion commands to the database's complete specification."""
        adapter = EMBEDDING_CORPORA[corpus]
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                metadata = embedding_table_metadata(cursor, adapter)
                if metadata is None:
                    raise ValueError(
                        f"No embedding specification is configured for {adapter.table_name!r}"
                    )
                if metadata.model_name != model_name:
                    raise EmbeddingModelMismatchError(
                        f"{adapter.table_name!r} uses embedding model {metadata.model_name!r}, not {model_name!r}"
                    )
        return cls(corpus=corpus, specification=metadata.specification)

    @classmethod
    def from_dump(
        cls, *, corpus: str, model_name: str, source: str | Path
    ) -> EmbeddingStore:
        """Bind an import to the required manifest's complete specification."""
        _, metadata = load_manifest(Path(source), EMBEDDING_CORPORA[corpus])
        if metadata.model_name != model_name:
            raise EmbeddingModelMismatchError(
                f"Embedding dump uses model {metadata.model_name!r}, not {model_name!r}"
            )
        return cls(corpus=corpus, specification=metadata.specification)

    def _require_client(self) -> Embeddings:
        """Return the configured embedding client or raise if unavailable."""
        if self.client is None:
            raise ValueError(
                "An embedding client is required for ingestion and querying"
            )
        return self.client

    @staticmethod
    def _validate_vector(
        vector: Sequence[float], dimensions: int | None
    ) -> tuple[float, ...]:
        """Convert a vector to finite floats and check its dimensions."""
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
        force: bool = False,
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
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor, EMBEDDING_CORPORA.values())
                metadata = associate_embedding_specification(
                    cursor, self.corpus, self.specification, force=force
                )
                inputs = self.corpus.read_inputs(
                    cursor,
                    chunk_size=chunk_size,
                    sample=sample,
                    seed=seed,
                )
                _, dimensions = embedding_stats(cursor, self.corpus)
                if dimensions is not None and dimensions != metadata.embedding_size:
                    raise ValueError(
                        "Stored vector dimensions disagree with embedding table metadata"
                    )
                dimensions = (
                    metadata.embedding_size or self.specification.embedding_size
                )
                pending = [
                    record
                    for record in inputs.records
                    if not stale_only or not self.corpus.is_current(cursor, record)
                ]
                embedded: list[tuple[EmbeddingInput, tuple[float, ...]]] = []
                records = (
                    tqdm(pending, unit="input", desc=f"Embedding {self.corpus.name}")
                    if progressbar
                    else pending
                )
                try:
                    for batch in embedding_request_batches(
                        records, self.specification.provider
                    ):
                        dimensions = self._embed_batch(
                            client,
                            batch,
                            embedded,
                            dimensions,
                        )
                finally:
                    if progressbar:
                        records.close()
                self.corpus.write_embeddings(cursor, embedded)
                self.corpus.remove_stale(cursor, inputs)
                if dimensions is None:
                    dimensions = len(
                        self._validate_vector(
                            embed_query_with_backoff(
                                client,
                                "Scrapyrus empty-corpus dimension readiness probe",
                                self.specification.provider,
                            ),
                            self.specification.requested_dimensions,
                        )
                    )
                set_embedding_size(cursor, self.corpus, dimensions)
                recreate_embedding_index(cursor, self.corpus.table_name, dimensions)
        return len(embedded)

    def _embed_batch(
        self,
        client: Embeddings,
        records: Sequence[EmbeddingInput],
        embedded: list[tuple[EmbeddingInput, tuple[float, ...]]],
        dimensions: int | None,
    ) -> int | None:
        """Embed one request, isolating skippable failures to individual inputs."""

        try:
            vectors = embed_documents_with_backoff(
                client,
                [record.text for record in records],
                self.specification.provider,
            )
        except Exception as error:
            if len(records) > 1 and is_skippable_embedding_error(error):
                for record in records:
                    dimensions = self._embed_batch(
                        client, (record,), embedded, dimensions
                    )
                return dimensions
            if not is_skippable_embedding_error(error):
                raise
            record = records[0]
            key = {name: record.values[name] for name in self.corpus.key_columns}
            print(
                f"Skipping {self.corpus.name} embedding {key!r} for model "
                f"{self.specification.model_name!r} after context-length validation error: "
                f"{embedding_error_message(error)}",
                flush=True,
            )
            return dimensions
        if len(vectors) != len(records):
            raise ValueError("Embedding client must return one vector per input")
        for record, raw_vector in zip(records, vectors, strict=True):
            vector = self._validate_vector(
                raw_vector,
                dimensions or self.specification.requested_dimensions,
            )
            if dimensions is None:
                dimensions = len(vector)
            embedded.append((record, vector))
        return dimensions

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
                metadata = require_embedding_specification(
                    cursor, self.corpus, self.specification
                )
                count, dimensions = embedding_stats(cursor, self.corpus)
                if count == 0:
                    raise ValueError(
                        f"No {self.corpus.name} embeddings found for model {model_name!r}. "
                        f"Run 'scrapyrus embeddings ingest {self.corpus.name}' with the same model first."
                    )
                if dimensions != metadata.embedding_size:
                    raise ValueError(
                        "Stored vector dimensions disagree with embedding table metadata"
                    )
                vector = self._validate_vector(
                    embed_query_with_backoff(client, text, self.specification.provider),
                    dimensions,
                )
                return self.corpus.query_matches(cursor, vector, top_k)

    def delete(self, conninfo: str = "") -> int:
        """Delete the configured model's vectors and index from the bound corpus."""

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor, EMBEDDING_CORPORA.values())
                require_embedding_specification(
                    cursor, self.corpus, self.specification, lock=True
                )
                drop_embedding_index(cursor, self.corpus.table_name)
                cursor.execute(
                    sql.SQL("DELETE FROM {}").format(
                        sql.Identifier(self.corpus.table_name)
                    ),
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
                metadata = require_embedding_specification(
                    cursor, corpus, self.specification
                )
                if metadata.embedding_size is None:
                    raise ValueError(
                        "Embedding dimensions must be known before exporting"
                    )
                count, dimensions = embedding_stats(cursor, corpus)
                if dimensions is not None and dimensions != metadata.embedding_size:
                    raise ValueError(
                        "Stored vector dimensions disagree with embedding table metadata"
                    )
                with target.open("wb") as output:
                    with cursor.copy(
                        sql.SQL(
                            "COPY (SELECT {columns} FROM {table} "
                            "ORDER BY {ordering}) TO STDOUT WITH (FORMAT binary)"
                        ).format(
                            columns=columns,
                            table=sql.Identifier(corpus.table_name),
                            ordering=ordering,
                        )
                    ) as copy:
                        for chunk in copy:
                            output.write(chunk)
                write_manifest(target, corpus, count, metadata)
        return count

    def import_dump(
        self, source: str | Path, conninfo: str = "", *, force: bool = False
    ) -> int:
        """Validate and replace this model's corpus records from a binary dump."""

        corpus = self.corpus
        source = Path(source)
        manifest, imported_metadata = load_manifest(source, corpus)
        if not self.specification.compatible_with(imported_metadata):
            raise EmbeddingModelMismatchError(
                "Embedding dump uses a different embedding specification"
            )
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
                reset_embedding_columns(cursor, temporary_table)
                cursor.execute(
                    sql.SQL("ALTER TABLE {} ADD PRIMARY KEY ({})").format(
                        sql.Identifier(temporary_table),
                        sql.SQL(", ").join(map(sql.Identifier, corpus.key_columns)),
                    )
                )
                if "chunk_id" in corpus.record_columns:
                    cursor.execute(
                        sql.SQL("ALTER TABLE {} ADD UNIQUE (chunk_id)").format(
                            sql.Identifier(temporary_table)
                        )
                    )
                with source.open("rb") as input_file:
                    with cursor.copy(
                        sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT binary)").format(
                            sql.Identifier(temporary_table), columns
                        )
                    ) as copy:
                        while chunk := input_file.read(1024 * 1024):
                            copy.write(chunk)
                count, dimensions = imported_embedding_stats(cursor, temporary_table)
                if count != manifest["row_count"]:
                    raise ValueError(
                        "Embedding dump row count disagrees with its manifest"
                    )
                if (
                    dimensions is not None
                    and dimensions != imported_metadata.embedding_size
                ):
                    raise ValueError(
                        "Imported vector dimensions disagree with the dump manifest"
                    )
                try:
                    corpus.validate_import(cursor, temporary_table)
                except psycopg.errors.UndefinedTable as error:
                    command = (
                        "metadata ingest"
                        if corpus.name == "keywords"
                        else "transcriptions ingest"
                    )
                    raise SourceUnavailableError(
                        f"Run 'scrapyrus {command}' before importing embeddings"
                    ) from error
                associate_embedding_specification(
                    cursor, corpus, imported_metadata.specification, force=force
                )
                drop_embedding_index(cursor, corpus.table_name)
                cursor.execute(
                    sql.SQL("DELETE FROM {}").format(sql.Identifier(corpus.table_name)),
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
                dimensions = imported_metadata.embedding_size
                set_embedding_size(cursor, corpus, dimensions)
                recreate_embedding_index(cursor, corpus.table_name, dimensions)
        return count
