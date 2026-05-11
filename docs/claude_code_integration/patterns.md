# 典型方法论 — Claude Code 用 CRM 的 9 种打法

每种打法都给：
- 业务场景
- Claude Code 内部步骤
- 关键 prompt / 工具调用模板
- 容易踩的坑

---

## 打法 1 · 沉默激活（最常用）

**场景**：运营说「激活近 30 天没回复的活跃-重点用户，介绍我们刚上线的 X 功能」。

**内部步骤**：
1. `query_segment_dimensions` — 看清楚枚举
2. `list_segments` — 看 `silent_30d_no_inbound` 是不是已经存在；存在就直接用
3. 如果没合适的，`validate_segment_sql` → `propose_segment` 创建
4. `preview_segment_members` 拿 50 条样本估一下数量级
5. `query_member_interaction_stats` 查这群人画像分布 → 决定要不要分层
6. **按 profile 分层后**，每个分层调 `request_copy_workorder` 让话术 AI 写多步话术
7. 拼 segments + steps，调 `propose_campaign`
8. `submit_campaign_for_review`
9. **回报运营**："已生成 camp-xxx，N 人 K 分层，请到 CRM 后台审阅启动。"

**节奏建议**：D+0（轻量唤醒）→ D+3（具体价值点）→ D+7（最后机会）。**不要超过 4 步**，沉默用户对超过 4 步的连续打扰耐受度低。

**关键提示**：
- ✅ 用 `member_joined_at` 锚点更合适（每个人从被加入 Campaign 那天算 Day 0）
- ✅ `stop_on_reply` 设 true（系统级保证，但显式声明更安全）
- ❌ 不要自己写最终话术 — 让话术 AI 写，你只提供"目的 / 人群摘要 / 样例画像"

---

## 打法 2 · 限时活动覆盖既有用户

**场景**：「下周一 5月13日要做限时优惠，覆盖所有付费意向客户」。

**关键差异**：anchor_mode = `campaign_start_date`，所有人从同一个启动日开始算 Day 0（不管他们是去年还是上周进的池子）。

**节奏模板**：
- D+0（启动日 09:00）：开抢通知
- D+2（10:00）：中段提醒，附"已抢 N%"社会证明
- D+4（18:00）：倒计时，今晚截止

**调用要点**：
```json
{
  "anchor_mode": "campaign_start_date",
  "anchor_date": "2026-05-13",
  "segments": [...]
}
```

---

## 打法 3 · 新人接力（叠加在现有 SOP 之上）

**场景**：新人进池后系统已经有一套基础 SOP，但运营想给某个画像组（如"创业者"）额外加一份激活路径。

**关键**：用 `propose_segment` 限定到"近 7 天进池且 profile=创业者"，再 `propose_campaign` 用 `member_joined_at` 锚点跑 D+0/2/5/9 节奏。

**注意**：和现有 SOP 共享同一批人时，**频次预算会自动兜底**（一个用户 7 天 ≤ 3 次的全局规则）。所以你不用担心叠太多。

---

## 打法 4 · 多分层分流（用户被多个 segment 命中时怎么办）

**场景**：「付费意向 + 活跃-重点」和「付费意向 + 不活跃-重点」两群人想用不同话术。但有些用户既是付费意向又是活跃-重点。

**做法**：在一个 Campaign 里挂两个 segment，**用 priority 决定谁抢这些重叠用户**。
```json
"segments": [
  { "segment_code": "paid_intent_active_focus", "priority": 900, "steps": [...] },
  { "segment_code": "paid_intent_inactive_focus", "priority": 500, "steps": [...] }
]
```

**系统保证**：哪怕一个用户同时在两个分层 SQL 里，UNIQUE(campaign_id, member_id) 拒绝重复分配，最终只在 priority 高的那条节奏里。

---

## 打法 5 · 复盘 + 修改（不是新建，而是改进运行中的计划）

**场景**：「上周启动的 X Campaign 第二步回复率只有 2%，看看问题，给我改进建议。」

**步骤**：
1. `list_campaigns(run_status="active")` 找到目标 Campaign
2. `query_recent_touch_outcomes(campaign_id=...)` 拉每一步效果
3. 分析：哪一步 reply_rate 异常低
4. **不要直接改 Campaign**（运行中的不可变），而是：
   - `pause_campaign` 暂停
   - `request_copy_workorder` 让话术 AI 重写问题步骤
   - 用 `propose_campaign` 建一个改进版（新 campaign_code，复用 segments）
5. 回报运营："旧 Campaign 已暂停，新版 camp-yyy 已生成请审阅，对比新旧话术..."

---

## 打法 6 · 临时一次性广播（不是 Campaign）

**场景**：「给所有活跃-重点 1000 人发一条系统通知，1 步搞定。」

**做法**：用 `propose_single_broadcast`（旧版 draft_broadcast_plan）更轻。`propose_campaign` 1 步也可以但有点重。

---

## 打法 7 · 沉默扫描日报（cron 自动跑 / 运营手工触发）

**场景**：每天扫沉默池，自动给运营推荐"今天值得激活的人群"。

**做法**：
1. `scan_silent_for_revival(silent_days_min=14, silent_days_max=60)` 拿候选
2. 按 profile 分组，每组建 segment（如果没有），propose 一个 draft Campaign
3. **不 submit_campaign_for_review**，而是放在 draft，运营第二天上班自己浏览

**关键**：每天最多生成 N 个 draft，避免堆积。

---

## 打法 8 · "我说一句你做完整"（高自由度模式）

**场景**：运营只说一句「激活我们的潜在大客户」。

**Claude Code 应当**：
1. 先反问一次（仅当严重模糊时）："『大客户』是指 ARR > 10 万的，还是某个标签？"
2. 拿到具体定义后，全自动走打法 1
3. 如果运营说"你看着办"，按经验默认（活跃-重点 + behavior_msg_gte_10 + 转化阶段 = potential，作为初稿），但**显式标注假设**

**容易踩的坑**：在没有明确定义时直接 propose，可能选错人。**宁愿多问一次**也比错发好。

---

## 打法 9 · 按问卷答案建分层（5 月新版本激活实例）

**场景**：运营说「给百万以下 + 有私教需求的用户发新版本激活通知」。

这类需求的核心是「**用问卷答案做精准分层**」，CRM 提供了 4 个 read-only 工具组合完成 — **任何问卷字段、任何组合，都用同一组工具，绝不写一次性脚本**。

### 4 步标准流

#### Step 1: 找目标问卷
```
list_questionnaires(keyword="激活")
```
返回所有标题含"激活"的问卷 + 每个的提交数。从中拿到 `questionnaire_id`。

#### Step 2: 看题目结构 + 选项分布
```
inspect_questionnaire(questionnaire_id=N)
```
返回完整树：每个 question 的 title / type / 全部 options 的 text 和 `selected_count`（被选过几次）。Agent 能看清「这道题有什么选项、各被多少人选了」，再决定 mapping：
- 「百万以下」 → 选项 ids `[1, 2]`（"50 万以下"、"50-100 万"）
- 「需要私教」 → 选项 id `[4]`（"需要"，注意别误选含"需要"二字的"不需要"）

#### Step 3: 验证人数
```
preview_questionnaire_population(filters=[
  {"question_id": 1, "option_ids": [1, 2]},          # 年收入 < 100万
  {"question_id": 2, "option_ids": [4]}               # 需要私教
])
```
返回 headcount + 样本 + filters_resolved（确认每个 filter 解析后命中了哪些 option）。如果数字明显不合理（比如 0 或 1 万）就回去调 filters。

#### Step 4: 拼 SQL → 落地分层
```
compose_segment_sql_from_questionnaire(filters=[...同上])
```
返回完整可用的 segment SQL + 试跑 headcount。把 sql_query 直接塞进 `propose_segment`：

```
propose_segment(
  segment_code="income_lt_100w_with_coach_intent",
  display_name="百万以下 + 需私教 · 5月激活目标",
  description="默认转化方案下、运营中的成员，问卷答过年收入 < 100 万 + 需要私教",
  sql_query=<上一步返回的 sql_query>,
  activate=true
)
```

#### Step 5: 用这个 segment 出 Campaign
```
propose_campaign(
  display_name="5 月新版本激活 · 百万以下需私教",
  intent="向百万以下 + 需私教用户介绍 5 月新版本（成长地图 + 功课 + 私教模式）",
  anchor_mode="member_joined_at",
  segments=[{
    "segment_code": "income_lt_100w_with_coach_intent",
    "priority": 999,
    "label": "目标人群",
    "steps": [
      {"step_index": 0, "day_offset": 0, "send_time": "10:00", "content_text": "..."},
      {"step_index": 1, "day_offset": 3, "send_time": "10:00", "content_text": "..."},
      {"step_index": 2, "day_offset": 7, "send_time": "10:00", "content_text": "..."}
    ]
  }]
)
```

### 关键规则

1. **不要写脚本**。每个新需求都是上面 4 步 + propose_segment + propose_campaign。脚本只是同样动作的硬编码版本，不可持续。
2. **option_text_keywords vs option_ids**：keyword 用 LIKE 模糊匹配，方便但可能误中（如 `'需要'` 也匹配 `'不需要'`）。**inspect 看到完整选项后，优先用 option_ids 精确指定**。
3. **多题 AND，每题内 OR**：filters 之间是 AND 关系（"既……又……"），filter 内的 option_ids 是 OR 关系（"……或者……"）。
4. **试跑 headcount 不合理就停下来问运营**。例如 0 个、或者 1 万这种数字，大概率 filter 不对，别贸然 propose 出去。

---

## 打法 10 · 出错排查（系统报错或效果异常）

**场景**：发完了但 sent_count 远低于 candidate_count；或者 propose_campaign 时分配失败。

**排查路径**：
1. 拿到 `trace_id`
2. 让运营到 CRM 后台 `/admin/cloud-orchestrator/observability` 输 trace_id
3. 你这边可以调 `query_recent_touch_outcomes(trace_id=...)` 看到 skipped 原因
4. 常见原因：
   - `budget_exceeded:<budget_code>` — 触发了运营在 admin 配置的频次预算（默认无内置预算；运营自加 budget 才会出现这个）
   - `do_not_disturb` — 用户在屏蔽列表
   - `missing_external_userid` — 数据完整性问题，给运营报

---

## 给所有打法的共性建议

1. **先 dry-run 再 propose**：`preview_segment_members` 看人数 + `validate_segment_sql` 检查 SQL，再正式 propose。
2. **每次操作带 trace_id 透传**：调 `propose_campaign` 时 CRM 自动生成 trace_id 并贯穿三端，但你在跨工具调用时，输出里的 trace_id 在后续工具的 audit 里能查到。
3. **写 prompt 给话术 AI 时附带"为什么是这群人"**：例如"目标是 78 个职场人，平均沉默 21 天，过去对'效率'类话术响应率 12%"。这给话术 AI 的写作背景，比单纯说"写一条激活话术"效果强很多。
4. **节奏设计的经验值**：
   - 沉默激活：3 步 ≤ D+10
   - 限时活动：3 步 ≤ D+7
   - 新人 onboarding：4-5 步 ≤ D+14
   - **绝不超过 6 步**，超过就切到运营 SOP 长期跟进
