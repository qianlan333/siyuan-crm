# Cloud Orchestrator 自唤醒（cron）

> Cron 定时跑一次「外部 Cloud Agent」，自动扫描 → 调 MCP 工具 → 落 draft plan，运营在 admin console 审核 → confirm → 真发。

## 链路总览

```
cron (system / supervisor)
   │
   ↓
scripts/run_cloud_orchestrator_scan.py
   │  (薄壳：解析 env + 调 domain 模块)
   ↓
wecom_ability_service.domains.cloud_orchestrator.external_agent.orchestrate
   │
   ├─→ Anthropic Messages API（claude-opus-4-7 默认）
   │     • prompt caching 双 breakpoint（system + tools 末尾）
   │     • tool-use loop（max 12 iter / 20 tool calls / 4096 tokens）
   │
   └─→ POST http://127.0.0.1:5000/mcp（JSON-RPC 2.0）
         │  • tools/list — 拉 cloud orchestrator 16 个工具
         │  • tools/call — 注入 __trace_id / __session_id / __operator
         ↓
       mcp_adapter → cloud_orchestrator.dispatch_cloud_tool
         ├─→ broadcast_planner（draft / simulate）
         ├─→ campaigns / segments / questionnaire_explorer
         └─→ cloud_agent_audit_log（自动写审计 + trace_id 三端贯穿）
```

## 必填环境变量

| 变量 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API Key（生产环境放 systemd EnvironmentFile，不要写进 cron 文件） |

## 可选环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `ANTHROPIC_BASE_URL` | 官方 | 自定义 endpoint（私有部署 / 代理） |
| `APP_HOST` | `127.0.0.1` | 本地 MCP 服务 host |
| `APP_PORT` | `5000` | 本地 MCP 服务端口（生产 `5001`） |
| `MCP_BEARER_TOKEN` | — | 与 mcp_adapter 约定的 Bearer token；兼容老名 `AUTOMATION_INTERNAL_API_TOKEN` |
| `CLOUD_ORCH_SCAN_OPERATOR` | `cloud_scheduler` | 写入 audit log 的 operator |
| `CLOUD_ORCH_SCAN_PROMPT` | 沉默激活 | 覆盖默认 user prompt |
| `CLOUD_ORCH_SCAN_SYSTEM` | 内置 | 覆盖默认 system prompt |
| `CLOUD_ORCH_SCAN_MODEL` | `claude-opus-4-7` | 模型；省钱可换 `claude-sonnet-4-6` |
| `CLOUD_ORCH_SCAN_MAX_ITER` | `12` | 最大 tool-use loop 迭代 |
| `CLOUD_ORCH_SCAN_MAX_TOOLS` | `20` | 单次任务最大工具调用次数 |
| `CLOUD_ORCH_SCAN_MAX_TOKENS` | `4096` | 单次响应 max_tokens |
| `CLOUD_ORCH_SCAN_MCP_RETRIES` | `3` | MCP 调用重试次数（1s/3s/9s 退避） |
| `CLOUD_ORCH_SCAN_MCP_TIMEOUT` | `60` | MCP 单次请求 timeout（秒） |
| `CLOUD_ORCH_SCAN_ALLOWED_TOOLS` | — | CSV 工具白名单，仅暴露这些工具给 Agent |

## 退出码

| 退出码 | 含义 | 排查 |
|---|---|---|
| `0` | 正常完成（含 budget 截断） | 看 stdout 的 summary JSON |
| `1` | 缺 `ANTHROPIC_API_KEY` | 检查 systemd EnvironmentFile |
| `2` | Claude API 失败 | `summary.error` 看具体错（鉴权 / 模型不可用 / 网络） |
| `3` | 本地 MCP 不可达 / 无可用工具 | 检查 5000/5001 端口、`MCP_BEARER_TOKEN`、`/mcp` 端点是否注册 |

## 生产部署（systemd timer 推荐）

### 1. 写 EnvironmentFile

```bash
sudo tee /etc/openclaw/cloud-orch.env > /dev/null <<'EOF'
ANTHROPIC_API_KEY=sk-ant-...
APP_HOST=127.0.0.1
APP_PORT=5001
MCP_BEARER_TOKEN=<生产 token>
CLOUD_ORCH_SCAN_OPERATOR=cloud_scheduler_prod
EOF
sudo chmod 600 /etc/openclaw/cloud-orch.env
```

### 2. 写 systemd service

```bash
sudo tee /etc/systemd/system/cloud-orch-scan.service > /dev/null <<'EOF'
[Unit]
Description=Cloud Orchestrator self-wakeup scan
Wants=cloud-orch-scan.timer

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/极简 crm
EnvironmentFile=/etc/openclaw/cloud-orch.env
ExecStart=/usr/bin/python3 /home/ubuntu/极简\ crm/scripts/run_cloud_orchestrator_scan.py
StandardOutput=append:/home/ubuntu/极简 crm/logs/cloud_orch_scan.log
StandardError=append:/home/ubuntu/极简 crm/logs/cloud_orch_scan.log
EOF
```

### 3. 写 systemd timer

```bash
sudo tee /etc/systemd/system/cloud-orch-scan.timer > /dev/null <<'EOF'
[Unit]
Description=Cloud Orchestrator self-wakeup daily

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cloud-orch-scan.timer
```

### 4. 验证

```bash
# 列待跑的 timer
systemctl list-timers cloud-orch-scan*

# 立即触发一次（不等 09:00）
sudo systemctl start cloud-orch-scan.service

# 看日志
tail -100 /home/ubuntu/极简\ crm/logs/cloud_orch_scan.log

# 查 audit
scripts/prod.sh psql "SELECT trace_id, tool_name, status, error_message
                      FROM cloud_agent_audit_log
                      WHERE created_at > now() - interval '1 hour'
                      ORDER BY id DESC LIMIT 20;"
```

## 多场景 cron（不改代码）

为不同场景配不同的 systemd unit + 不同 EnvironmentFile，复用同一个脚本：

```ini
# /etc/openclaw/cloud-orch-newuser.env
ANTHROPIC_API_KEY=sk-ant-...
CLOUD_ORCH_SCAN_OPERATOR=cloud_scheduler_newuser
CLOUD_ORCH_SCAN_PROMPT=扫描注册 7 天内未完成首次互动的 new_user 池成员，按 owner_userid 分组建 draft 计划...
CLOUD_ORCH_SCAN_ALLOWED_TOOLS=search_segment_members,query_member_interaction_stats,draft_broadcast_plan
```

```ini
# /etc/openclaw/cloud-orch-revival.env
ANTHROPIC_API_KEY=sk-ant-...
CLOUD_ORCH_SCAN_OPERATOR=cloud_scheduler_revival
CLOUD_ORCH_SCAN_PROMPT=扫描近 30 天沉默的 inactive_focus 用户，做 silent_wake 激活...
CLOUD_ORCH_SCAN_MODEL=claude-sonnet-4-6
CLOUD_ORCH_SCAN_MCP_RETRIES=5
```

每个场景一个 timer，0 代码改动。

## 测试

```bash
# 跑单元测试（不依赖 anthropic SDK 也不连 PG）
python3 -m pytest tests/test_cloud_orchestrator_external_agent.py tests/test_run_cloud_orchestrator_scan.py -v

# 23 个 case 覆盖：
# - call_mcp / discover_tools / execute_tool / call_claude
# - orchestrate 主流程：缺 key / mcp 挂 / 无工具 / happy / blocked tool / tool budget / max iter / tool 异常恢复
# - 薄壳脚本：_resolve_env / run / main
```

## Troubleshooting

### exit_code=1 (missing API key)
- 检查 systemd EnvironmentFile 是否生效：`systemctl show cloud-orch-scan.service | grep -i environment`
- 检查文件权限：`ls -l /etc/openclaw/cloud-orch.env`（应该是 600 + ubuntu owner）

### exit_code=2 (claude api failed)
- 看 summary.error 的 message
- `messages.create failed: ... 401` → API key 无效
- `messages.create failed: ... model not found` → 模型权限问题，换 `CLOUD_ORCH_SCAN_MODEL=claude-sonnet-4-6`
- `messages.create failed: ... rate limit` → 等会再跑或调小 `CLOUD_ORCH_SCAN_MAX_ITER`

### exit_code=3 (mcp unreachable)
- 检查后端是否在跑：`scripts/prod.sh ps | grep gunicorn`
- 检查端口：`scripts/prod.sh psql "SELECT 1"` 能跑说明 PG 正常但 web server 可能挂了
- 检查 token：`curl -X POST http://127.0.0.1:5001/mcp -H 'Authorization: Bearer ...' -d '{"jsonrpc":"2.0","id":"1","method":"tools/list"}'`

### Agent 调到 commit_broadcast_plan 被拦截
- 这是设计，cron 不允许真发；UI 上让运营 confirm
- 如果要让 cron 也能 commit（不推荐），需要在 `external_agent.DEFAULT_BLOCKED_TOOL_NAMES` 里删掉对应名字 + 写一个 approval token 来源

### Agent 跑了但没产出 plan
- 看 stdout 的 `tool_call_log` 数组：哪几个工具被调了、参数、结果
- `query_recent_audit_logs` MCP tool（由 Agent 自己调）会查 cloud_agent_audit_log 看错误
- 直接查表：`scripts/prod.sh psql "SELECT * FROM cloud_broadcast_plans WHERE created_by_session = '<session_id>';"`

## 相关文件

- `scripts/run_cloud_orchestrator_scan.py` — cron 脚本（130 行薄壳）
- `wecom_ability_service/domains/cloud_orchestrator/external_agent.py` — 核心 tool-use loop（domain 层）
- `wecom_ability_service/domains/cloud_orchestrator/mcp_tools.py` — Cloud Agent 16 个工具的 catalog + dispatch
- `wecom_ability_service/mcp_adapter.py` — MCP HTTP server（`POST /mcp` JSON-RPC 2.0）
- `tests/test_cloud_orchestrator_external_agent.py` — 17 个 case 覆盖核心
- `tests/test_run_cloud_orchestrator_scan.py` — 6 个 case 覆盖薄壳
