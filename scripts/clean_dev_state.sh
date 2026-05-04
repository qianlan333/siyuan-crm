#!/usr/bin/env bash

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
FULL=0
REMOVED=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/clean_dev_state.sh [--dry-run] [--full]

Options:
  --dry-run  只打印会删除什么，不实际删除
  --full     额外删除可重建的本地虚拟环境（.venv / .venv311）
EOF
}

remove_path() {
  local target="$1"
  if [[ ! -e "$target" && ! -L "$target" ]]; then
    return 0
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] rm -rf $target"
  else
    rm -rf "$target"
    echo "[removed] $target"
  fi
  REMOVED=$((REMOVED + 1))
}

remove_found() {
  local prune_find=(
    find "$ROOT"
    \( -path "$ROOT/.git" -o -path "$ROOT/.venv" -o -path "$ROOT/.venv311" \) -prune
    -o
  )

  while IFS= read -r -d '' path; do
    remove_path "$path"
  done < <("${prune_find[@]}" "$@" -print0)
}

remove_bytecode_files_outside_pycache() {
  while IFS= read -r -d '' path; do
    remove_path "$path"
  done < <(
    find "$ROOT" \
      \( -path "$ROOT/.git" -o -path "$ROOT/.venv" -o -path "$ROOT/.venv311" -o -name '__pycache__' \) -prune \
      -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0
  )
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --full)
      FULL=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

echo "Repository root: $ROOT"
echo

# 1. 删除 pytest / coverage / lint 等可重建缓存目录。
remove_path "$ROOT/.pytest_cache"
remove_path "$ROOT/.mypy_cache"
remove_path "$ROOT/.ruff_cache"
remove_path "$ROOT/.cache"
remove_path "$ROOT/.hypothesis"
remove_path "$ROOT/htmlcov"

# 2. 删除 coverage 产物，避免看旧报告。
while IFS= read -r -d '' file; do
  remove_path "$file"
done < <(find "$ROOT" -maxdepth 1 -type f \( -name '.coverage' -o -name '.coverage.*' \) -print0)

# 3. 删除 Python 字节码缓存，解决“代码改了但像没生效”的问题。
remove_found -type d -name '__pycache__'
remove_bytecode_files_outside_pycache

# 4. 删除 Finder / 编辑器残留。
remove_found -type f \( -name '.DS_Store' -o -name '*.tmp' \)

# 5. 仅在显式要求时删除本地虚拟环境。
#    这两套环境都是可重建内容，但默认不删，以免每次都重新装依赖。
if [[ "$FULL" -eq 1 ]]; then
  remove_path "$ROOT/.venv"
  remove_path "$ROOT/.venv311"
fi

echo
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run complete. Matched items: $REMOVED"
else
  echo "Cleanup complete. Removed items: $REMOVED"
fi

echo "Next step: ./scripts/test_wave1_smoke.sh"
