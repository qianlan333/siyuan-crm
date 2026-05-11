# MCP 工具一览（给 Claude Code 阅读）

CRM 暴露 21 个工具，分四组。每个工具都标了**副作用等级**，决定它能否在没有人工介入下直接调用。

| 等级 | 含义 | Claude Code 行为 |
|---|---|---|
| **read** | 只读，不写库 | 任何时候直接调，不需要确认 |
| **draft** | 写草稿表（segments draft / cloud_broadcast_plans draft / campaign draft），不发消息、不动生产数据 | 直接调，但调完要告诉运营创建了什么 |
| **async_write** | 创建工单等异步任务（如让话术 AI 写文案），不发消息 | 直接调 |
| **write** | **真发消息 / 改生产状态** | **必须先有 CRM 后台签发的 `approval_token`**，否则会被拒 |

---

## 1️⃣ Segments（命名分层）— 这是新概念，先看这组

CRM 自带 9 个系统默认分层（池子 / 行为画像 / 沉默 30 天等），你可以直接调 `list_segments` 看到。
不够用就用 `propose_segment` 写一段 SELECT SQL 创建新的，但得满足沙箱规则（见 [rules.md](./rules.md) §3）。

### `list_segments` (read)
列出已注册的分层。

```
{
  "status": "active",           // active / draft / archived，默认 active
  "source_type": "",             // system_default / ai_generated（不填全要）
  "keyword": "",                 // 模糊匹配 code/name/description
  "limit": 200
}
```

返回数组，每条含：`segment_code`, `display_name`, `cached_headcount`, `usage_count`, `source_type`, ...

### `get_segment` (read)
拿单个分层详情，含 SQL、缓存样本。
```
{ "segment_code": "silent_30d_no_inbound" }
```

### `validate_segment_sql` (read)
**写代码前先调这个**，确保 SQL 通过沙箱再 propose。
```
{ "sql_query": "SELECT id AS member_id, external_contact_id FROM automation_member WHERE ..." }
```
返回 `{ "ok": true/false, "reason": "..." }`。

### `preview_segment_members` (read)
拿前 N 个成员看看是不是你想要的（`propose_segment` 之后或之前都可调）。
```
{ "segment_code": "silent_30d_no_inbound", "limit": 50 }
```

### `propose_segment` (draft)
创建新分层。**SQL 必须返回 `member_id` 列**，沙箱会替你强制 LIMIT 1万，禁止 DROP/UPDATE/DELETE 等。
```
{
  "segment_code": "silent_recent_focus",
  "display_name": "近 14 天沉默-重点",
  "description": "活跃-重点 + 14 天内有 outbound 但 0 inbound",
  "sql_query": "SELECT m.id AS member_id, m.external_contact_id FROM automation_member m JOIN automation_member_interaction_stats s ON s.member_id = m.id WHERE m.current_pool='active_focus' AND s.outbound_count_7d>0 AND (s.last_inbound_at='' OR s.last_inbound_at < datetime('now','-14 days'))",
  "tags": ["silent","focus"],
  "activate": true
}
```

### `update_segment` (draft) / `archive_segment` (draft)
更新或归档（不删，被引用的分层只能归档）。

---

## 2️⃣ 互动数据查询 — 选人和复盘的眼睛

### `query_segment_dimensions` (read)
摸维度。返回当前 CRM 里实际存在的池子 / 画像 / 行为分层枚举值。**写 SQL 前先调它，确保枚举值是对的**。

### `search_segment_members` (read)
**这是个临时筛选工具，不创建分层**。如果你只想看一眼"在某些条件下有多少人"，调它。如果要保存这个口径，调 `propose_segment`。
```
{
  "pool_keys": ["active_focus","inactive_focus"],
  "profile_segment_keys": ["职场人"],
  "behavior_tier_keys": ["msg_2_to_9"],
  "page": 1, "page_size": 50
}
```

### `query_member_interaction_stats` (read)
对一批人拉互动聚合（30 天触达 / 回复率 / 沉默天数 / cooldown）。
```
{ "external_contact_ids": ["wm_xxx",...], "lookback_days": 30 }
```

### `query_recent_touch_outcomes` (read)
群发后效果。可按 plan_id / trace_id / send_record_id 任一查。
```
{ "trace_id": "tr-xxx", "lookback_hours": 72 }
```

### `scan_silent_for_revival` (read)
扫沉默池候选。
```
{ "silent_days_min": 14, "silent_days_max": 60, "pool_keys": ["active_focus","inactive_focus"], "limit": 100 }
```

---

## 3️⃣ Campaign（多分层多步骤运营计划）— 重点工具

### `propose_campaign` (draft) — **最常用的入口**
一次性提交完整 Campaign。系统会自动按 priority 互斥分配候选成员。

```json
{
  "display_name": "5月限时优惠激活",
  "intent": "覆盖付费意向客户，5月13日启动",
  "anchor_mode": "campaign_start_date",
  "anchor_date": "2026-05-13",
  "owner_userid": "user_001",
  "segments": [
    {
      "segment_code": "pool_active_focus",
      "priority": 999,
      "label": "活跃-重点",
      "steps": [
        {"step_index": 0, "day_offset": 0, "send_time": "09:00",
         "content_text": "开抢通知：限时 7 折，仅本周。"},
        {"step_index": 1, "day_offset": 2, "send_time": "10:00",
         "content_text": "中段提醒：还有 5 天，名额已用 60%。"},
        {"step_index": 2, "day_offset": 4, "send_time": "18:00",
         "content_text": "倒计时：今晚截止。"}
      ]
    },
    {
      "segment_code": "pool_inactive_focus",
      "priority": 500,
      "label": "不活跃-重点",
      "steps": [
        {"step_index": 0, "day_offset": 0, "content_text": "..."},
        {"step_index": 1, "day_offset": 3, "content_text": "..."}
      ]
    }
  ],
  "auto_allocate": true
}
```

返回 `overview`，含分配结果（`allocation.allocated`、`allocation.skipped_collisions` 看互斥效果）。

**Anchor 两种模式**：
- `campaign_start_date`：所有人从同一个启动日算 Day 0（限时活动用）
- `member_joined_at`：每个人从加入 Campaign 那天算 Day 0（持续运营用）

### `submit_campaign_for_review` (draft)
方案打磨好后切到待审状态，CRM 后台开始可见。

### `get_campaign` (read) / `list_campaigns` (read)
查 Campaign 详情 / 列表（按 review_status / run_status 过滤）。

### `start_campaign` (write, **需 token**)
**调用方需要带 approval_token**。token 由 CRM 后台 `/api/admin/cloud-orchestrator/campaigns/<code>/approve` 端点签发。**不要尝试自己 approve，那会被运营/审计标记为绕过。**

### `pause_campaign` (draft) / `resume_campaign` (draft)
暂停 / 恢复。已发出去的不会撤回，但停止后续节奏。

---

## 4️⃣ 话术工单（让话术 AI 写文案）

### `request_copy_workorder` (async_write)
给话术 AI 发一个工单，**它有完整 QA 库和打磨好的话术经验，你不要在 prompt 里写最终话术，让它写**。

```json
{
  "scenario_code": "bulk_activation",  // bulk_activation / silent_wake / journey_step
  "intent": "激活沉默用户，介绍 X 新功能",
  "audience_summary": {
    "candidate_count": 124,
    "pool_distribution": {"active_focus": 124},
    "profile_segment_distribution": {"职场人": 78, "创业者": 46}
  },
  "target_segments": ["职场人", "创业者"],
  "sample_recipients": [{"profile_segment_key": "职场人", ...}, ...],
  "plan_id": ""   // 可选，关联到一个 Campaign
}
```

返回 `variants`：每个 profile_segment_key 一条话术。把这些 variants 填进 `propose_campaign` 的对应 step.content_text。

---

## 5️⃣ 兼容旧的"单次群发"

### `propose_single_broadcast` (旧 `draft_broadcast_plan`，draft)
一次性广播（不分层、单步）。建议优先用 `propose_campaign`，单次广播本质是 1 步 Campaign。

### `commit_broadcast_plan` (write, **需 token**)
对应 `propose_single_broadcast` 的真发入口。

### `simulate_broadcast` (read)
对 plan 跑 dry-run。

---

## 6️⃣ 审计 / 评估辅助

### `evaluate_transition` (read)
节奏中如果有 `condition_kind=ai_decision`，调这个回写决策。
```
{ "transition_id": 42, "matched": true, "reason": "用户最近回复频率回升" }
```

---

## 一句话用法对照

| 你想做的事 | 调哪个工具 |
|---|---|
| 看 CRM 现有分层有哪些 | `list_segments` |
| 临时看符合条件的人有多少 | `search_segment_members` |
| 写一个新口径并保存 | `propose_segment` |
| 看一群人最近互动情况 | `query_member_interaction_stats` |
| 让话术 AI 写文案 | `request_copy_workorder` |
| 给一群人设计多步运营计划 | `propose_campaign` |
| 提交计划到 CRM 等运营审 | `submit_campaign_for_review` |
| 看效果 | `query_recent_touch_outcomes` |
| 出错了排查 | 在 CRM `/admin/cloud-orchestrator/observability` 输 trace_id |
