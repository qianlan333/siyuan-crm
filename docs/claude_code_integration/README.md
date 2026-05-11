# Claude Code × CRM 接入指南

让 Claude Code（或任何兼容 MCP 的 Agent 客户端）直接对接本 CRM，用自然语言完成"选人 → 设计运营计划 → 上架 → 等人工启动 → 自动按节奏推送"的全闭环。

---

## 1. 三端协作的产品定位（先看这个，避免误用）

```
                 ┌──────────────────────┐
                 │  Claude Code（你）   │  ← 提目标、写策略、调工具
                 └──────────┬───────────┘
                            │ MCP HTTP
                ┌───────────▼────────────┐
                │  CRM（能力服务方）      │  ← 池子、画像、互动、调度、发送
                └─────────┬──────────────┘
                          │ 工单
                ┌─────────▼───────────────┐
                │  话术 AI（DeepSeek）    │  ← 写多变体话术
                └─────────────────────────┘
```

**三个边界要记牢**：
- **Claude Code 端只做策略和编排**：选哪个分层、设计什么节奏、给哪些分层分别配什么话术。**不要在 Claude Code 里写最终话术**，让话术 AI 端做（用 `request_copy_workorder` 工具）。
- **CRM 端只做能力 + 人工把关**：所有写操作（启动 Campaign、真发广播）必须人工在 CRM 后台点确认。Claude Code 只能提交"上架"，不能直接发。
- **话术 AI 端是单独的笔杆子**：它有完整的 QA / 话术库，你只需要描述"为这群 X 类用户写一条目的是 Y 的话术"，剩下交给它。

---

## 2. 接入步骤（运营人 / 工程师都看得懂）

### Step 1 拿凭证
1. 登录 CRM 后台
2. 进 `/admin/cloud-orchestrator/integration` （"我的接入凭证"页）
3. 点 **生成新凭证** → 拷下：
   - `MCP Endpoint URL`（例：`https://crm.example.com/mcp`）
   - `Bearer Token`（一次性显示，妥善保存）

### Step 2 在 Claude Code 里加 MCP server
编辑 Claude Code 的 MCP 配置（`~/.config/claude-code/mcp.json` 或当前项目的 `.mcp.json`）：

```json
{
  "mcpServers": {
    "crm": {
      "type": "http",
      "url": "https://crm.example.com/mcp",
      "headers": {
        "Authorization": "Bearer <你的-token>"
      }
    }
  }
}
```

重启 Claude Code，输入 `/mcp` 应该能看到 `crm` 已连接。

### Step 3 把工具方法论喂给 Claude Code
**这一步是关键**：把 [tools.md](./tools.md)、[patterns.md](./patterns.md)、[rules.md](./rules.md) 三个文件**整个粘进**你的项目 `CLAUDE.md` 里（或者放在工作目录让 Claude Code 读到）。这样它一上来就知道工具怎么用、什么要避免。

---

## 3. 立即可用的 5 句话场景

打开 Claude Code，就可以这么说：

> 「激活近 30 天没回复的活跃-重点用户，介绍我们刚上线的新功能。请按用户画像分层，每层独立节奏。」

> 「我们下周一 5月13日要做限时优惠，覆盖所有付费意向客户，从启动日开始 4 天的节奏。」

> 「上周启动的『新人激活』Campaign 效果不好，看一下哪一步问题最大，给我修改建议。」

> 「按沉默 14~30 天的活跃-重点用户建一个分层叫 silent_recent_focus。」

> 「列一下当前所有等待审阅的 Campaign，告诉我每个的目标和候选人数。」

---

## 4. 必读三件事（在 Claude Code 里设计计划前）

1. **互斥保障是系统级的，不用你在 prompt 里担心**。同一用户被多个分层同时命中？数据库 UNIQUE(campaign_id, member_id) 会拒绝重复分配，按 `priority` 高的优先抢人。你只需要给每个 segment 设一个合理的 priority 值。
2. **每次跑工具都附带 trace_id**（系统自动给）。出问题在 CRM 后台 `/admin/cloud-orchestrator/observability` 输 trace_id 一查到底。
3. **真发只能在 CRM 后台点击启动**。你提交后只到"待审"，运营在 CRM 上看完候选 + 节奏 + 话术，点"启动"才会按节奏跑。

---

## 5. 文档清单

- [tools.md](./tools.md) — 21 个工具的标准用法（read / draft / write 副作用分级）
- [patterns.md](./patterns.md) — 9 个典型运营场景的端到端方法论（含 prompt 模板）
- [rules.md](./rules.md) — 必守的 8 条规则（防骚扰、互斥、token、人工 review）
- [troubleshooting.md](./troubleshooting.md) — 常见报错和处理

---

## 6. 一个完整的对话示例

**运营**："激活近 30 天没回复的活跃-重点用户，介绍我们的新功能。"

**Claude Code（应当）**：
1. `query_segment_dimensions` 看维度
2. `list_segments` 看现有命名分层是否能直接用
3. 如果没合适的，`validate_segment_sql` → `propose_segment` 创建一个新分层
4. `preview_segment_members` 看人数是否合理
5. `query_member_interaction_stats` 拉这群人的画像分布
6. 推理出分层（例：3 个画像组）
7. `request_copy_workorder` 给话术 AI 端发工单（每组一份）
8. `propose_campaign` 一次性提交多分层多步骤计划
9. `submit_campaign_for_review` 上架到 CRM
10. **回报运营**："已生成 Campaign camp-xxx，N 人 3 分层，请到 CRM 后台 /admin/cloud-orchestrator/campaigns/xxx 审阅启动"

整个过程对运营透明、每步可解释、出错可追溯。
