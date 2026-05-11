#!/usr/bin/env bash
# scripts/prod.sh — 本地→生产 sandbox 转发器
# 所有命令都通过 `ssh crm-prod <子命令> [参数]` 走 forced-command 受限通道。
# 服务器侧子命令实现在 ~/claude-debug.sh，扩展指引: docs/claude_prod_sandbox_extension.md
set -euo pipefail

HOST="${SSH_HOST:-crm-prod}"

usage() {
  cat <<'EOF'
用法: scripts/prod.sh <子命令> [参数...]

只读类（sandbox 现成支持）:
  logs <service> [n]       journalctl -u <service> -n <n>（默认 200）
  status <service>         systemctl status
  tail <path> [n]          /var/log/* 或项目 logs/* 的尾部
  health                   GET localhost:5001/health
  pg-status                pg_isready + 连接数
  git-status               项目 git status / log -3
  ps / disk / mem          关键进程 / 磁盘 / 内存
  whoami                   当前用户 + 子命令清单

需扩展（见 docs/claude_prod_sandbox_extension.md）:
  psql <SQL>               执行任意 SQL；写操作需追加 --write 才放行
  psql-stdin               从 stdin 读多行 SQL（cat foo.sql | prod.sh psql-stdin）
  cat <path>               读 /home/ubuntu/, /var/log/, /etc/nginx/
  ls [path]                列目录（同上白名单）

环境变量:
  SSH_HOST=crm-prod        默认 ssh 别名

示例:
  scripts/prod.sh logs openclaw-wecom-postgres 100
  scripts/prod.sh psql "SELECT count(*) FROM users;"
  echo "SELECT * FROM users LIMIT 5;" | scripts/prod.sh psql-stdin
  scripts/prod.sh psql "UPDATE users SET name='x' WHERE id=1" --write
EOF
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage; exit 0
fi

cmd="$1"; shift

case "$cmd" in
  psql)
    sql="${1:-}"
    if [[ -z "$sql" ]]; then
      echo "用法: prod.sh psql <SQL>" >&2; exit 2
    fi
    # 写操作拦截：默认拒，要求显式 --write
    if echo "$sql" | grep -qiE '\b(update|delete|drop|truncate|alter|insert|grant|revoke|create)\b'; then
      if [[ "${2:-}" != "--write" ]]; then
        cat >&2 <<EOF
❗检测到写/DDL 操作。Claude 不会擅自执行写——请人工确认 SQL 后追加 --write 重跑：

  scripts/prod.sh psql "$sql" --write

如果这其实是只读 SQL（例如表名里恰好含上述关键字），同样可以用 --write 强制放行。
EOF
        exit 3
      fi
    fi
    exec ssh "$HOST" psql "$sql"
    ;;

  psql-stdin)
    if [[ -t 0 ]]; then
      echo "psql-stdin 需要从管道/文件读 SQL，例如: cat q.sql | prod.sh psql-stdin" >&2
      exit 2
    fi
    exec ssh "$HOST" psql-stdin
    ;;

  logs|status|tail|health|pg-status|git-status|ps|disk|mem|whoami|cat|ls)
    exec ssh "$HOST" "$cmd" "$@"
    ;;

  *)
    echo "未知子命令: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
