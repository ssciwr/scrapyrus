#!/usr/bin/env bash
# Prints the 10 most frequent scheme-and-host URL prefixes.

set -euo pipefail

input_file="${1:-images_todo.txt}"

awk '{
      if (match($2, /^https?:\/\/[^/]+/)) {
          print substr($2, RSTART, RLENGTH)
      }
}' "$input_file" |
      sort |
      uniq -c |
      sort -k1,1nr -k2,2 |
      head -n 30
