#!/usr/bin/env bash
set -euo pipefail

EXPECTED_BRANCH="${EXPECTED_BRANCH:-migration/aicrm-next-port}"

pass() { printf 'PASS %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; exit 1; }

command -v git >/dev/null 2>&1 || fail "git is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v psql >/dev/null 2>&1 || fail "psql is required"
command -v pg_dump >/dev/null 2>&1 || fail "pg_dump is required"
command -v pg_restore >/dev/null 2>&1 || fail "pg_restore is required"
pass "required commands are available"

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("FAIL python3 >= 3.10 is required")
print(f"PASS python version {sys.version.split()[0]}")
PY

if [[ -z "${DATABASE_URL:-}" ]]; then
  warn "DATABASE_URL is not set in the current shell; source the siyuan env file before DB checks"
else
  pass "DATABASE_URL is set"
fi

branch="$(git branch --show-current)"
if [[ "${branch}" == "${EXPECTED_BRANCH}" ]]; then
  pass "current branch is ${branch}"
else
  warn "current branch is ${branch:-detached}; expected ${EXPECTED_BRANCH}"
fi

if git diff --quiet && git diff --cached --quiet; then
  pass "no tracked or staged local modifications"
else
  warn "working tree has tracked or staged modifications"
  git status --short
fi

pending_sensitive="$(
  git status --porcelain --untracked-files=all |
    awk '{$1=""; sub(/^ /,""); print}' |
    grep -E '(^|/)(\.env|[^/]+\.dump|[^/]+\.sql\.gz|[^/]+\.tar\.gz|[^/]+\.pem|[^/]+\.key|uploads/|static/uploads/|instance/|backups/|[^/]+\.sqlite|[^/]+\.db)$' || true
)"
if [[ -n "${pending_sensitive}" ]]; then
  warn "possible sensitive files are pending in git status:"
  printf '%s\n' "${pending_sensitive}"
else
  pass "no pending sensitive files detected in git status"
fi

tracked_sensitive="$(
  git ls-files |
    grep -E '(^|/)(\.env($|\.)|[^/]+\.dump|[^/]+\.sql\.gz|[^/]+\.tar\.gz|[^/]+\.pem|[^/]+\.key|uploads/|static/uploads/|instance/|backups/|[^/]+\.sqlite|[^/]+\.db)$' |
    grep -v '^\.env\.example$' || true
)"
if [[ -n "${tracked_sensitive}" ]]; then
  warn "tracked files match sensitive patterns; review before PR:"
  printf '%s\n' "${tracked_sensitive}"
else
  pass "no tracked sensitive files detected"
fi

pass "preflight completed"
