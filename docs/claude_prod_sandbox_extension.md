# Claude 生产 Sandbox 扩展 — 部署指引

本文给**服务器管理员（你）**看。Claude 当前通过 `claude_crm_debug` 这把 SSH key 登 `ubuntu@www.youcangogogo.com`，被 forced-command 锁在 `~/claude-debug.sh` 这个受限 sandbox 里，只能跑预设子命令。

为了让 Claude 能"查任意 PG 表 + 读项目文件"，需要在 sandbox 里加 3 个新子命令：`psql`、`psql-stdin`、`cat`、`ls`。

下面的步骤都在**服务器上**执行。

## Step 1：备份现有脚本

```bash
ssh ubuntu@www.youcangogogo.com   # 你自己的常规通道，不是 claude_crm_debug
cp ~/claude-debug.sh ~/claude-debug.sh.bak.$(date +%Y%m%d)
```

## Step 2：在 case 分支前加入新子命令

打开 `~/claude-debug.sh`，找到形如：

```bash
case "$cmd" in
  logs) ... ;;
  status) ... ;;
  tail) ... ;;
  ...
  whoami) ... ;;
  *) echo "未知子命令 ..." ; exit 2 ;;
esac
```

在 `*)` 默认分支**之前**，插入以下 4 个新分支：

```bash
  psql)
    # 用法: ssh crm-prod psql "<SQL>"
    SQL="${ARGS[*]:-}"
    if [[ -z "$SQL" ]]; then
      echo "用法: psql <SQL>" >&2; exit 2
    fi
    set -a; source "$HOME/.openclaw-wecom-pg.env"; set +a
    exec psql "$DATABASE_URL" \
      -v ON_ERROR_STOP=1 \
      -P pager=off \
      -c "$SQL"
    ;;

  psql-stdin)
    # 用法: ssh crm-prod psql-stdin < big_query.sql
    set -a; source "$HOME/.openclaw-wecom-pg.env"; set +a
    exec psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -P pager=off
    ;;

  cat)
    # 用法: ssh crm-prod cat <path>
    P="${ARGS[0]:-}"
    if [[ -z "$P" ]]; then echo "用法: cat <path>" >&2; exit 2; fi
    case "$P" in
      *..*) echo "cat: 禁止 '..' 路径穿越" >&2; exit 2 ;;
    esac
    case "$P" in
      /home/ubuntu/*|/var/log/*|/etc/nginx/*) ;;
      *) echo "cat: 路径不在白名单 (/home/ubuntu/, /var/log/, /etc/nginx/)" >&2; exit 2 ;;
    esac
    exec cat -- "$P"
    ;;

  ls)
    # 用法: ssh crm-prod ls [path]
    P="${ARGS[0]:-/home/ubuntu}"
    case "$P" in
      *..*) echo "ls: 禁止 '..'" >&2; exit 2 ;;
    esac
    case "$P" in
      /home/ubuntu*|/var/log*|/etc/nginx*) ;;
      *) echo "ls: 路径不在白名单" >&2; exit 2 ;;
    esac
    exec ls -lah -- "$P"
    ;;
```

> **注意**：上面用了 `ARGS` 数组——具体变量名需对照你脚本里现有 case（比如可能叫 `$@`、`$2`、或别的解析方式）。如果你的脚本是用 `cmd="$1"; shift` 然后 `case $cmd` 配 `$@` 取剩余参数，则把 `${ARGS[*]}` 换成 `$*`、`${ARGS[0]}` 换成 `$1`。

## Step 3：在帮助文本里加上新子命令

找到 `whoami` 或脚本顶部的 help 字符串（开头列子命令的那段），在末尾追加：

```
  psql <SQL>               执行任意 SQL（含写）。本地脚本会拦截写操作要求 --write。
  psql-stdin               从 stdin 读多行 SQL
  cat <path>               读 /home/ubuntu/, /var/log/, /etc/nginx/ 下的文件
  ls [path]                列目录（同上白名单）
```

## Step 4：本地验证（用 claude_crm_debug 这把 key）

```bash
# 读一行任意配置
ssh -i ~/.ssh/claude_crm_debug ubuntu@www.youcangogogo.com cat /home/ubuntu/.openclaw-wecom-pg.env

# 跑一条 SELECT
ssh -i ~/.ssh/claude_crm_debug ubuntu@www.youcangogogo.com psql "SELECT current_database(), current_user;"

# 列项目目录
ssh -i ~/.ssh/claude_crm_debug ubuntu@www.youcangogogo.com 'ls /home/ubuntu/极简 crm'
```

3 条都成功之后，告诉 Claude，本地脚本就能用了。

## Step 5（可选）：限制 cat 不能读敏感文件

如果担心 `.env`、`.pgpass` 等被 Claude 读出来上下文外泄，可以再加一层黑名单：

```bash
  cat)
    P="${ARGS[0]:-}"
    case "$P" in
      *.env|*.pem|*.key|*authorized_keys*|*.pgpass)
        echo "cat: 该类型文件不允许读" >&2; exit 2 ;;
    esac
    # ... 后面接白名单检查 ...
```

是否启用看你的偏好——Claude 知道 `DATABASE_URL` 后多了个把柄，但也意味着调试能力强很多。
