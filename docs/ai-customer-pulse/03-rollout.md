# AI 客户推进收件箱上线说明

## 开关与配置

### 必开 Feature Flag

- `ai_customer_pulse=true`

### 最小配置项

- `CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD`
  - 默认 `70`
  - 含义：`priority_score` 达到阈值后标记为高优先级
- `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS`
  - 默认 `true`
  - 含义：是否展示因 AI 低置信度降级出来的建议卡
- `CUSTOMER_PULSE_ALLOWED_ACTION_TYPES`
  - 默认允许全部：
  - `generate_reply_draft,create_followup_task,update_followup_segment,update_tags,set_followup_reminder`
- `CUSTOMER_PULSE_TENANT_MODE`
  - 默认 `legacy_internal`
  - 可选：`legacy_internal`、`request_scoped`
  - 含义：兼容当前单租户后台管理台，或切换到请求级租户隔离模式
- `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`
  - 默认空
  - 含义：`request_scoped` 模式下为必填；按 `tenant_key` 定义 `owner_userids`、`member_userids`、`viewer_roles`、`operator_roles`、`internal_roles`
- `CUSTOMER_PULSE_FLAG_POLICY_JSON`
  - 默认空
  - 含义：在 `ai_customer_pulse=true` 基础上继续按 tenant / role / userid 做灰度；不配置时沿用全局开关

### 推荐灰度策略示例

```json
{
  "default_enabled": false,
  "tenants": {
    "tenant-acme": {
      "enabled": true,
      "roles": {
        "sales": true,
        "ops": true,
        "admin": true
      }
    }
  }
}
```

### 推荐租户策略示例

```json
{
  "tenant-acme": {
    "owner_userids": ["owner-a", "owner-b"],
    "member_userids": ["owner-a", "owner-b", "ops-1"],
    "viewer_roles": ["sales", "delivery", "ops", "admin"],
    "operator_roles": ["sales", "delivery", "ops", "admin"],
    "internal_roles": ["ops", "admin"],
    "notes": "Acme 外放租户"
  }
}
```

### 推荐本地设置命令

```bash
python scripts/seed_customer_pulse_demo.py --init-db --write-settings
```

## 租户与权限模式

### `legacy_internal`

- 面向当前单租户后台管理台。
- Customer Pulse 默认 tenant 为 `aicrm`。
- 适合内部运营或历史环境，不要求请求级 tenant header。

### `request_scoped`

- 面向对外 SaaS 租户接入。
- Customer Pulse 所有读写链路都要求显式 tenant context 和 actor context。
- 请求优先从以下位置解析：
  - tenant：`X-Tenant-Key`、`X-Customer-Pulse-Tenant`、`tenant_key`
  - actor：`X-Admin-Userid`、`X-Admin-Role`、`admin_userid/admin_role`
- 默认拒绝：
  - 无 tenant
  - tenant policy 缺失
  - 无 actor 或无 role
  - actor 不在 tenant member allowlist
  - owner scope 不在当前 tenant 策略内
  - 角色不在 `viewer_roles` / `operator_roles` / `internal_roles`

### 页面与 API 行为

- `/admin/customer-pulse` 与客户详情页 widget 在服务端注入 `mode/tenant_key/actor_userid/actor_role`。
- 前端 `fetch` 请求自动回传 `X-Tenant-Key`、`X-Admin-Userid`、`X-Admin-Role`。
- HTML 表单动作同时透传 `tenant_key`、`admin_userid`、`admin_role`。
- internal API 除 bearer token 外，在 `request_scoped` 模式下还要求 actor role 命中 `internal_roles`。

## 依赖与前置检查

- 会话记录来源：`archived_messages`
- 客户与负责人关系：`contacts`、`external_contact_bindings`、`wecom_external_contact_follow_users`
- 阶段/分层：`customer_marketing_state_current`、`customer_value_segment_current`
- 回复草稿落盘：`outbound_tasks`
- AI 推荐链路：
  - 优先复用现有 AI gateway / provider 封装
  - 不可用时必须允许 rule-based fallback
- 管理后台配置中心：
  - `/admin/config/app-settings`
- 权限与审计：
  - 复用 `validate_admin_console_action_token()`
  - 复用 `admin_operation_logs`
  - 复用 `user_ops_deferred_jobs`

## 数据与监控

### 核心表

- `customer_pulse_signal_events`
- `customer_pulse_snapshots`
- `customer_pulse_cards`
- `customer_pulse_feedback_logs`
- `customer_pulse_execution_logs`
- `customer_pulse_activity_logs`
- `customer_pulse_action_feedback`
- `customer_pulse_metric_events`
- `user_ops_deferred_jobs`

### 审计点

- 后台访问拒绝、刷新、执行、反馈、撤销、内部重算统一写 `admin_operation_logs`
- `customer_pulse_execution_logs` 记录 tenant context、actor、resource type/id、动作输入/输出摘要、结果、错误、幂等键、撤销窗口、rollback payload
- `customer_pulse_activity_logs` 记录回写到 timeline / activity / follow-up 的动作轨迹
- `customer_pulse_feedback_logs` 与 `customer_pulse_action_feedback` 分开承载操作反馈和学习反馈
- evidence 查看成功与拒绝都带 `tenant_context + actor + resource` 审计痕迹；拒绝场景额外记录安全计数

### 关键埋点

- `card_exposed`
- `card_clicked`
- `evidence_viewed`
- `draft_confirmed`
- `followup_task_created`
- `followup_segment_updated`
- `card_ignored`
- `ai_recommendation_completed`
- `ai_error`
- `action_executed`
- `access_denied`
- `guardrail_blocked`
- `writeback_success`
- `writeback_failed`

### 关键反馈类型

- `adopted`
- `edited_then_sent`
- `ignored`
- `misjudged`
- `unhelpful`

### 执行审计标签

- `ai_suggested`
- `human_confirmed`
- `human_edited`

### 建议监控口径

- 卡片曝光量：`event_type='card_exposed'`
- 卡片点击率：`card_clicked / card_exposed`
- 草稿确认率：`draft_confirmed / card_clicked`
- 任务创建率：`followup_task_created / action_executed`
- 阶段更新率：`followup_segment_updated / action_executed`
- 忽略率：`card_ignored / card_exposed`
- AI 错误率：`ai_error / ai_recommendation_completed`
- 写回成功率：`writeback_success / (writeback_success + writeback_failed)`
- 越权拒绝次数：`event_type='unauthorized_denied'`
- 跨租户拒绝次数：`event_type='cross_tenant_denied'`

### 最小统计接口

- 后台 API：`GET /api/admin/customer-pulse/stats?days=7`
- internal API：`GET /api/internal/customer-pulse/stats?days=7`
- 返回内容：
  - `feature_gate`
  - `dependencies`
  - `counts`
  - `rates`
  - `summary_cards`

### 建议排查 SQL

```sql
SELECT event_type, COUNT(*) AS total_count
FROM customer_pulse_metric_events
GROUP BY event_type
ORDER BY event_type;
```

```sql
SELECT feedback_type, COUNT(*) AS total_count
FROM customer_pulse_action_feedback
GROUP BY feedback_type
ORDER BY feedback_type;
```

```sql
SELECT tenant_key, action_type, execution_status, COUNT(*) AS total_count
FROM customer_pulse_execution_logs
GROUP BY tenant_key, action_type, execution_status
ORDER BY tenant_key, action_type, execution_status;
```

## 回滚方案

### 快速止损

1. 在系统设置中将 `ai_customer_pulse=false`
2. 如需保留页面但收紧动作，将 `CUSTOMER_PULSE_ALLOWED_ACTION_TYPES` 改为仅 `generate_reply_draft`
3. 如需减少争议卡片，将 `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS=false`
4. 如需从外放模式退回内部模式，将 `CUSTOMER_PULSE_TENANT_MODE=legacy_internal`

### 数据回滚说明

- 本期新增表均为 append-only 日志表，不要求数据回滚才能关闭功能
- 已生成草稿仍留在 `outbound_tasks`，不会自动外发
- 已执行动作的客户/阶段/标签变更，按业务需要用现有撤销能力或人工修正
- `request_scoped` 下写入的数据都带 `tenant_key`，必要时可按租户筛查或归档

## 验收与演示

### 本地 Demo 数据

脚本：

```bash
python scripts/seed_customer_pulse_demo.py --init-db --write-settings
```

双 tenant 验证：

```bash
python scripts/seed_customer_pulse_demo.py --init-db --write-settings --dual-tenant
```

将生成 3 类典型客户：

- `wm_pulse_demo_reply`
  - 最近追问价格，预期出现“生成回复草稿”
- `wm_pulse_demo_stalled`
  - 阶段停滞，预期出现“设置提醒”或“创建跟进任务”
- `wm_pulse_demo_risk`
  - 负向情绪/投诉，预期出现“人工介入类动作”

双 tenant 模式会额外生成：

- `tenant-alpha`
  - `wm_pulse_demo_tenant_a_reply`
  - `wm_pulse_demo_tenant_a_stalled`
- `tenant-beta`
  - `wm_pulse_demo_tenant_b_risk`
  - `wm_pulse_demo_tenant_b_reminder`

### 建议验收路径

1. 打开 `/admin/customer-pulse`
2. 确认列表按 `priority_score` 排序
3. 点击卡片查看证据、为什么现在、建议动作
4. 执行草稿/任务/阶段/提醒动作，确认只生成草稿不自动发送
5. 在客户详情页确认同卡片数据、活动回写和反馈按钮可用

### 推荐回归命令

```bash
make lint
make typecheck
make build
make test-customer-pulse
make check
./.venv310/bin/python -m pytest -q tests/test_admin_customer_profile_console.py
./.venv310/bin/python -m pytest -q -k e2e
./.venv310/bin/python -m pytest -q
```

## 已知限制

- `edited_then_sent` 当前在 MVP 中表示“改写后确认执行”，对回复草稿场景是“改写后保存草稿”，不是最终外发回执
- 指标事件当前先落日志表，未接外部 BI/时序系统
- 卡片曝光按页面/API 返回记录，属于服务端埋点口径，不是前端 viewport 精确曝光
- demo seed 主要面向本地 / sqlite 场景
- `request_scoped` 依赖调用方稳定注入 tenant/actor 头；如果外围网关没有传递这些上下文，Customer Pulse 会直接拒绝访问
