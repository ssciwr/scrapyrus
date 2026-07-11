import psycopg
import pytest

from scrapyrus.transcriptions.evaluation import evaluate_embeddings_model


class RecordingCursor:
    def __init__(self, results=(), all_results=()):
        self.executions = []
        self._results = list(results)
        self._all_results = list(all_results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchone(self):
        if not self._results:
            return None
        return self._results.pop(0)

    def fetchall(self):
        if not self._all_results:
            return []
        return self._all_results.pop(0)


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


def _normalize_sql(sql):
    return " ".join(sql.split())


def test_evaluate_embeddings_model_computes_recall_and_writes_markdown(
    tmp_path,
    monkeypatch,
):
    cursor = RecordingCursor(
        results=[(42, 3, 3), (7, 3, 4)],
        all_results=[
            [
                (
                    "1",
                    "DDB_EpiDoc_XML/p.test/1.xml",
                    "HGV_trans_EpiDoc/1.xml",
                    "[1,0,0]",
                ),
                (
                    "2",
                    "DDB_EpiDoc_XML/p.test/2.xml",
                    "HGV_trans_EpiDoc/2.xml",
                    "[0,1,0]",
                ),
                (
                    "3",
                    "DDB_EpiDoc_XML/p.test/3.xml",
                    "HGV_trans_EpiDoc/3.xml",
                    "[0,0,1]",
                ),
            ],
            [
                ("1", "HGV_trans_EpiDoc/1.xml"),
                ("2", "HGV_trans_EpiDoc/2.xml"),
                ("3", "HGV_trans_EpiDoc/3.xml"),
                ("4", "HGV_trans_EpiDoc/4.xml"),
                ("5", "HGV_trans_EpiDoc/5.xml"),
            ],
            [
                ("1", "HGV_trans_EpiDoc/1.xml"),
                ("2", "HGV_trans_EpiDoc/2.xml"),
                ("3", "HGV_trans_EpiDoc/3.xml"),
                ("4", "HGV_trans_EpiDoc/4.xml"),
                ("5", "HGV_trans_EpiDoc/5.xml"),
            ],
            [
                ("1", "HGV_trans_EpiDoc/1.xml"),
                ("2", "HGV_trans_EpiDoc/2.xml"),
                ("4", "HGV_trans_EpiDoc/4.xml"),
                ("5", "HGV_trans_EpiDoc/5.xml"),
                ("6", "HGV_trans_EpiDoc/6.xml"),
            ],
        ],
    )
    connection = RecordingConnection(cursor)

    def connect(conninfo):
        assert conninfo == "postgresql://metadata.example/scrapyrus"
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)
    output_file = tmp_path / "evaluation.md"

    evaluation = evaluate_embeddings_model(
        "postgresql://metadata.example/scrapyrus",
        modelname="embed/model",
        output_file=output_file,
        abbrev=True,
        lost=True,
    )

    assert evaluation.evaluated_count == 3
    assert evaluation.recall_hits == {
        1: 1,
        2: 2,
        3: 2,
        4: 2,
        5: 2,
    }
    assert evaluation.recall_at == {
        1: 1 / 3,
        2: 2 / 3,
        3: 2 / 3,
        4: 2 / 3,
        5: 2 / 3,
    }
    assert output_file.read_text(encoding="utf-8") == evaluation.to_markdown()
    assert "| recall@1 | 1 | 3 | 33.33% |" in evaluation.to_markdown()
    assert "| recall@5 | 2 | 3 | 66.67% |" in evaluation.to_markdown()

    transcription_select = cursor.executions[0]
    assert "FROM embedding_configurations" in _normalize_sql(transcription_select[0])
    assert transcription_select[1] == {
        "model_name": "embed/model",
        "document_kind": "transcription",
        "abbrev": True,
        "break_on_gap": False,
        "lost": True,
        "unclear": False,
        "regularize": False,
    }

    translation_select = cursor.executions[1]
    assert translation_select[1] == {
        "model_name": "embed/model",
        "document_kind": "translation",
        "abbrev": False,
        "break_on_gap": False,
        "lost": False,
        "unclear": False,
        "regularize": False,
    }

    query_select = cursor.executions[2]
    assert "JOIN document_embeddings AS translations" in _normalize_sql(query_select[0])
    assert query_select[1] == {
        "transcription_config_id": 42,
        "translation_config_id": 7,
    }

    nearest_selects = cursor.executions[3:]
    assert [params["embedding"] for _, params in nearest_selects] == [
        "[1,0,0]",
        "[0,1,0]",
        "[0,0,1]",
    ]
    assert all(params["limit"] == 5 for _, params in nearest_selects)


def test_evaluate_embeddings_model_requires_matching_dimensions(monkeypatch):
    cursor = RecordingCursor(results=[(42, 3, 1), (7, 4, 1)])
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: connection)

    with pytest.raises(ValueError, match="has 3 dimensions"):
        evaluate_embeddings_model(modelname="embed/model")
