#!/usr/bin/env bash
set -euo pipefail

# Normalize an application/SQLAlchemy PostgreSQL URL for PostgreSQL CLI tools.
# Example:
#   normalize_pg_cli_url 'postgresql+psycopg://u:p@h:5432/db'
#   # => postgresql://u:p@h:5432/db
normalize_pg_cli_url() {
  local input_url="${1:-}"

  if [[ -z "${input_url}" ]]; then
    printf 'normalize_pg_cli_url: URL is required\n' >&2
    return 1
  fi

  case "${input_url}" in
    postgresql+psycopg://*)
      printf 'postgresql://%s\n' "${input_url#postgresql+psycopg://}"
      ;;
    postgresql+psycopg2://*)
      printf 'postgresql://%s\n' "${input_url#postgresql+psycopg2://}"
      ;;
    postgresql://*|postgres://*)
      printf '%s\n' "${input_url}"
      ;;
    *)
      printf 'normalize_pg_cli_url: unsupported PostgreSQL URL scheme\n' >&2
      return 1
      ;;
  esac
}
