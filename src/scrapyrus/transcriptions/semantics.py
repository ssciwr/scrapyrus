"""Semantic definitions for source XML and searchable text."""

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


__all__ = ["TRANSCRIPTIONS_SEMANTICS"]
