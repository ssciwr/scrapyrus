# Welcome to scrapyrus

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/ssciwr/scrapyrus/ci.yml?branch=main)](https://github.com/ssciwr/scrapyrus/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ssciwr/scrapyrus/branch/main/graph/badge.svg)](https://codecov.io/gh/ssciwr/scrapyrus)

## Installation

The Python package `scrapyrus` can be installed from PyPI:

```
python -m pip install scrapyrus
```

## Development installation

If you want to contribute to the development of `scrapyrus`, we recommend
the following editable installation from this repository:

```
git clone git@github.com:ssciwr/scrapyrus.git
cd scrapyrus
python -m pip install --editable .[tests]
```

Having done so, the test suite can be run using `pytest`:

```
python -m pytest
```

## PostgreSQL configuration

Database-backed `scrapyrus` commands use PostgreSQL's standard connection
defaults when no connection URL is supplied. To use a connection URL instead,
set `SCRAPYRUS_DATABASE_URL` once in the shell before running ingestion,
dumping, lemmatization, embedding, or evaluation commands:

```
export SCRAPYRUS_DATABASE_URL=postgresql://scrapyrus:secret@localhost:5432/scrapyrus

scrapyrus metadata ingest
scrapyrus transcriptions ingest
scrapyrus embeddings ingest \
    --inference-server-url <url> --model-name <model> --api-key <key>
```

The database must already exist and be reachable. Embedding commands additionally
require the PostgreSQL `vector` extension. Embedding ingestion reads the XML rows
created by `transcriptions ingest`, so those commands must run in that order.

The `--database-url` option can override `SCRAPYRUS_DATABASE_URL` for a single
command. If neither is supplied, standard PostgreSQL parameters such as the
`PGHOST`, `PGPORT`, `PGDATABASE`, and `PGUSER` environment variables apply.

For local development, a pgvector-enabled PostgreSQL server can be started on
port 5432 with Docker:

```
docker run --name scrapyrus-postgres \
    --detach \
    --publish 5432:5432 \
    --env POSTGRES_DB=scrapyrus \
    --env POSTGRES_USER=scrapyrus \
    --env POSTGRES_PASSWORD=scrapyrus \
    pgvector/pgvector:pg16

export SCRAPYRUS_DATABASE_URL=postgresql://scrapyrus:scrapyrus@localhost:5432/scrapyrus
scrapyrus metadata ingest
```

This container does not use persistent storage, so removing it also removes its
database data. Stop and remove it with `docker stop scrapyrus-postgres` followed
by `docker rm scrapyrus-postgres`.

### Moving the database

The database can be moved to another PostgreSQL instance with the dump and
restore scripts. Set `SCRAPYRUS_DATABASE_URL` to the source for the dump, then
to the target for the restore:

```
SCRAPYRUS_DATABASE_URL=<source-url> scripts/postgres_dump.sh scrapyrus.dump
SCRAPYRUS_DATABASE_URL=<target-url> scripts/postgres_restore.sh scrapyrus.dump
```

The target database must already exist and be empty, and its server must have
the `vector` extension available. Source roles must also exist on the target;
otherwise, pass `--no-owner` to the restore script to make the target connection
user own the restored objects and omit source privileges. Keep the source
database until the restored database has been verified.

## Acknowledgments

This repository was set up using the [SSC Cookiecutter for Python Packages](https://github.com/ssciwr/cookiecutter-python-package).
