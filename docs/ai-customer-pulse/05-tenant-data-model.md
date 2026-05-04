# AI Customer Pulse 租户数据模型

更新时间：2026-04-11
适用范围：`ai_customer_pulse` feature flag 打开后的 Customer Pulse 读写链路。

## 一句话结论

Customer Pulse 现已从“tenant-tagged 表”升级为“tenant-scoped 读写模型”：

- 所有 Customer Pulse 主表都显式带 `tenant_key`
- repo/service/executor 入口显式要求 tenant context 或 `tenant_key`
- 详情、列表、evidence、action executor、timeline 回写均按 tenant 过滤
- 关联写入不再只靠约定，改为同租户显式校验
- 卡片展示读链不再 join 全局客户表，改为使用 tenant-scoped 卡片上的冗余字段

这轮的目标不是全仓库 tenant 化，而是把 Customer Pulse 做成一个可外放的 tenant-aware island。

## 表级模型

### 1. `customer_pulse_signal_events`

- tenant 字段：`tenant_key`
- 写入来源：rule engine / recompute job / event-trigger refresh
- 主职责：保存可解释信号明细
- 当前约束：
  - `signal_key` 已按 `tenant_key` 做 scoped key
  - `get/list/upsert/resolve` 全部显式走 tenant
- 关键索引：
  - `idx_customer_pulse_signal_events_tenant_external_status`
  - `idx_customer_pulse_signal_events_tenant_type`

### 2. `customer_pulse_snapshots`

- tenant 字段：`tenant_key`
- 写入来源：refresh / recompute 产出的快照层
- 主职责：保存某次聚合后的优先级、风险、机会、候选动作
- 当前约束：
  - `create/get/list/get_latest` 全部要求 tenant
  - detail 页面按 `tenant_key + external_userid` 读取最新快照
- 关键索引：
  - `idx_customer_pulse_snapshots_tenant_external`

### 3. `customer_pulse_cards`

- tenant 字段：`tenant_key`
- 写入来源：snapshot -> card 投影
- 主职责：保存收件箱展示和执行入口需要的稳定卡片数据
- 本轮新增冗余字段：
  - `customer_name`
  - `mobile`
  - `owner_display_name`
  - `marketing_main_stage`
  - `marketing_sub_stage`
  - `value_segment`
- 当前约束：
  - `get/get_by_key/list/update/upsert/count` 全部要求 tenant
  - `snapshot_id` 更新或写入前，必须先校验该 snapshot 属于同一 tenant
  - 卡片详情读取已移除对以下全局表的 join：
    - `contacts`
    - `external_contact_bindings`
    - `owner_role_map`
    - `customer_marketing_state_current`
    - `customer_value_segment_current`
- 原因：
  - 这些表仍是单租户/全局事实表
  - 即便卡片本身已按 tenant 过滤，join 全局表仍可能造成展示级越权泄漏
- 关键索引：
  - `idx_customer_pulse_cards_tenant_external`
  - `idx_customer_pulse_cards_tenant_status_score`

### 4. `customer_pulse_feedback_logs`

- tenant 字段：`tenant_key`
- 主职责：记录卡片级人工反馈
- 当前约束：
  - 插入前校验 `card_id` 属于同一 tenant
  - 返回查询按 `tenant_key + id`
- 关键索引：
  - `idx_customer_pulse_feedback_logs_tenant_card`

### 5. `customer_pulse_execution_logs`

- tenant 字段：`tenant_key`
- 主职责：记录 action executor 的请求、结果、幂等和撤销状态
- 当前约束：
  - `insert/get/get_latest/update/get_latest_by_idempotency` 全部要求 tenant
  - 插入前校验 `card_id` 属于同一 tenant
  - 如携带 `activity_log_id`，也必须验证同租户
  - update 已从“按全局 id 更新”改为“`tenant_key + id` 更新”
- 关键索引：
  - `idx_customer_pulse_execution_logs_tenant_card`
  - `idx_customer_pulse_execution_logs_tenant_idempotency`

### 6. `customer_pulse_activity_logs`

- tenant 字段：`tenant_key`
- 主职责：记录执行成功后的本地写回活动，用于 timeline/activity 回流
- 当前约束：
  - `insert/get/update/list` 全部要求 tenant
  - 插入前校验 `card_id` 属于同一 tenant
  - timeline 聚合读取已改为 `tenant_key + external_userid`
  - `has_customer_timeline_scope(...)` 对 pulse activity 的存在性判断也已加 tenant 条件
- 关键索引：
  - `idx_customer_pulse_activity_logs_tenant_external_userid`
  - `idx_customer_pulse_activity_logs_tenant_card`
  - `idx_customer_pulse_activity_logs_tenant_idempotency`

### 7. `customer_pulse_action_feedback`

- tenant 字段：`tenant_key`
- 主职责：记录采纳、改写后发送、忽略、误判、无帮助等学习反馈
- 当前约束：
  - `insert/list` 全部要求 tenant
  - 插入前校验：
    - `card_id` 属于同一 tenant
    - `execution_log_id` 如存在，也必须属于同一 tenant
- 关键索引：
  - `idx_customer_pulse_action_feedback_tenant_card`
  - `idx_customer_pulse_action_feedback_tenant_execution`
  - `idx_customer_pulse_action_feedback_tenant_type`

### 8. `customer_pulse_metric_events`

- tenant 字段：`tenant_key`
- 主职责：记录曝光、点击、确认、写回成功/失败等埋点
- 当前约束：
  - `insert/count` 全部要求 tenant
  - 插入前校验：
    - `card_id` 如存在，必须属于同一 tenant
    - `execution_log_id` 如存在，必须属于同一 tenant
- 关键索引：
  - `idx_customer_pulse_metric_events_tenant_type`
  - `idx_customer_pulse_metric_events_tenant_card`
  - `idx_customer_pulse_metric_events_tenant_execution`

### 9. `user_ops_deferred_jobs`

- tenant 字段：`tenant_key`
- 当前使用：`customer_pulse_recompute`
- 当前约束：
  - enqueue / get / list_due / mark_running / finish 均显式 tenant-scoped
  - legacy internal mode 仍写默认 tenant：`aicrm`

## 继承关系与校验规则

### tenant 来源

1. request-scoped mode：
   - 从 request context 解析 `tenant_key`
   - 无 tenant、非法 tenant、冲突 tenant 直接拒绝
2. legacy internal mode：
   - 显式写入默认 tenant：`aicrm`
   - 日志与 payload 中可区分 `legacy_internal`

### 实体继承链

1. `signal_event`
   - tenant 直接来自当前 refresh/recompute 上下文
2. `pulse_snapshot`
   - tenant 直接来自当前 refresh/recompute 上下文
3. `action_card`
   - tenant 直接来自当前 refresh/recompute 上下文
   - `snapshot_id` 必须在同租户下可见
4. `execution_log`
   - 依附 `card_id`
   - `card_id` 必须在同租户下可见
5. `activity_log`
   - 依附 `card_id`
   - `card_id` 必须在同租户下可见
6. `action_feedback`
   - 依附 `card_id`
   - 可选依附 `execution_log_id`
   - 两者都必须同租户
7. `metric_event`
   - 可选依附 `card_id` / `execution_log_id`
   - 只要引用存在，就必须同租户

### 拒绝策略

- repo 层不再接受“空 tenant 然后隐式 fallback”
- 对 tenantized 表：
  - 无 tenant：直接抛错
  - tenant 不匹配：返回空结果或拒绝更新
  - 关联 id 不匹配：直接抛错，阻止写入

## 本轮最小迁移方案

### 已实施

1. 保留既有 Customer Pulse 表上的 `tenant_key`
2. 将卡片展示必需字段下沉到 `customer_pulse_cards`
3. 所有 id-based getter / update 改为 tenant-scoped
4. 所有 feedback / execution / activity / metric 插入增加同租户校验
5. timeline 中 Customer Pulse 回写活动改成 tenant-scoped 读取
6. 为 tenant 过滤后的列表与详情查询补 tenant-leading 索引

### 为什么不直接改上游客户主表

当前以下上游事实表仍是全局单租户模型：

- `contacts`
- `external_contact_bindings`
- `customer_marketing_state_current`
- `customer_value_segment_current`
- `archived_messages`
- `contact_tags`

如果这一轮直接把它们 tenant 化，会扩大爆炸半径到客户中心、timeline、任务、营销自动化、消息归档和后台页面主流程，不符合“先让 Customer Pulse 可外放”的目标。

所以本轮采用更小的路径：

- 不大改上游表
- 先把 Customer Pulse 对外读链从全局表 join 中摘出来
- 用 tenant-scoped card/snapshot/log 表承接对外展示和写回审计

## 索引策略

本轮统一把高频查询改成 tenant-leading 索引，避免加了 tenant filter 之后性能退化。

### 列表与详情

- cards：
  - `tenant_key, external_userid, updated_at DESC, id DESC`
  - `tenant_key, card_status, priority_score DESC, due_at, updated_at DESC, id DESC`
- snapshots：
  - `tenant_key, external_userid, created_at DESC, id DESC`
- signals：
  - `tenant_key, external_userid, signal_status, updated_at DESC, id DESC`
  - `tenant_key, signal_type, updated_at DESC, id DESC`

### 执行与写回

- execution logs：
  - `tenant_key, card_id, created_at DESC, id DESC`
  - `tenant_key, idempotency_key, created_at DESC, id DESC`
- activity logs：
  - `tenant_key, external_userid, created_at DESC, id DESC`
  - `tenant_key, card_id, created_at DESC, id DESC`
  - `tenant_key, idempotency_key, created_at DESC, id DESC`

### 反馈与埋点

- action feedback：
  - `tenant_key, card_id, created_at DESC, id DESC`
  - `tenant_key, execution_log_id, created_at DESC, id DESC`
  - `tenant_key, feedback_type, created_at DESC, id DESC`
- metric events：
  - `tenant_key, event_type, created_at DESC, id DESC`
  - `tenant_key, card_id, created_at DESC, id DESC`
  - `tenant_key, execution_log_id, created_at DESC, id DESC`

## 已知边界

### 已解决

- 跨租户读 action card：已阻断
- 跨租户读 evidence / snapshot / execution log：已阻断
- 跨租户执行 action 并写日志：已阻断
- timeline 中 pulse activity 跨租户泄漏：已阻断
- 因全局 join 导致的卡片展示信息泄漏：已阻断

### 仍待后续治理

- 上游客户、消息、标签、营销状态表仍不是 request-scoped tenant 数据模型
- `admin_operation_logs` 仍没有结构化 `tenant_key` 字段，目前 tenant 信息在 JSON 审计载荷中
- legacy internal mode 继续使用默认 tenant `aicrm`，适合内部兼容，不适合作为 SaaS 外放长期形态

## 推荐迁移顺序

1. 先上线当前 Customer Pulse tenant-scoped island
2. 再把审计日志表补成结构化 tenant 维度
3. 最后再评估客户中心 / timeline / archive 上游事实表的真正 tenant 化

这能在最小爆炸半径下，先杜绝 Customer Pulse 的跨租户读写风险。
