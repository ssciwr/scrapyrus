#!/usr/bin/env bash
# Creates a complete custom-format dump of the Scrapyrus PostgreSQL database.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: postgres_dump.sh [DUMP_FILE]

Dump the database identified by SCRAPYRUS_DATABASE_URL. DUMP_FILE defaults to
scrapyrus.dump and must not already exist.

Example:
  SCRAPYRUS_DATABASE_URL='postgresql://scrapyrus@localhost/scrapyrus' \
      scripts/postgres_dump.sh /backups/scrapyrus.dump
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

if (( $# > 1 )); then
    usage >&2
    exit 2
fi

if [[ -z "${SCRAPYRUS_DATABASE_URL:-}" ]]; then
    echo "postgres_dump.sh: SCRAPYRUS_DATABASE_URL is not set" >&2
    exit 2
fi

if ! command -v pg_dump >/dev/null 2>&1; then
    echo "postgres_dump.sh: pg_dump is not installed or not on PATH" >&2
    exit 127
fi

dump_file="${1:-scrapyrus.dump}"
if [[ -e "$dump_file" ]]; then
    echo "postgres_dump.sh: refusing to overwrite $dump_file" >&2
    exit 1
fi

dump_directory="$(dirname -- "$dump_file")"
if [[ ! -d "$dump_directory" ]]; then
    echo "postgres_dump.sh: output directory does not exist: $dump_directory" >&2
    exit 1
fi

temporary_dump="${dump_file}.tmp.$$"
cleanup() {
    rm -f -- "$temporary_dump"
}
trap cleanup EXIT HUP INT TERM

pg_dump \
    --dbname="$SCRAPYRUS_DATABASE_URL" \
    --format=custom \
    --file="$temporary_dump" \
    --verbose

mv -- "$temporary_dump" "$dump_file"
trap - EXIT HUP INT TERM

echo "Database dump written to $dump_file"
