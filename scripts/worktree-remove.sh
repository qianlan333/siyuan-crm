#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/worktree-remove.sh <worktree-path|branch-name> [--delete-branch]

Examples:
  scripts/worktree-remove.sh /Users/qianlan/Downloads/aicrm-new-feature-login
  scripts/worktree-remove.sh feature/login
  scripts/worktree-remove.sh feature/login --delete-branch
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 1
fi

target="$1"
delete_branch="false"

if [[ "${2:-}" == "--delete-branch" ]]; then
  delete_branch="true"
elif [[ $# -eq 2 ]]; then
  usage
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
repo_root="$(cd "${repo_root}" && pwd -P)"

resolve_worktree_by_branch() {
  local wanted_branch="$1"
  local current_path=""
  local current_branch=""
  while IFS= read -r line; do
    if [[ -z "${line}" ]]; then
      if [[ "${current_branch}" == "refs/heads/${wanted_branch}" ]]; then
        printf '%s\n' "${current_path}"
        return 0
      fi
      current_path=""
      current_branch=""
      continue
    fi
    case "${line}" in
      worktree\ *)
        current_path="${line#worktree }"
        ;;
      branch\ *)
        current_branch="${line#branch }"
        ;;
    esac
  done < <(git worktree list --porcelain; printf '\n')
  return 1
}

if [[ -d "${target}" ]]; then
  worktree_path="$(cd "${target}" && pwd -P)"
else
  worktree_path="$(resolve_worktree_by_branch "${target}")" || {
    echo "worktree not found for branch: ${target}"
    exit 1
  }
fi

if [[ "${worktree_path}" == "${repo_root}" ]]; then
  echo "refusing to remove the main repository worktree: ${repo_root}"
  exit 1
fi

if [[ ! -d "${worktree_path}" ]]; then
  echo "worktree path not found: ${worktree_path}"
  exit 1
fi

branch_name="$(git -C "${worktree_path}" branch --show-current)"

git worktree remove "${worktree_path}"
git worktree prune

echo "removed worktree: ${worktree_path}"

if [[ "${delete_branch}" == "true" ]]; then
  if [[ -z "${branch_name}" ]]; then
    echo "branch deletion skipped: detached HEAD"
    exit 0
  fi
  git branch -d "${branch_name}"
  echo "deleted branch: ${branch_name}"
fi
