import psycopg

from scrapyrus.transcriptions.evaluation import (
    EmbeddingEvaluation,
    LanguageEmbeddingEvaluation,
    evaluate_embeddings_model,
)


class Cursor:
    def __init__(self):
        self.executions = []
        self.fetchone_results = [(2, 3), (2, 3)]
        self.fetchall_results = [
            [("1", "ddb/1.xml", "grc", "[1,0,0]")],
            [("1", "hgv/1.xml"), ("2", "hgv/2.xml")],
        ]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchone(self):
        return self.fetchone_results.pop(0)

    def fetchall(self):
        return self.fetchall_results.pop(0)


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


def test_evaluation_uses_separate_embedding_tables_and_stored_language(
    tmp_path, monkeypatch
):
    cursor = Cursor()
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: Connection(cursor))
    output = tmp_path / "report.md"

    evaluation = evaluate_embeddings_model(
        "postgresql://db", modelname="model", output_file=output
    )

    assert evaluation.transcription_count == 2
    assert evaluation.translation_count == 2
    assert evaluation.embedding_dimensions == 3
    assert evaluation.evaluated_count == 1
    assert evaluation.recall_at[1] == 1.0
    assert evaluation.language_results["greek"].recall_at[1] == 1.0
    sql = "\n".join(query for query, _ in cursor.executions)
    assert "transcription_embeddings" in sql
    assert "translation_embeddings" in sql
    assert "embedding_configurations" not in sql
    assert output.read_text().startswith("# Embedding Evaluation: `model`")


def test_markdown_renders_collection_counts():
    result = EmbeddingEvaluation(
        modelname="model",
        transcription_count=4,
        translation_count=3,
        embedding_dimensions=2,
        evaluated_count=2,
        recall_hits={1: 1},
        language_results={"greek": LanguageEmbeddingEvaluation("greek", 2, {1: 1})},
    )

    report = result.to_markdown()
    assert "- Transcription documents: 4" in report
    assert "- Translation documents: 3" in report
    assert "| recall@1 | 1 | 2 | 50.00% |" in report


def test_evaluation_accepts_partial_embedding_collections(monkeypatch):
    cursor = Cursor()
    cursor.fetchone_results = [(3, 3), (1, 3)]
    cursor.fetchall_results = [
        [("1", "ddb/1.xml", "grc", "[1,0,0]")],
        [("1", "hgv/1.xml")],
    ]
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: Connection(cursor))

    evaluation = evaluate_embeddings_model("postgresql://db", modelname="sample")

    assert evaluation.transcription_count == 3
    assert evaluation.translation_count == 1
    assert evaluation.evaluated_count == 1
    assert evaluation.recall_at[5] == 1.0
