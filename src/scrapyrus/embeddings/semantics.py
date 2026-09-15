"""Semantic definitions for keyword and XML embedding records."""

from scrapyrus.semantics import ColumnSemantics, RelationshipSemantics, TableSemantics


def _embedding_semantics(table_name: str, document_kind: str) -> TableSemantics:
    """Build table semantics for an embedding document kind."""
    return TableSemantics(
        table_name=table_name,
        description=(
            f"The {table_name} table stores {document_kind} text chunks and "
            "vector embeddings from the table's configured model."
        ),
        row_grain=(
            f"One {document_kind} text chunk for one source XML row, "
            "keyed by (xml_id, chunk_index)."
        ),
        useful_for=(f"semantic search over {document_kind} chunks",),
        columns={
            "chunk_id": ColumnSemantics(
                description="Deterministic unique chunk identity: corpus name, source XML row ID, and zero-based chunk index, separated by colons."
            ),
            "xml_id": ColumnSemantics(
                description="Source transcriptions.transcription_id, despite the xml_id name.",
                caveats=(
                    f"For this table it must identify a transcriptions row whose type is {document_kind}; this is not database-enforced.",
                ),
            ),
            "chunk_index": ColumnSemantics(
                description="Zero-based deterministic chunk position within the rendered source row for the selected model/run."
            ),
            "source_path": ColumnSemantics(
                description="Denormalized source XML path copied at embedding time."
            ),
            "tm_id": ColumnSemantics(
                description="Denormalized Trismegistos ID copied as text at embedding time.",
                caveats=(
                    "Prefer joining by xml_id = transcriptions.transcription_id.",
                ),
            ),
            "language": ColumnSemantics(
                description="Denormalized source language copied at embedding time."
            ),
            "document_text": ColumnSemantics(
                description="Exact whitespace-word-based text chunk supplied for embedding.",
                caveats=("Chunks overlap by ten percent when chunking is needed.",),
            ),
            "input_hash": ColumnSemantics(
                description="Lowercase SHA-256 hexadecimal digest of document_text used for stale-input detection.",
                caveats=("It is not a document identity.",),
            ),
            "embedding": ColumnSemantics(
                description="pgvector value produced by the model in embedding_table_metadata, with model-dependent dimension."
            ),
            "updated_at": ColumnSemantics(
                description="Time the stored embedding row was inserted or refreshed."
            ),
        },
        relationships=(
            RelationshipSemantics(
                target_table="transcriptions",
                source_columns=("xml_id",),
                target_columns=("transcription_id",),
                cardinality="many-to-one",
                description="Logical source-row relationship; it is not a foreign key.",
            ),
        ),
        caveats=(
            "Cosine and distance operations must not compare vectors from different models merely because dimensions match.",
        ),
    )


TRANSCRIPTION_EMBEDDINGS_SEMANTICS = _embedding_semantics(
    "transcription_embeddings", "transcription"
)
TRANSLATION_EMBEDDINGS_SEMANTICS = _embedding_semantics(
    "translation_embeddings", "translation"
)

KEYWORD_EMBEDDINGS_SEMANTICS = TableSemantics(
    table_name="keyword_embeddings",
    description=(
        "The keyword_embeddings table stores one model-specific vector for each "
        "distinct keyword and optional qualifier string."
    ),
    row_grain=("One exact keyword string, keyed by keyword."),
    useful_for=("semantic keyword candidate search",),
    columns={
        "keyword": ColumnSemantics(
            description=(
                "Exact text supplied to the embedding model: a keyword by itself, "
                "or 'keyword, qualifier' when a qualifier is present."
            )
        ),
        "embedding": ColumnSemantics(
            description="pgvector value produced by the model in embedding_table_metadata for keyword."
        ),
        "updated_at": ColumnSemantics(
            description="Time the stored embedding row was inserted or refreshed."
        ),
    },
    caveats=(
        "Cosine and distance operations must not compare vectors from different models.",
    ),
)


EMBEDDING_TABLE_METADATA_SEMANTICS = TableSemantics(
    table_name="embedding_table_metadata",
    description="Complete non-secret embedding specification for each corpus table.",
    row_grain="One model configuration per embedding table, keyed by table_name.",
    useful_for=("checking model compatibility before comparing vectors",),
    columns={
        "table_name": ColumnSemantics(description="Embedding corpus table name."),
        "model_name": ColumnSemantics(
            description="The single embedding model used by this table."
        ),
        "embedding_size": ColumnSemantics(
            description="Positive vector dimension, determined by source embeddings or an empty-corpus readiness probe."
        ),
        "provider": ColumnSemantics(
            description="Allowlisted LangChain embedding provider."
        ),
        "provider_options": ColumnSemantics(
            description="All effective options affecting document/query embedding compatibility; excludes credentials and endpoint URLs."
        ),
        "endpoint_profile": ColumnSemantics(
            description="Optional deployment profile resolved by consumers through EMBEDDING_ENDPOINT_<PROFILE>; required for vllm."
        ),
        "contract_version": ColumnSemantics(
            description="Embedding compatibility contract version; currently 1."
        ),
    },
    caveats=("Matching vector dimensions alone do not establish model compatibility.",),
)
