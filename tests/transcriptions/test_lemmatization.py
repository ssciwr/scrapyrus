from types import SimpleNamespace

import psycopg

from scrapyrus.transcriptions.lemmatization import (
    lemmatize_text,
    lemmatize_transcriptions,
    normalize_language,
)


class RecordingCursor:
    def __init__(self, rows, executions):
        self.rows = rows
        self.executions = executions

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return RecordingCursor(self.rows, self.executions)


class Pipeline:
    def __init__(self, language, analyses):
        self.language = language
        self.analyses = analyses

    def analyze(self, text):
        self.analyses.append((self.language, text))
        return SimpleNamespace(
            words=[
                SimpleNamespace(lemma=f"{self.language}-lemma", string="ignored"),
                SimpleNamespace(lemma=None, string="fallback"),
                SimpleNamespace(lemma="", string=""),
            ]
        )


def test_normalize_language_accepts_supported_language_variants():
    assert normalize_language("grc") == "grc"
    assert normalize_language("el-Grek") == "grc"
    assert normalize_language("la") == "lat"
    assert normalize_language("LAT") == "lat"
    assert normalize_language("cop_Egyp") == "cop"
    assert normalize_language("en") is None
    assert normalize_language(None) is None


def test_lemmatize_text_uses_word_text_when_lemma_is_missing():
    analyses = []

    result = lemmatize_text("input", Pipeline("grc", analyses))

    assert result == "grc-lemma fallback"
    assert analyses == [("grc", "input")]


def test_lemmatize_transcriptions_updates_only_supported_rows(monkeypatch):
    rows = [
        {
            "transcription_id": 1,
            "xml_content": "greek transcription",
            "type": "transcription",
            "language": None,
        },
        {
            "transcription_id": 2,
            "xml_content": "latin translation",
            "type": "translation",
            "language": "la",
        },
        {
            "transcription_id": 3,
            "xml_content": "english translation",
            "type": "translation",
            "language": "en",
        },
        {
            "transcription_id": 4,
            "xml_content": "second greek transcription",
            "type": "transcription",
            "language": None,
        },
    ]
    connection = RecordingConnection(rows)
    connect_calls = []

    def connect(conninfo, **kwargs):
        connect_calls.append((conninfo, kwargs))
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(
        "scrapyrus.transcriptions.lemmatization.transcription_language",
        lambda xml: "grc",
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.lemmatization.epidoc_xml_to_text",
        lambda xml: f"text from {xml}",
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.lemmatization.translation_epidoc_xml_to_text",
        lambda xml: f"translation from {xml}",
    )
    factory_calls = []
    analyses = []

    def factory(language):
        factory_calls.append(language)
        return Pipeline(language, analyses)

    lemmatize_transcriptions(
        "postgresql://database.example/scrapyrus",
        progressbar=False,
        pipeline_factory=factory,
        application_name="scrapyrus-test",
    )

    assert connect_calls[0][0] == "postgresql://database.example/scrapyrus"
    assert connect_calls[0][1]["application_name"] == "scrapyrus-test"
    assert factory_calls == ["grc", "lat"]
    assert analyses == [
        ("grc", "text from greek transcription"),
        ("lat", "translation from latin translation"),
        ("grc", "text from second greek transcription"),
    ]
    assert "WHERE lemma_text IS NULL" in connection.executions[0][0]
    updates = [params for _, params in connection.executions[1:]]
    assert updates == [
        {"transcription_id": 1, "lemma_text": "grc-lemma fallback"},
        {"transcription_id": 2, "lemma_text": "lat-lemma fallback"},
        {"transcription_id": 4, "lemma_text": "grc-lemma fallback"},
    ]
