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

## Docker Compose

The repository includes a Docker Compose setup with PostgreSQL and a profiled
`scrapyrus` execution container. The PostgreSQL service uses a pgvector-enabled
image because `scrapyrus embeddings` commands require the `vector` extension:

```
docker compose up -d postgres
```

The `scrapyrus` container mounts this repository at `/workspace` and sets
`SCRAPYRUS_DATABASE_URL` to the PostgreSQL service. It also mounts the local
`./exchange` directory at `/exchange` for moving data between the host and the
container. Start it as a one-off shell when you need to run the CLI:

```
docker compose run --build --rm scrapyrus bash
scrapyrus metadata ingest
```

The `scrapyrus` service is intentionally not started by the default `up`
command. Some Snap-packaged Docker installations fail to stop idle long-lived
containers during rebuilds with `cannot stop container: ... permission denied`;
using one-off `run --rm` containers avoids that host-side recreate path.

If `idp.data` is somewhere else inside the mounted workspace, pass it explicitly:

```
scrapyrus --idp-data /workspace/idp.data metadata ingest
```

To export the metadata database tables as CSV files:

```
scrapyrus metadata dump
```

If an older checkout already started the Compose stack with the stock PostgreSQL
image, recreate the database service after updating:

```
docker compose up -d --force-recreate postgres
```

## Acknowledgments

This repository was set up using the [SSC Cookiecutter for Python Packages](https://github.com/ssciwr/cookiecutter-python-package).
