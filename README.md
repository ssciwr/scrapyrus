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
uv sync --extra tests
```

The test suite uses generated corpus fixtures and does not require an
`idp.data` checkout. Run it through the worktree's environment:

```
.venv/bin/python -m pytest
```

## The idp.data corpus

Every ingestion command parses XML records from a local clone of the
[papyri.info `idp.data`](https://github.com/papyri/idp.data) repository. There is
no bundled copy and nothing is downloaded at runtime, so the clone is required
before `metadata ingest`, `transcriptions ingest`, or `images` will do anything.
Only the test suite is exempt.

```
git clone --depth 1 https://github.com/papyri/idp.data.git
```

The clone is several gigabytes. Ingestion reads only three directories, so a
sparse checkout is considerably faster and smaller:

```
git clone --filter=blob:none --sparse --depth 1 \
    https://github.com/papyri/idp.data.git
cd idp.data
git sparse-checkout set HGV_meta_EpiDoc DDbDP Translations
```

Commands look for `idp.data` in the current working directory. Point them
elsewhere with `--idp-data`, which belongs to the top-level command group and
therefore precedes the subcommand:

```
scrapyrus --idp-data /path/to/idp.data metadata ingest
```

A checkout missing `HGV_meta_EpiDoc`, `DDbDP`, or `Translations` fails with a
`FileNotFoundError` naming the absent directories.

## PostgreSQL configuration

### Creating a local database

Create the database and its owner as the `postgres` superuser:

```
sudo -u postgres psql
```

```sql
CREATE DATABASE scrapyrus;
CREATE USER scrapyrus WITH ENCRYPTED PASSWORD 'yourpw';
ALTER DATABASE scrapyrus OWNER TO scrapyrus;
```

The `ALTER DATABASE ... OWNER` statement matters. Since PostgreSQL 15,
`GRANT ALL PRIVILEGES ON DATABASE` does not confer the right to create objects
in the `public` schema, and ingestion creates its own tables. Granting database
privileges alone leaves ingestion failing with `permission denied for schema
public`. Where changing the owner is not an option, grant the schema explicitly
instead:

```sql
GRANT ALL ON SCHEMA public TO scrapyrus;
```

No schema migration step is needed. Ingestion drops and recreates the tables it
owns on every run.

When the PostgreSQL role name matches the Unix account running the command, the
default peer authentication connects without a password. The database name still
has to be supplied, because libpq defaults it to the account name as well and
otherwise fails with `database "<your-username>" does not exist`. Either name the
database in a connection URL:

```
export SCRAPYRUS_DATABASE_URL=postgresql:///scrapyrus
```

or set the standard PostgreSQL environment variable:

```
export PGDATABASE=scrapyrus
```

### Enabling the vector extension

Embedding commands require the `vector` extension from
[pgvector](https://github.com/pgvector/pgvector). Install the server package for
the running major version, for example `postgresql-16-pgvector` on Debian and
Ubuntu, then enable the extension once per database.

Because pgvector loads a native shared library into the server process, it is not
a trusted extension and `CREATE EXTENSION` requires a superuser even for the
database owner:

```
sudo -u postgres psql -d scrapyrus -c 'CREATE EXTENSION IF NOT EXISTS vector'
```

Confirm that the extension is available on the cluster before enabling it:

```
psql -d scrapyrus -c "SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector'"
```

An empty result means the server package is missing rather than the extension
being disabled. This step is unnecessary in the Docker setup below, where the
image ships pgvector and the configured user is a superuser.

### Connecting

Database-backed `scrapyrus` commands use PostgreSQL's standard connection
defaults when no connection URL is supplied. To use a connection URL instead,
set `SCRAPYRUS_DATABASE_URL` once in the shell before running ingestion,
dumping, lemmatization, embedding, or evaluation commands:

```
export SCRAPYRUS_DATABASE_URL=postgresql://scrapyrus:secret@localhost:5432/scrapyrus

scrapyrus metadata ingest
scrapyrus transcriptions ingest

# requires the vector extension; see "Enabling the vector extension" above
scrapyrus embeddings ingest \
    --inference-server-url <url> --model-name <model> --api-key <key>
```

Create a keyword embedding store from the distinct strings in the `keywords`
table with the same inference settings:

```
scrapyrus embeddings keywords \
    --inference-server-url <url> --model-name <model> --api-key <key>
```

The command keeps separate rows and cosine-search indexes for each model. On a
rerun it embeds only newly encountered keyword strings and removes strings that
no longer occur in `keywords` for that model.

Embed free text and print its top candidates with the evaluation command:

```
scrapyrus embeddings evaluate_keywords \
    "sale of a house" --top-k 10 \
    --inference-server-url <url> --model-name <model> --api-key <key>
```

Both commands accept `SCRAPYRUS_DATABASE_URL`, `SCRAPYRUS_EMBEDDINGS_URL`,
`SCRAPYRUS_EMBEDDINGS_MODEL`, and `SCRAPYRUS_EMBEDDINGS_API_KEY` instead of the
corresponding options. The query must use the same model as the stored keyword
embeddings.

The database must already exist and be reachable. Embedding ingestion reads the
XML rows created by `transcriptions ingest`, so those commands must run in that
order.

Embedding commands additionally require the `vector` extension to be enabled in
this database. Enable it before the first `embeddings ingest` run; without it the
command stops with `PostgreSQL extension 'vector' is not available`. Verify with:

```
psql -d scrapyrus -c "SELECT extname FROM pg_extension WHERE extname = 'vector'"
```

### Structured semantic catalog

Schema creation and import publish producer-owned table and column meanings to
`public.scrapyrus_semantic_catalog` in the same transaction as the data schema.
Metadata, transcriptions, and embeddings are independently published components,
covering `papyri`, `principal_editions`, `keywords`, `orig_dates`, `orig_places`,
`ancient_editions`, `transcriptions`, `transcription_embeddings`,
`translation_embeddings`, and `keyword_embeddings`.

A PostgreSQL-only consumer can read the versioned JSONB contract with:

```sql
SELECT
    schema_name,
    table_name,
    catalog_schema_version,
    producer_version,
    semantics
FROM public.scrapyrus_semantic_catalog
ORDER BY schema_name, table_name;
```

Publish all current definitions without rebuilding any data tables:

```
scrapyrus catalog
```

As with other database commands, use `--database-url` or
`SCRAPYRUS_DATABASE_URL` to select the database.

Consumers must support the returned `catalog_schema_version`, intersect entries
with live base tables, and introspect PostgreSQL for SQL types, nullability,
keys, and constraints. Semantic relationships marked
`enforced_by_database=false` are guidance rather than referential guarantees;
in particular, `tm_id` joins are generally logical and unenforced and may
multiply rows. Exclude the catalog table itself from ordinary domain-table
listings.

The `--database-url` option can override `SCRAPYRUS_DATABASE_URL` for a single
command. If neither is supplied, standard PostgreSQL parameters such as the
`PGHOST`, `PGPORT`, `PGDATABASE`, and `PGUSER` environment variables apply.

### Running PostgreSQL in Docker

Where a local server is unavailable, a pgvector-enabled PostgreSQL server can be
started on port 5432 with Docker. Mount a named volume so the data outlives the
container:

```
docker volume create scrapyrus-pgdata

docker run --name scrapyrus-postgres \
    --detach \
    --publish 5432:5432 \
    --env POSTGRES_DB=scrapyrus \
    --env POSTGRES_USER=scrapyrus \
    --env POSTGRES_PASSWORD=scrapyrus \
    --volume scrapyrus-pgdata:/var/lib/postgresql/data \
    pgvector/pgvector:pg16

export SCRAPYRUS_DATABASE_URL=postgresql://scrapyrus:scrapyrus@localhost:5432/scrapyrus
scrapyrus --idp-data /path/to/idp.data metadata ingest
```

The image ships pgvector and `POSTGRES_USER` is a superuser, so the extension can
be enabled from the host without `sudo`:

```
docker exec scrapyrus-postgres \
    psql --username=scrapyrus --dbname=scrapyrus \
    --command='CREATE EXTENSION IF NOT EXISTS vector'
```

With the volume in place, `docker stop scrapyrus-postgres` and
`docker rm scrapyrus-postgres` remove only the container; recreating it with the
same `--volume` argument restores the database. Ingested data survives image
upgrades within the same PostgreSQL major version. Deleting the data requires
removing the volume explicitly:

```
docker volume rm scrapyrus-pgdata
```

Omitting `--volume` stores the data inside the container's writable layer, where
`docker rm` destroys it along with the container.

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

Depending on the setup, it might worth to run pg_restore inside the postgres
Docker container:

```
docker exec -i papyri-prod-postgres-1 sh -c \
  'pg_restore --verbose --clean --if-exists --no-owner \
  --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  < scrapyrus.dump
```
## Acknowledgments

This repository was set up using the [SSC Cookiecutter for Python Packages](https://github.com/ssciwr/cookiecutter-python-package).
