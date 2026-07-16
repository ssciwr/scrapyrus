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

All database-backed `scrapyrus` commands use `SCRAPYRUS_DATABASE_URL` for the
PostgreSQL connection URL. Set it once in the shell before running ingestion,
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
command.

## Acknowledgments

This repository was set up using the [SSC Cookiecutter for Python Packages](https://github.com/ssciwr/cookiecutter-python-package).
