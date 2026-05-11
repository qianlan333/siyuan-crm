# 必守规则（Claude Code 在调用 CRM 工具时必须遵守的 8 条）

下面这些是**系统级 / 业务级红线**，违反了会被审计、被运营投诉，或者直接被工具拒绝。请把这一节当成 hard constraint，不要尝试绕过。

---

## 规则 1 · 真发只能在 CRM 后台启动

任何会真正发消息给用户的操作（`commit_broadcast_plan`、`start_campaign`），调用时**必须带 `approval_token`**。这个 token 只能由 CRM 后台的 `/api/admin/cloud-orchestrator/.../approve` 端点签发，由运营人在 UI 上点"启动"按钮触发。

**Claude Code 不能尝试自己给自己签 token**。这一条是审计红线。

---

## 规则 2 · 跨分层互斥是数据库层保证，但你也要给合理的 priority

`UNIQUE(campaign_id, member_id)` 在数据库层强制保证一个用户在同一个 Campaign 内只占一条节奏。但**谁抢到这个用户**取决于 `campaign_segments.priority`。

写 `propose_campaign` 时，给每个 segment 一个明确的 priority 值（数字越大越优先）：
- 高价值 / 强信号的人群 → 高 priority（800–999）
- 兜底 / 宽口径的人群 → 低 priority（100–500）

**默认值是 100**，多个 segment 都用默认 100 时分配顺序不稳定。**显式给值**。

---

## 规则 3 · SQL 沙箱不可绕过

`propose_segment` 时给的 SQL 必须满足：

| 约束 | 含义 |
|---|---|
| 单条 SELECT 或 WITH 开头 | 不能 ;-分隔多语句 |
| 长度 ≤ 8000 字符 | 防滥用 |
| 不含黑名单关键字 | DROP / DELETE / UPDATE / INSERT / ALTER / CREATE / TRUNCATE / ATTACH / DETACH / PRAGMA / VACUUM / REPLACE / GRANT / REVOKE / EXEC |
| 仅引用白名单表 | automation_member, automation_member_interaction_stats, automation_member_audience_entry, automation_touch_delivery_log, automation_ai_push_log, automation_reply_monitor_queue, user_ops_pool_current, user_ops_send_records, contact_tags 等（详见 sql_sandbox.py: ALLOWED_TABLES） |
| 必须返回 `member_id` 列 | 别名为 `member_id` 或返回 `id` 列（系统会自动重命名） |
| 不需要写 LIMIT | 沙箱会自动包一层 LIMIT 1万 |

**先调 `validate_segment_sql` 验证**，通过了再 `propose_segment`。

---

## 规则 4 · 频次预算永远在你前面

哪怕你给一个用户精心设计了 5 步节奏，如果该用户已经被全局/渠道频次预算限制了，**会被静默跳过**。

默认配置：
- 全局每周每人 ≤ 3 次
- AI 主动发起每周每人 ≤ 2 次
- 全局每天每人 ≤ 1 次

**所以**：
- ✅ 单个 Campaign 节奏不要密于 3 天 1 次（避免内部触发自我跳过）
- ✅ 同一个用户短期内不要被两个 Campaign 同时挂上
- ❌ 不要试图"绕过"频次预算，没办法绕过，连超管也不行

---

## 规则 5 · 不在 Claude Code 写最终话术

话术 AI 端拥有完整 QA 库 + 打磨好的话术风格。Claude Code 端写出来的话术大概率不如它。

**正确做法**：
1. Claude Code 决定"为这群什么样的人，要达成什么目的"
2. 调 `request_copy_workorder` 把这两件事告诉话术 AI 端
3. 话术 AI 端返回多变体，你把 variants 填进 `propose_campaign` 的对应 step

**不要做的**：
- 自己在 Claude Code 里 hardcode 最终话术文案
- 把 step.content_text 写得过于详细以至于运营无法在 CRM 上微调

---

## 规则 6 · 节奏不要超过 6 步

任何 Campaign 的任何一个分层，**节奏步数 ≤ 6**。超过这个数，应该切到长期 SOP 而不是临时 Campaign。

经验值：
- 限时活动：3-4 步
- 沉默激活：3 步
- 新人 onboarding：4-5 步
- 持续触达 / 关怀：放在 SOP，不放 Campaign

---

## 规则 7 · 不要"批量风暴"

单次 Campaign 候选人数：**软上限 1000，硬上限 5000**（频次预算会强制兜底但应当主动控制）。

如果你算出来候选 > 5000：
- 切分为多个独立 Campaign，间隔启动
- 或者收紧 segment SQL 条件（提高门槛）

---

## 规则 8 · trace_id 是黄金线索

每次调用 `propose_campaign` / `propose_single_broadcast` 都会生成一个 trace_id，**贯穿 CRM 端 → 话术端 → 发送端**。

- 给运营回报时**必须报上 trace_id**
- 报错排查时**先问 trace_id**
- 不要发明、伪造、重用别的 trace_id

CRM 后台 `/admin/cloud-orchestrator/observability` 是按 trace_id 查的入口。

---

## 失败处理 — 工具返回 error 时怎么做

| 错误码 | 含义 | 处理 |
|---|---|---|
| `forbidden_keyword:DROP` | SQL 含黑名单关键字 | 改写 SQL |
| `forbidden_tables:xxx` | SQL 引用了非白名单表 | 改用允许的表 |
| `sql_missing_member_id_column` | SELECT 输出没 member_id | 加 `id AS member_id` |
| `dry_run_failed:...` | SQL 跑出错（语法 / 参数） | 看 error 详情，修 SQL |
| `approval_token rejected:expired` | token 过期了 | 让运营到 CRM 后台重新签发 |
| `approval_token rejected:plan_mismatch` | token 是给别的 plan 签的 | 用对应 plan 的 token |
| `budget_exceeded:xxx` | 频次预算用完 | 告诉运营，不要绕过 |
| `do_not_disturb` | 用户在屏蔽列表 | 跳过即可，不要重试 |
| `segment not active` | 引用的分层是 draft 或 archived | 先 `update_segment(status='active')` |

---

## 一句话总结

**你是策略层，CRM 是能力层，话术 AI 是文案层。三层各司其职，谁也不要伸到别人的领地里去。**
