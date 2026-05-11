# 排错速查（Claude Code × CRM）

按现象查处理方案。

---

## 现象 1 · `propose_campaign` 返回 allocated=0

**原因**：所有 segment 命中的 member_id 集合为空，或者全部命中的人都因为别的 segment 已经先抢走了（更高 priority）。

**排查**：
1. 单独 `preview_segment_members(segment_code=...)` 看每个 segment 的 sample 是否非空
2. 看返回里 `allocation.skipped_collisions` —— 如果非 0，说明被高优先级的抢走了
3. 检查 segment SQL 是否真的返回 member_id（必填列）

---

## 现象 2 · `propose_segment` 报 `forbidden_tables`

**原因**：你的 SQL 引用了沙箱白名单之外的表。

**白名单**（详见 `domains/segments/sql_sandbox.py: ALLOWED_TABLES`）：
- automation_member
- automation_member_interaction_stats
- automation_member_audience_entry
- automation_touch_delivery_log
- automation_ai_push_log
- automation_reply_monitor_queue
- automation_focus_send_batch
- automation_focus_send_batch_item
- user_ops_pool_current
- user_ops_send_records
- contact_tags
- automation_value_segment_current
- marketing_value_segment_current
- automation_member_segment_assignment

**对策**：用上面的表重写 SQL；如果确实需要新的表，找运营/工程师在白名单里加。

---

## 现象 3 · `start_campaign` 报 `approval_token rejected:expired`

**原因**：token 5 分钟过期了。

**对策**：让运营到 CRM 后台对应 Campaign 详情页**重新点"签发 token"按钮**，拿到新的就立刻调 `start_campaign`。

---

## 现象 4 · 节奏跑了几步后突然不动了

**可能原因**：
1. Campaign 被人手动 paused（看 `get_campaign(...).campaign.run_status`）
2. 全部 member 的 `next_due_at` 还没到 — 等到 due 时间
3. Cron 没跑（运营/运维问题）— 让运营检查 `scripts/run_campaign_scheduler.py` 的 cron

---

## 现象 5 · 多个 Campaign 在跑，同一个用户被反复打扰

**这不应该发生**。跨 Campaign 的反复骚扰由"全局每周每人 ≤ 3 次"频次预算兜底。

**排查**：
1. 在 CRM 后台输用户的 external_contact_id 查最近 7 天 outbound 次数
2. 调 `query_member_interaction_stats` 看 `outbound_count_7d`
3. 如果真超了 3 次，说明频次预算被绕过了 — **报 bug**，不要自己处理

---

## 现象 6 · 同一个用户在多个 segment 下都出现

**这是正常现象**。一个用户可以同时属于多个 segment（例如同时是"活跃-重点"和"职场人"）。

**关键**：在**同一个 Campaign 内**，UNIQUE(campaign_id, member_id) 保证只出现一次。
**跨 Campaign**：同一个用户可以同时在多个 Campaign 里，但频次预算会兜底。

不要为了"避免多分层"而把 segment 设计得过分细。**让重叠存在，让 priority 决定**。

---

## 现象 7 · 我想撤回已发的消息

**做不到**。已经发出去的消息无法撤回（这是企业微信平台限制）。

**能做的**：
1. `pause_campaign` — 停止后续步骤
2. 给已发的用户单独发一条澄清/道歉（`propose_single_broadcast`）

---

## 现象 8 · 话术工单返回 `requires_manual_copy=true`

**含义**：话术 AI 端返回失败或解析失败，系统给了你一个 fallback 文案。

**对策**：
1. 看 `error` 字段：`fallback:variants_parse_failed` — 话术 AI 返回了但格式不对（可能是 prompt 的 output_schema 有问题）；`no_agent_config_for_scenario` — 这个 scenario 还没配 agent
2. 把 fallback 文案放进 step.content_text 让运营在 CRM 上手动改
3. 或者让运营在 admin 配 agent_config 后重试

---

## 现象 9 · 我想看某次发送到底发给了谁

**用 trace_id 查**：
1. 拿到该 Campaign 的 trace_id（`get_campaign(...).campaign.trace_id`）
2. CRM 后台 `/admin/cloud-orchestrator/observability` 输 trace_id
3. 或者你这边直接调 `query_recent_touch_outcomes(trace_id="...")`

---

## 紧急情况 · 误启动了一个 Campaign

1. **立刻** `pause_campaign(campaign_id=...)` — 停止后续节奏（已发的回不来）
2. 通知运营到 CRM 后台 `reject_campaign` 永久禁用
3. 用 `query_recent_touch_outcomes(campaign_id=...)` 看实际触达了多少人，给运营做善后
