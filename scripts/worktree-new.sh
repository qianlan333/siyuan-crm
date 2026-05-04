#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/worktree-new.sh <branch-name> [base-ref] [worktree-path]

Examples:
  scripts/worktree-new.sh feature/customer-timeline
  scripts/worktree-new.sh feature/customer-timeline main
  scripts/worktree-new.sh feature/customer-timeline origin/main /tmp/aicrm-customer-timeline
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 1
fi

branch_name="$1"
base_ref="${2:-main}"

repo_root="$(git rev-parse --show-toplevel)"
repo_parent="$(dirname "${repo_root}")"
repo_name="$(basename "${repo_root}")"
branch_slug="$(printf '%s' "${branch_name}" | tr '/[:space:]' '-' | tr -cd '[:alnum:]._-' )"

if [[ -z "${branch_slug}" ]]; then
  echo "invalid branch name: ${branch_name}"
  exit 1
fi

worktree_path="${3:-${repo_parent}/${repo_name}-${branch_slug}}"

if [[ -e "${worktree_path}" ]]; then
  echo "worktree path already exists: ${worktree_path}"
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/${branch_name}"; then
  git worktree add "${worktree_path}" "${branch_name}"
  echo "attached existing branch to worktree"
else
  git rev-parse --verify "${base_ref}^{commit}" >/dev/null
  git worktree add -b "${branch_name}" "${worktree_path}" "${base_ref}"
  echo "created new branch from ${base_ref}"
fi

echo "branch: ${branch_name}"
echo "path: ${worktree_path}"
