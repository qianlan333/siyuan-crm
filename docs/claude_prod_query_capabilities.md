# Claude 生产环境查询能力手册

> 给未来的 Claude 看（也给 reviewer 看）：通过 `scripts/prod.sh` 我能直接查生产服务器的什么数据，怎么查。
>
> 本文不是"指引"——是**能力清单 + 查询配方**，遇到具体问题直接对照抄。
>
> 🔒 **sandbox 模式：只读**。PG 走 `claude_ro` 账号 + `default_transaction_read_only=on`，所有写/DDL 在数据库层硬拒。文件读限白名单 + `.env / .pem / .pgpass / authorized_keys` 等敏感文件黑名单。

## 1. 通道架构（一句话理解）

```
本地 Claude
    │  scripts/prod.sh <子命令> [参数]
    ▼
ssh crm-prod    （别名 → ubuntu@www.youcangogogo.com，私钥 ~/.ssh/claude_crm_debug）
    │  forced-command
    ▼
/usr/local/bin/claude-debug.sh    （服务器侧 sandbox，白名单子命令）
    │
    ├── psql / psql-stdin → PostgreSQL (DATABASE_URL from /home/ubuntu/.openclaw-wecom-pg.env)
    ├── cat / ls          → /home/ubuntu/, /var/log/, /etc/nginx/
    ├── tail              → /var/log/, /home/ubuntu/极简 crm/logs/, /home/ubuntu/logs/
    ├── logs / status     → systemd: openclaw-wecom-postgres / nginx / postgresql
    └── health / pg-status / git-status / ps / disk / mem / whoami
```

服务器：`VM-0-17-ubuntu`（腾讯云）。项目目录：`/home/ubuntu/极简 crm/`。
应用：systemd unit `openclaw-wecom-postgres.service` → Flask 监听 `127.0.0.1:5001`，前面挂 nginx。
数据库：PostgreSQL，库名 `openclaw_wecom`，用户 `openclaw`。

## 2. 所有子命令速查表

| 子命令 | 参数 | 用途 | 示例 |
|---|---|---|---|
| `psql` | SQL（含空格 OK） | 单条 SQL，写需 `--write` | `prod.sh psql "SELECT count(*) FROM questionnaires;"` |
| `psql-stdin` | （SQL 走 stdin） | 多行 SQL | `cat q.sql \| prod.sh psql-stdin` |
| `cat` | 绝对路径 | 读文件 | `prod.sh cat "/home/ubuntu/极简 crm/app.py"` |
| `ls` | 路径（默认 `/home/ubuntu`） | 列目录 | `prod.sh ls "/home/ubuntu/极简 crm/"` |
| `tail` | 路径 [行数=200] | 读日志尾部 | `prod.sh tail "/home/ubuntu/极简 crm/logs/app.log" 500` |
| `logs` | service [n=200] | journalctl | `prod.sh logs openclaw-wecom-postgres 100` |
| `status` | service | systemctl status | `prod.sh status nginx` |
| `health` | – | curl localhost:5001/health | `prod.sh health` |
| `pg-status` | – | pg_isready + 当前连接数 | `prod.sh pg-status` |
| `git-status` | – | 项目 git status + log -3 | `prod.sh git-status` |
| `ps` / `disk` / `mem` | – | 进程/磁盘/内存摘要 | `prod.sh disk` |
| `whoami` | – | 当前 sandbox 边界 | `prod.sh whoami` |

**白名单边界**

- 服务名（`logs`/`status`）只接受：`openclaw-wecom-postgres` / `nginx` / `postgresql`
- 日志路径（`tail`）前缀：`/var/log/` / `/home/ubuntu/极简 crm/logs/` / `/home/ubuntu/logs/`
- 文件路径（`cat`/`ls`）前缀：`/home/ubuntu/` / `/var/log/` / `/etc/nginx/`
- 拒绝任何含 `..` `$` `;` `&` `|` `` ` `` 的路径
- `tail` 上限 5000 行；`logs` 上限 2000 行

## 3. 写操作（不可能发生）

sandbox 当前是**真只读**：

- `psql` 走 PG 用户 `claude_ro`，仅有 SELECT 权限
- 该用户 `ALTER USER ... SET default_transaction_read_only = on`，事务层面强制只读
- 任何 `UPDATE / DELETE / INSERT / CREATE / DROP / TRUNCATE / ALTER` 直接被 PG 拒：
  ```
  ERROR: cannot execute UPDATE in a read-only transaction
  ```

`prod.sh` 还保留了一个客户端 `--write` 关键字检测，纯粹是冗余防呆——即使绕过本地脚本，PG 也会拒。

**结论**：你不可能用这个通道改任何数据。要做写操作就直接告诉用户"我无法执行写，请你登服务器跑 X"。

## 4. 数据库能查什么

### 4.1 库总览

```bash
# 所有表
prod.sh psql "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;"

# 某表的列
prod.sh psql "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='questionnaire_submissions' ORDER BY ordinal_position;"

# 表的行数
prod.sh psql "SELECT n_live_tup FROM pg_stat_user_tables WHERE relname='users';"

# 索引
prod.sh psql "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='questionnaire_submissions';"

# 找包含某关键字的表
prod.sh psql "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ILIKE '%user%' ORDER BY 1;"
```

### 4.2 已知核心表（按业务域）

| 业务域 | 关键表 |
|---|---|
| 问卷 | `questionnaires` / `questionnaire_questions` / `questionnaire_options` / `questionnaire_submissions` / `questionnaire_submission_answers` / `questionnaire_score_rules` / `questionnaire_external_push_logs` / `questionnaire_scrm_apply_logs` |
| 营销自动化 | `marketing_automation_question_rules`（和 `app.py` 里 automation 相关表） |

执行 `prod.sh psql "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;"` 拿全量表名。

### 4.3 跨表 JOIN 示例

```bash
# 问卷 21 所有提交 + 答题明细（JSON 形式聚合）
prod.sh psql "
SELECT s.id, s.mobile_snapshot, s.submitted_at,
       jsonb_agg(jsonb_build_object(
         'q', q.sort_order,
         'title', q.title,
         'answer', COALESCE(a.selected_option_texts_snapshot::text, a.text_value)
       ) ORDER BY q.sort_order) AS answers
FROM questionnaire_submissions s
JOIN questionnaire_submission_answers a ON a.submission_id = s.id
JOIN questionnaire_questions q ON q.id = a.question_id
WHERE s.questionnaire_id = 21
GROUP BY s.id
ORDER BY s.submitted_at DESC
LIMIT 5;"
```

### 4.4 多行 SQL（推荐 psql-stdin）

```bash
cat <<'SQL' | prod.sh psql-stdin
\timing on
SELECT date_trunc('day', submitted_at) AS day, count(*)
FROM questionnaire_submissions
WHERE questionnaire_id = 21
GROUP BY 1 ORDER BY 1;
SQL
```

### 4.5 EXPLAIN / ANALYZE

```bash
prod.sh psql "EXPLAIN ANALYZE SELECT * FROM questionnaire_submissions WHERE questionnaire_id=21;"
```

## 5. 文件能读什么

### 5.1 应用代码

```bash
prod.sh cat "/home/ubuntu/极简 crm/app.py" | head -100
prod.sh ls "/home/ubuntu/极简 crm/"
prod.sh ls "/home/ubuntu/极简 crm/openclaw_service/"
```

### 5.2 配置/环境变量

```bash
# .env 文件被 sandbox 黑名单拒（生产是真只读，不暴露密码）：
prod.sh cat /home/ubuntu/.openclaw-wecom-pg.env
# → path not in whitelist or matches denied pattern
```

如需查应用读了哪些 env，去看代码：`prod.sh cat "/home/ubuntu/极简 crm/app.py"` 看 `os.environ.get(...)` 调用。

### 5.3 nginx 配置

```bash
prod.sh ls /etc/nginx/
prod.sh cat /etc/nginx/sites-enabled/default   # 实际文件名按 ls 结果定
```

### 5.4 上传/数据文件

服务器项目目录里 `.tar.gz`、上传的 Excel 等都在 `/home/ubuntu/` 下。`cat` 二进制会乱码，这种情况下用 `ls -la` 看大小、修改时间即可。

## 6. 日志能看什么

### 6.1 应用 stdout（systemd 捕获）

```bash
# 默认最近 200 行
prod.sh logs openclaw-wecom-postgres
# 最近 500 行
prod.sh logs openclaw-wecom-postgres 500
```

`logs` 没有 `--since` / `-f`——是一次性快照。要看更早的需要拉更大 N（最大 2000）然后本地 grep。

### 6.2 应用自写日志（按文件）

```bash
prod.sh tail "/home/ubuntu/极简 crm/logs/app.log" 500
prod.sh ls "/home/ubuntu/极简 crm/logs/"
```

### 6.3 nginx 访问/错误日志

```bash
prod.sh tail /var/log/nginx/access.log 500
prod.sh tail /var/log/nginx/error.log 200
```

### 6.4 系统层

```bash
prod.sh logs nginx 100
prod.sh logs postgresql 100
prod.sh status openclaw-wecom-postgres
```

## 7. 不能做的事（边界）

- ❌ 写文件、改配置、`scp` 上传
- ❌ 重启服务（`systemctl restart` 等）
- ❌ 部署/发布
- ❌ 跑任意 shell 命令、grep/find/sed 远端文件（只能 `cat` 整文件再本地处理）
- ❌ 读白名单外的路径（`/root/`、`/etc/shadow` 之类）
- ❌ 端口转发 / SSH 隧道（forced-command 已禁止 port-forwarding）
- ❌ 长连接 / `psql` 交互模式（每次都是一次性命令）

需要这些能力时直接告诉用户"我做不到，请你登服务器跑 X"。

## 8. 典型场景 cookbook

### 场景 A：用户报告"我提交了问卷但没看到 SCRM 推送"

```bash
# 1. 找用户最近的问卷提交
prod.sh psql "SELECT id, questionnaire_id, mobile_snapshot, submitted_at FROM questionnaire_submissions WHERE mobile_snapshot='13800138000' ORDER BY submitted_at DESC LIMIT 5;"

# 2. 看推送日志
prod.sh psql "SELECT * FROM questionnaire_scrm_apply_logs WHERE submission_id=<上面的id> ORDER BY created_at DESC;"

# 3. 看应用日志附近时间窗
prod.sh logs openclaw-wecom-postgres 1000 | grep -A 3 "submission_id=<id>"
```

### 场景 B：某接口 5xx

```bash
prod.sh tail /var/log/nginx/error.log 200
prod.sh logs openclaw-wecom-postgres 500 | grep -E "ERROR|Traceback|500 "
prod.sh status openclaw-wecom-postgres
```

### 场景 C：数据库慢

```bash
prod.sh pg-status                                        # 连接数
prod.sh psql "SELECT pid, state, wait_event, query_start, left(query,80) FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start;"
prod.sh psql "SELECT relname, n_live_tup, n_dead_tup, last_autovacuum FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 10;"
```

### 场景 D：分析某问卷全量提交（参见 [docs/claude_prod_sandbox_extension.md](claude_prod_sandbox_extension.md) 同思路）

参考此前对问卷 21 的报告——典型套路：
1. `pg_tables` 找相关表
2. `information_schema.columns` 看字段
3. 主表过滤 + 子表 JOIN 取明细
4. 单选题用 `jsonb_array_elements_text` 展开 `selected_option_texts_snapshot` 做分布
5. 文本题直接 `text_value` 取出，本地按主题归类

### 场景 E：服务器空间不足

```bash
prod.sh disk
prod.sh ls "/home/ubuntu/极简 crm/logs/"   # 看哪些 log 占空间
```

## 9. 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `Permission denied (publickey,password)` | 别的 key 误用 | 确认走 `ssh crm-prod`（IdentityFile=claude_crm_debug） |
| `unknown subcommand: xxx` | sandbox 没该子命令 | 看 [docs/claude_prod_sandbox_extension.md](claude_prod_sandbox_extension.md)，可能要扩 `~/claude-debug.sh` |
| `path not in whitelist` | 路径前缀不在白名单 | 改用允许前缀；或让用户在 sandbox 里加白名单 |
| `service not in whitelist` | systemd unit 不在白名单 | 同上 |
| psql `relation "x" does not exist` | 表名猜错 | 先跑 `pg_tables` 列表确认真实名 |
| `❗检测到写/DDL 操作` | 本地写拦截 | **不要**自己加 `--write`，把 SQL 贴给用户确认 |

## 10. 一次性配置

### 10.1 同一台 Mac 上的后续会话 → 不用配

私钥 `~/.ssh/claude_crm_debug` 是用户级的，存在 `~/.ssh/` 下，跨会话/跨 worktree 都在。`~/.ssh/config` 的 `Host crm-prod` 段也是用户级，配一次就行。`.claude/settings.local.json` 是项目级，配一次也行。

**所以同一台 Mac 上，新开一个 Claude 会话直接 `scripts/prod.sh psql "..."` 就能用，无需重配。**

### 10.2 换设备 / 新机器 → 必须重做密钥环节

私钥**故意不进 git**（仓库里只有调用脚本，没有凭证）。换机器要做：

**步骤 1**：从老机器把私钥 + 公钥拷到新机器
```bash
# 在老机器
scp ~/.ssh/claude_crm_debug    新机器:~/.ssh/
scp ~/.ssh/claude_crm_debug.pub 新机器:~/.ssh/
# 新机器上
chmod 600 ~/.ssh/claude_crm_debug
chmod 644 ~/.ssh/claude_crm_debug.pub
```

**或者**（不想拷私钥时）：在新机器**生成新 key**，把公钥追加到服务器 `~/.ssh/authorized_keys`：
```bash
# 新机器
ssh-keygen -t ed25519 -f ~/.ssh/claude_crm_debug2 -C "claude-crm-debug-newdev" -N ""
cat ~/.ssh/claude_crm_debug2.pub
# 把输出贴到服务器（用你常规通道登）：
echo 'ssh-ed25519 AAAA... claude-crm-debug-newdev' >> ~/.ssh/authorized_keys
# ⚠️ 关键：新公钥前面要带上 forced-command 前缀，否则就开了一把不受限的后门：
#   command="/usr/local/bin/claude-debug.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...
```

**步骤 2**：新机器加 `~/.ssh/config` 段
```
Host crm-prod
    HostName www.youcangogogo.com
    User ubuntu
    IdentityFile ~/.ssh/claude_crm_debug   # 或 _debug2
    IdentitiesOnly yes
    ServerAliveInterval 60
```

**步骤 3**：新机器项目根 `.claude/settings.local.json`
```json
{
  "permissions": {
    "allow": [
      "Bash(scripts/prod.sh:*)",
      "Bash(ssh crm-prod:*)"
    ]
  }
}
```

**步骤 4**：验证
```bash
ssh crm-prod whoami    # 应输出 user=ubuntu cwd=/home/ubuntu host=VM-0-17-ubuntu
```

### 10.3 服务器侧 → 一般不用动

服务器 `~/.ssh/authorized_keys` 已经有这把 key 的公钥（用户在 2026-05-08 配的）+ forced-command 绑定 `/usr/local/bin/claude-debug.sh`。
sandbox 已扩展支持 `psql/cat/ls`（见 [docs/claude_prod_sandbox_extension.md](claude_prod_sandbox_extension.md)）。

只有以下情况要再动服务器：
- 想加新子命令（比如 `redis-cli`、`gunicorn-restart`）
- 想加新白名单路径（比如 `/opt/...`）
- 想加新服务名到 `logs`/`status` 白名单
- 旧 key 泄露要轮换（删 `authorized_keys` 对应行 + 客户端用新 key）

### 10.4 检查清单（不通时按这个排查）

| 检查 | 命令 | 期望 |
|---|---|---|
| 私钥在 | `ls -l ~/.ssh/claude_crm_debug` | 600 权限，文件存在 |
| ssh config 有别名 | `grep -A 5 "Host crm-prod" ~/.ssh/config` | 看到 5 行配置 |
| ssh 通 | `ssh crm-prod whoami` | `user=ubuntu ... host=VM-0-17-ubuntu` |
| sandbox 命令完整 | `ssh crm-prod help` | 看到 14 个子命令 |
| 本地脚本可执行 | `ls -l scripts/prod.sh` | 有 x 权限 |
| 项目权限放行 | `cat .claude/settings.local.json` | 有 `Bash(scripts/prod.sh:*)` |

---

**记忆约束**：本文档配套的硬规则已写进自动记忆 `feedback_prod_writes.md` —— 任何写/DDL 操作必须先贴 SQL 让用户确认再加 `--write`，不允许自动通过。
