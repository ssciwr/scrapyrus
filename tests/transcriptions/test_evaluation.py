import psycopg

from scrapyrus.transcriptions.evaluation import (
    EmbeddingEvaluation,
    LanguageEmbeddingEvaluation,
    evaluate_embeddings,
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
    assert evaluation.mrr == 1.0
    assert evaluation.language_results["greek"].recall_at[1] == 1.0
    assert evaluation.language_results["greek"].mrr == 1.0
    sql = "\n".join(query for query, _ in cursor.executions)
    assert "transcription_embeddings" in sql
    assert "translation_embeddings" in sql
    assert "embedding_configurations" not in sql
    report = output.read_text()
    assert report.startswith("# Embedding Evaluation: `model`")
    assert "| MRR | 1.0000 | 1 | 100.00% |" in report


def test_markdown_renders_collection_counts():
    result = EmbeddingEvaluation(
        modelname="model",
        transcription_count=4,
        translation_count=3,
        embedding_dimensions=2,
        evaluated_count=2,
        recall_hits={1: 1},
        reciprocal_rank_sum=1.5,
        language_results={
            "greek": LanguageEmbeddingEvaluation("greek", 2, {1: 1}, 1.5)
        },
    )

    report = result.to_markdown()
    assert "- Transcription documents: 4" in report
    assert "- Translation documents: 3" in report
    assert "| recall@1 | 1 | 2 | 50.00% |" in report
    assert "| MRR | 1.5000 | 2 | 75.00% |" in report


def test_evaluation_calculates_mean_reciprocal_rank(monkeypatch):
    cursor = Cursor()
    cursor.fetchall_results = [
        [
            ("1", "ddb/1.xml", "grc", "[1,0,0]"),
            ("2", "ddb/2.xml", "grc", "[0,1,0]"),
        ],
        [("2", "hgv/2.xml"), ("1", "hgv/1.xml")],
        [("2", "hgv/2.xml"), ("1", "hgv/1.xml")],
    ]
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: Connection(cursor))

    evaluation = evaluate_embeddings_model("postgresql://db", modelname="sample")

    assert evaluation.reciprocal_rank_sum == 1.5
    assert evaluation.mrr == 0.75
    assert evaluation.recall_at[1] == 0.5
    assert evaluation.recall_at[2] == 1.0
    assert evaluation.language_results["greek"].mrr == 0.75


def test_evaluation_uses_exact_rank_for_mrr_outside_recall_window(monkeypatch):
    cursor = Cursor()
    cursor.fetchone_results = [(1, 3), (6, 3), (6,)]
    cursor.fetchall_results = [
        [("1", "ddb/1.xml", "grc", "[1,0,0]")],
        [
            ("2", "hgv/2.xml"),
            ("3", "hgv/3.xml"),
            ("4", "hgv/4.xml"),
            ("5", "hgv/5.xml"),
            ("6", "hgv/6.xml"),
        ],
    ]
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: Connection(cursor))

    evaluation = evaluate_embeddings_model("postgresql://db", modelname="sample")

    assert evaluation.recall_at[5] == 0.0
    assert evaluation.mrr == 1 / 6
    assert "row_number()" in cursor.executions[-1][0]


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


def test_evaluation_runs_for_all_models_with_embeddings(tmp_path, monkeypatch):
    cursor = Cursor()
    cursor.fetchone_results = [(1, 2), (1, 2), (1, 2), (1, 2)]
    cursor.fetchall_results = [
        [("alpha",), ("beta",)],
        [("1", "ddb/1.xml", "grc", "[1,0]")],
        [("1", "hgv/1.xml")],
        [("2", "ddb/2.xml", "la", "[0,1]")],
        [("3", "hgv/3.xml"), ("2", "hgv/2.xml")],
    ]
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: Connection(cursor))
    output = tmp_path / "report.md"

    evaluation = evaluate_embeddings("postgresql://db", output_file=output)

    assert [result.modelname for result in evaluation.results] == ["alpha", "beta"]
    assert evaluation.results[0].recall_at[1] == 1.0
    assert evaluation.results[1].recall_at[1] == 0.0
    assert evaluation.results[1].recall_at[2] == 1.0
    sql = "\n".join(query for query, _ in cursor.executions)
    assert "GROUP BY transcriptions.model_name" in sql
    report = output.read_text()
    assert report.startswith("# Embedding Evaluations")
    assert "| `alpha` | 1 | 1 | 1 | 2 | 100.00%" in report
    assert "## Embedding Evaluation: `beta`" in report
