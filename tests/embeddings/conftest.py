"""Database and client doubles for the shared embedding lifecycle tests."""

from copy import deepcopy

import pytest


class Copy:
    def __init__(self, chunks, writes):
        self.chunks = chunks
        self.writes = writes

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.chunks)

    def write(self, chunk):
        self.writes.append(chunk)


class Cursor:
    def __init__(self):
        self.executions = []
        self.one_results = []
        self.all_results = []
        self.copy_chunks = []
        self.copy_writes = []
        self.copies = []
        self.rowcount = 0
        self.fail_on = None
        self.metadata = {}
        self.metadata_result = ...

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string()
        self.executions.append((text, params))
        self.metadata_result = ...
        if text.startswith("INSERT INTO embedding_table_metadata"):
            self.metadata.setdefault(
                params[0],
                (params[1], params[2], params[3], params[4].obj, params[5], params[6]),
            )
        elif text.startswith("SELECT table_name, model_name, embedding_size"):
            configured = self.metadata.get(params[0])
            self.metadata_result = (
                None if configured is None else (params[0], *configured)
            )
        elif text.startswith("UPDATE embedding_table_metadata"):
            if "model_name =" in text:
                self.metadata[params[6]] = (
                    params[0],
                    params[1],
                    params[2],
                    params[3].obj,
                    params[4],
                    params[5],
                )
            else:
                model, _, *contract = self.metadata[params[1]]
                self.metadata[params[1]] = (model, params[0], *contract)
        if self.fail_on:
            self.fail_on(text)

    def fetchone(self):
        if self.metadata_result is not ...:
            return self.metadata_result
        return self.one_results.pop(0)

    def fetchall(self):
        return self.all_results.pop(0)

    def copy(self, query):
        self.copies.append(query.as_string())
        return Copy(self.copy_chunks, self.copy_writes)


class Connection:
    def __init__(self, cursor):
        self.db_cursor = cursor
        self.outcomes = []

    def __enter__(self):
        self.saved_metadata = deepcopy(self.db_cursor.metadata)
        return self

    def __exit__(self, error_type, *args):
        if error_type:
            self.db_cursor.metadata = self.saved_metadata
        self.outcomes.append("rollback" if error_type else "commit")
        return False

    def cursor(self):
        return self.db_cursor


class Client:
    def __init__(self):
        self.documents = []
        self.queries = []
        self.vectors = []

    def embed_documents(self, texts):
        self.documents.extend(texts)
        result = self.vectors.pop(0) if self.vectors else (1.0, 0.0)
        if isinstance(result, Exception):
            raise result
        return [result]

    def embed_query(self, text):
        self.queries.append(text)
        return self.vectors.pop(0) if self.vectors else (1.0, 0.0)


@pytest.fixture
def database(monkeypatch):
    cursor = Cursor()
    connection = Connection(cursor)
    monkeypatch.setattr("psycopg.connect", lambda conninfo: connection)
    return cursor, connection


@pytest.fixture
def client():
    return Client()
