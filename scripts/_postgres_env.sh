#!/usr/bin/env bash

require_database_url() {
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required" >&2
    exit 1
  fi
}
