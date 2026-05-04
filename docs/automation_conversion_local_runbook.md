# 自动化转化本地联调 Runbook

## 1. 启动本地服务

```bash
cd /Users/qianlan/.codex/worktrees/8d7e/aicrm-new-codex-1
python3.11 -m venv .venv311-codex
source .venv311-codex/bin/activate
pip install -r requirements.txt
python app.py init-db
python app.py run
```

默认地址：

- `http://127.0.0.1:5000`

## 2. 配置本地环境项

推荐直接在后台设置页或环境变量写入以下配置：

- `AUTOMATION_INTERNAL_API_TOKEN`
- `MCP_BEARER_TOKEN`（仅 legacy 兼容需要时保留）
- `OPENCLAW_WEBHOOK_URL`
- `AUTOMATION_ACTIVATION_WEBHOOK_TOKEN`（仅 legacy 兼容需要时保留）
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_URL`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN`
- `QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS`
- `MESSAGE_ACTIVITY_DB_HOST`
- `MESSAGE_ACTIVITY_DB_PORT`
- `MESSAGE_ACTIVITY_DB_NAME`
- `MESSAGE_ACTIVITY_DB_USER`
- `MESSAGE_ACTIVITY_DB_PASS`

如果只是本地联调，也可以在 app context 里直接写 `app_settings`：

```bash
python scripts/seed_automation_conversion_demo.py --write-settings \
  --internal-api-token internal-local-token \
  --mcp-token mcp-local-token \
  --openclaw-webhook-url http://127.0.0.1:19090/openclaw-focus \
  --activation-webhook-token activation-local-token \
  --questionnaire-webhook-url http://127.0.0.1:19090/questionnaire-submit \
  --questionnaire-webhook-token questionnaire-local-token
```

## 3. 启动本地 mock webhook

```bash
python - <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size).decode()
        print(f"\\n== {self.path} ==")
        print(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

HTTPServer(("127.0.0.1", 19090), Handler).serve_forever()
PY
```

## 4. 准备测试问卷

1. 打开 `/admin/questionnaires`
2. 新建一份问卷
3. 至少准备：
   - 1 道单选或多选题
   - 1 道必填手机号题
4. 打开 `/admin/automation-conversion`
5. 选择这份问卷作为自动化转化问卷
6. 配置至少 1 道关键题
7. 配置普通跟进 / 重点跟进门槛
8. 配置 5 个池子的沉默阈值
9. 如果要联调自动 SOP，再打开 `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop`
10. 至少为 `new_user / inactive_normal / active_normal` 配置：
   - enabled
   - max_day_count
   - send_time
   - timezone
   - day1 模板

## 5. 准备测试客户

运行 demo seed：

```bash
python scripts/seed_automation_conversion_demo.py
```

脚本会准备两个样本客户：

- `wm_demo_normal` / `13800138001` / `owner_userid=QianLan`
- `wm_demo_focus` / `13800138002` / `owner_userid=sales_demo_02`

## 6. 跑普通路径

1. 提交问卷：

```bash
curl -X POST http://127.0.0.1:5000/api/h5/questionnaires/<slug>/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "external_userid":"wm_demo_normal",
    "answers":{
      "<问题id>":"<普通答案id>",
      "<手机号题id>":"13800138001"
    }
  }'
```

2. 验证当前仍在新用户池或等待试用开通：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/marketing-automation/config/preview \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_normal"}'
```

3. 写入试用开通事实：

```bash
python scripts/seed_automation_conversion_demo.py --mark-trial-opened wm_demo_normal
```

4. 再次预览，确认进入 `pool/inactive_normal`

5. 回写激活：

```bash
curl -X POST http://127.0.0.1:5000/api/customers/automation/activation-webhook \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer internal-local-token' \
  -d '{"mobile":"13800138001","activated_at":"2026-04-06 10:10:00"}'
```

6. 再次预览，确认进入 `pool/active_normal`

## 7. 跑重点跟进路径

1. 提交问卷：

```bash
curl -X POST http://127.0.0.1:5000/api/h5/questionnaires/<slug>/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "external_userid":"wm_demo_focus",
    "answers":{
      "<问题id>":"<命中重点跟进答案id>",
      "<手机号题id>":"13800138002"
    }
  }'
```

2. 写入试用开通事实：

```bash
python scripts/seed_automation_conversion_demo.py --mark-trial-opened wm_demo_focus
```

3. 预览确认进入 `pool/inactive_focus`

4. 验证重点跟进池来消息推送 OpenClaw：

```bash
python scripts/seed_automation_conversion_demo.py --insert-focus-message
```

预期本地 mock webhook 收到 `/openclaw-focus`。

5. 回写激活：

```bash
curl -X POST http://127.0.0.1:5000/api/customers/automation/activation-webhook \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer internal-local-token' \
  -d '{"mobile":"13800138002","activated_at":"2026-04-06 10:11:00"}'
```

6. 预览确认进入 `pool/active_focus`

## 8. 验证侧边栏人工改判

普通转重点：

```bash
curl -X POST http://127.0.0.1:5000/api/sidebar/marketing-status/set-followup-segment \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_normal","owner_userid":"QianLan","operator":"qa_local","followup_segment":"focus"}'
```

重点转普通：

```bash
curl -X POST http://127.0.0.1:5000/api/sidebar/marketing-status/set-followup-segment \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_focus","owner_userid":"sales_demo_02","operator":"qa_local","followup_segment":"normal"}'
```

然后查询状态：

```bash
curl "http://127.0.0.1:5000/api/sidebar/marketing-status?external_userid=wm_demo_focus"
```

## 9. 验证自动化转化首页 / 阶段页 / send 页面

1. 打开 `/admin/automation-conversion`
2. 验证首页有：
   - `立即刷新一次`
   - `自动启动时间窗`
   - 每个阶段都包含 `查看名单 / 创建群发`
3. 打开 `/admin/automation-conversion/programs/<program_id>/member-ops?stage=new-user&panel=members`
4. 点击 `创建群发` 进入 `/admin/automation-conversion/programs/<program_id>/member-ops?stage=new-user&panel=send`
5. 验证页面显示 `官方群发`
6. 打开 `/admin/automation-conversion/programs/<program_id>/member-ops?stage=inactive-focus&panel=send`
7. 验证页面显示 `AI 批量处理`

## 10. 验证非重点阶段官方群发

`new-user / inactive-normal / active-normal / silent / won` 都走这个接口：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/automation-conversion/stage/new-user/manual-send \
  -H 'Content-Type: application/json' \
  -d '{
    "content":"这是本地联调官方群发消息",
    "operator":"qa_local"
  }'
```

如果要带图片，当前支持本地上传图片预览，也支持直接按 `image media_id` 调接口：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/automation-conversion/stage/silent/manual-send \
  -H 'Content-Type: application/json' \
  -d '{
    "content":"这是沉默池唤醒消息",
    "image_media_ids":["img-media-001"],
    "operator":"qa_local"
  }'
```

后台 `member-ops` 页面保留 no-JS 表单兜底入口，用于浏览器 session、admin action token 和 multipart 图片实际发送：

- 当前路径：`POST /admin/automation-conversion/programs/<program_id>/member-ops/stage/<stage_key>/send`
- 旧路径：`/admin/automation-conversion/stage/<stage_key>/send` 已下线，不再注册
- 注意：`manual-send` API 仍保持 JSON/API 调用协议，不承担页面 multipart 实际发送；图片预览仍使用 `/manual-send/preview`

预期：

- 返回 `ok / stage_key / total_target_count / sent_count / skipped_count / skipped_reasons / record_id / task_ids`
- 不按 owner 分桶
- `silent / won` 也允许发送

## 10.1 验证自动 SOP v1

当前自动 SOP 只覆盖：

- `new_user`
- `inactive_normal`
- `active_normal`

业务规则：

- 名单执行时现算
- 只对当前仍在该池子的成员发
- 重复进同池不重来
- 离池期间错过的 day 不补发
- SOP 和手工群发不去重
- 只支持文本 + 图片

手动触发 runner：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/automation-conversion/sop/run-due \
  -H 'Authorization: Bearer internal-local-token' \
  -H 'Content-Type: application/json' \
  -d '{
    "operator":"qa_local"
  }'
```

预期返回：

- `scanned_pool_count`
- `created_batch_count`
- `total_success_count`
- `total_skipped_count`
- `total_failed_count`
- `batch_ids`

再执行一次，预期同一天不会重复给同一个 `member + pool + day` 发送。

打开 `/admin/automation-conversion/programs/<program_id>/flow-design?section=sop`，确认最近 batch 区域能看到：

- pool
- day
- scheduled_for
- status
- total / success / skipped / failed

## 11. 验证重点阶段 OpenClaw 批任务

创建批任务：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches \
  -H 'Content-Type: application/json' \
  -d '{
    "operator":"qa_local"
  }'
```

查看批任务详情：

```bash
curl http://127.0.0.1:5000/api/admin/automation-conversion/focus-send-batches/<batch_id>
```

后台 runner 推进到期 item：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/automation-conversion/focus-send-batches/run-due \
  -H 'Authorization: Bearer internal-local-token'
```

预期：

- 每次 runner 最多推进到期 item，不在 HTTP 请求里 sleep
- `next_run_at` 按 20 秒向后推进
- item 失败或 cooldown 只影响当前 item，不会卡死整批

## 12. 验证消息活跃同步

先保证环境变量已配置：

- `MESSAGE_ACTIVITY_DB_HOST`
- `MESSAGE_ACTIVITY_DB_PORT`
- `MESSAGE_ACTIVITY_DB_NAME`
- `MESSAGE_ACTIVITY_DB_USER`
- `MESSAGE_ACTIVITY_DB_PASS`

首页直接点一次 `立即刷新一次`。浏览器页面使用 program-scoped 入口：

```text
POST /admin/automation-conversion/programs/<program_id>/overview/signup-tag/apply
POST /admin/automation-conversion/programs/<program_id>/overview/message-activity-sync/run
```

脚本或服务端巡检直接调 internal-token 接口：

```bash
curl -X POST http://127.0.0.1:5000/api/admin/automation-conversion/message-activity-sync/run \
  -H 'Authorization: Bearer internal-local-token' \
  -H 'Content-Type: application/json' \
  -d '{"trigger_source":"manual","operator":"qa_local"}'
```

预期：

- 首页和设置页都能看到最近一次同步摘要
- 只更新已有 `automation_member`
- 不会新增成员入池

## 13. 验证默认渠道二维码

在 `/admin/automation-conversion/programs/<program_id>/flow-design`：

- 配置 `欢迎语`
- 打开 `免验证直接添加好友`
- 保存后重新生成默认二维码

预期：

- 保存后再次进入能读回
- `welcome_message / auto_accept_friend` 会随默认二维码一起下发给 provider
- provider 不支持欢迎语时会明确显示 `unsupported`

## 14. 验证问卷提交外发 webhook

按第 6 步或第 7 步提交问卷后，检查本地 mock webhook 是否收到：

- `mobile`
- `userid`
- `unionid`

其中 `userid` 取 `questionnaire_submissions.follow_user_userid`。

## 15. 验证人工确认成交退出营销

```bash
curl -X POST http://127.0.0.1:5000/api/sidebar/marketing-status/mark-enrolled \
  -H 'Content-Type: application/json' \
  -d '{"external_userid":"wm_demo_focus","owner_userid":"sales_demo_02","operator":"qa_local"}'
```

再预览或查侧边栏状态，确认：

- `stage_key = converted/enrolled`
- `eligible_for_conversion = false`
