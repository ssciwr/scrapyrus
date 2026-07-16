#!/usr/bin/env bash
# Restores a custom-format Scrapyrus dump into an existing PostgreSQL database.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: postgres_restore.sh [--no-owner] [DUMP_FILE]

Restore DUMP_FILE (default: scrapyrus.dump) into the existing database identified
by SCRAPYRUS_DATABASE_URL. The target should be empty and must already have any
required extension packages, including pgvector, installed on its server.

By default, ownership and privileges from the source database are restored, so
the corresponding roles must exist on the target server. Use --no-owner to make
the user in SCRAPYRUS_DATABASE_URL own restored objects and omit source grants.

Example:
  SCRAPYRUS_DATABASE_URL='postgresql://scrapyrus@localhost/scrapyrus' \
      scripts/postgres_restore.sh /backups/scrapyrus.dump
EOF
}

no_owner=false
if [[ "${1:-}" == "--no-owner" ]]; then
    no_owner=true
    shift
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

if (( $# > 1 )); then
    usage >&2
    exit 2
fi

if [[ -z "${SCRAPYRUS_DATABASE_URL:-}" ]]; then
    echo "postgres_restore.sh: SCRAPYRUS_DATABASE_URL is not set" >&2
    exit 2
fi

if ! command -v pg_restore >/dev/null 2>&1; then
    echo "postgres_restore.sh: pg_restore is not installed or not on PATH" >&2
    exit 127
fi

dump_file="${1:-scrapyrus.dump}"
if [[ ! -f "$dump_file" || ! -r "$dump_file" ]]; then
    echo "postgres_restore.sh: dump file is not readable: $dump_file" >&2
    exit 1
fi

# Validate the archive before opening a transaction on the target database.
pg_restore --list "$dump_file" >/dev/null

restore_options=(
    --dbname="$SCRAPYRUS_DATABASE_URL"
    --exit-on-error
    --single-transaction
    --verbose
)
if [[ "$no_owner" == true ]]; then
    restore_options+=(--no-owner --no-privileges)
fi

pg_restore "${restore_options[@]}" "$dump_file"

echo "Database restored from $dump_file"
