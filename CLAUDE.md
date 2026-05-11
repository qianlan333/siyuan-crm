# CLAUDE.md

## 生产直连（直接查日志/数据/文件）

📖 **完整能力手册**：[docs/claude_prod_query_capabilities.md](docs/claude_prod_query_capabilities.md) — 所有子命令、白名单边界、查询配方、典型 cookbook 都在这里。

服务器: `ubuntu@www.youcangogogo.com`，SSH 别名 `crm-prod`，走 forced-command sandbox（`/usr/local/bin/claude-debug.sh`）。

**入口脚本**：[scripts/prod.sh](scripts/prod.sh)。所有跟生产相关的查询都走它，不要自己拼 ssh 命令。

### 常用

```bash
# 看应用日志（systemd）
scripts/prod.sh logs openclaw-wecom-postgres 200

# 项目自己的日志文件
scripts/prod.sh tail "/home/ubuntu/极简 crm/logs/app.log" 100

# 数据库状态
scripts/prod.sh pg-status

# 查任意 SQL（只读）
scripts/prod.sh psql "SELECT count(*) FROM users WHERE created_at > '2026-05-01';"

# 多行 SQL
cat <<'SQL' | scripts/prod.sh psql-stdin
SELECT u.id, u.name, count(o.id)
FROM users u LEFT JOIN orders o ON o.user_id = u.id
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 20;
SQL

# 读项目配置/上传文件
scripts/prod.sh cat "/home/ubuntu/极简 crm/app.py"
scripts/prod.sh ls "/home/ubuntu/极简 crm"

# 健康检查 / 进程 / 磁盘
scripts/prod.sh health
scripts/prod.sh ps
scripts/prod.sh disk
```

### 真只读，不可能写

- sandbox 走 PG `claude_ro` 账号 + `default_transaction_read_only=on`，所有写/DDL 在数据库层硬拒
- `.env / .pem / .pgpass / authorized_keys` 等敏感文件被 sandbox 黑名单拒
- `prod.sh` 还有客户端 `--write` 关键字检测但纯属冗余——PG 会先拒
- 要做写操作直接告诉用户"我无法执行写，请你登服务器跑 X"

### sandbox 子命令清单

`logs / status / tail / health / pg-status / git-status / ps / disk / mem / whoami / psql / psql-stdin / cat / ls`

`cat` 和 `ls` 限定路径白名单：`/home/ubuntu/`、`/var/log/`、`/etc/nginx/`。

### 一次性配置（首次拿到这个仓库后做一次）

1. 本地 `~/.ssh/config` 需有 `Host crm-prod` 段（`HostName www.youcangogogo.com`、`User ubuntu`、`IdentityFile ~/.ssh/claude_crm_debug`）。
2. 在 `.claude/settings.local.json` 的 `permissions.allow` 加：
   ```json
   "Bash(scripts/prod.sh:*)",
   "Bash(ssh crm-prod:*)"
   ```
3. 服务器侧若 `psql/cat/ls` 报 `unknown subcommand`，按 [docs/claude_prod_sandbox_extension.md](docs/claude_prod_sandbox_extension.md) 扩 sandbox。
