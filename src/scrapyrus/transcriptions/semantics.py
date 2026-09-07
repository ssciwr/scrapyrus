"""Data-only semantic definitions for textual and embedding tables."""

from scrapyrus.semantics import ColumnSemantics, RelationshipSemantics, TableSemantics


TRANSCRIPTIONS_SEMANTICS = TableSemantics(
    table_name="transcriptions",
    description=(
        "The transcriptions table stores source EpiDoc XML and derived searchable "
        "text for transcription and translation divisions."
    ),
    row_grain=(
        "One stored EpiDoc edition division or one top-level translation division; "
        "one source file or tm_id may produce multiple rows."
    ),
    useful_for=("source XML access", "full-text and lemma search", "translations"),
    columns={
        "transcription_id": ColumnSemantics(
            description="Generated internal row identity copied to embedding tables as xml_id."
        ),
        "source_path": ColumnSemantics(
            description="Relative idp.data XML path used as source provenance.",
            caveats=(
                "It is not guaranteed unique because a file may contain multiple translation divisions.",
            ),
        ),
        "tm_id": ColumnSemantics(
            description="Logical Trismegistos document ID relating textual rows to metadata."
        ),
        "xml_content": ColumnSemantics(
            description="Serialized source TEI/EpiDoc XML.",
            caveats=("Use XML operations; this is not normalized plain text.",),
        ),
        "type": ColumnSemantics(
            description="Controlled kind of stored textual division.",
            value_meanings={
                "transcription": "an EpiDoc edition division",
                "translation": "a top-level translation division",
            },
        ),
        "language": ColumnSemantics(
            description="Translation xml:lang value when supplied.",
            null_means="The row is a transcription, or a translation with no supplied language.",
            caveats=("Database constraints require null for transcription rows.",),
        ),
        "text": ColumnSemantics(
            description="Complete plain-text rendering used for textual access and source search.",
            caveats=(
                "It is derived from XML with editorial rendering choices, not a diplomatic byte-for-byte transcription.",
            ),
        ),
        "text_vector": ColumnSemantics(
            description="Generated PostgreSQL simple-configuration tsvector derived from text.",
            caveats=("This is a search representation, not readable text.",),
        ),
        "lemma_text": ColumnSemantics(
            description="Space-separated lemmata populated for supported Greek, Latin, and Coptic rows.",
            null_means="Lemmata have not been populated or the language is unsupported or unidentified.",
        ),
        "lemma_vector": ColumnSemantics(
            description="Generated PostgreSQL simple-configuration tsvector derived from lemma_text.",
            null_means="lemma_text is null.",
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
        RelationshipSemantics(
            target_table="transcription_embeddings",
            source_columns=("transcription_id",),
            target_columns=("xml_id",),
            cardinality="one-to-many",
            description="One source row can have multiple chunks and embedding models.",
        ),
        RelationshipSemantics(
            target_table="translation_embeddings",
            source_columns=("transcription_id",),
            target_columns=("xml_id",),
            cardinality="one-to-many",
            description="One translation row can have multiple chunks and embedding models.",
        ),
    ),
)


def _embedding_semantics(table_name: str, document_kind: str) -> TableSemantics:
    return TableSemantics(
        table_name=table_name,
        description=(
            f"The {table_name} table stores {document_kind} text chunks and "
            "model-specific vector embeddings."
        ),
        row_grain=(
            f"One {document_kind} text chunk for one source XML row and embedding "
            "model, keyed by (xml_id, model_name, chunk_index)."
        ),
        useful_for=(f"semantic search over {document_kind} chunks",),
        columns={
            "xml_id": ColumnSemantics(
                description="Source transcriptions.transcription_id, despite the xml_id name.",
                caveats=(
                    f"For this table it must identify a transcriptions row whose type is {document_kind}; this is not database-enforced.",
                ),
            ),
            "model_name": ColumnSemantics(
                description="Embedding model identifier.",
                caveats=(
                    "Filter vector comparisons to one compatible model; dimensions may vary by model.",
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
                description="pgvector value produced by model_name, with model-dependent dimension."
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
    row_grain=(
        "One exact keyword string and embedding model, keyed by (keyword, model_name)."
    ),
    useful_for=("semantic keyword candidate search",),
    columns={
        "keyword": ColumnSemantics(
            description=(
                "Exact text supplied to the embedding model: a keyword by itself, "
                "or 'keyword, qualifier' when a qualifier is present."
            )
        ),
        "model_name": ColumnSemantics(
            description="Embedding model identifier.",
            caveats=(
                "Filter vector comparisons to one compatible model; dimensions may vary by model.",
            ),
        ),
        "embedding": ColumnSemantics(
            description="pgvector value produced by model_name for keyword."
        ),
        "updated_at": ColumnSemantics(
            description="Time the stored embedding row was inserted or refreshed."
        ),
    },
    caveats=(
        "Cosine and distance operations must not compare vectors from different models.",
    ),
)


__all__ = [
    "TRANSCRIPTIONS_SEMANTICS",
    "KEYWORD_EMBEDDINGS_SEMANTICS",
    "TRANSCRIPTION_EMBEDDINGS_SEMANTICS",
    "TRANSLATION_EMBEDDINGS_SEMANTICS",
]
