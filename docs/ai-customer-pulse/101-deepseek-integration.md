# Customer Pulse DeepSeek Integration

## 目标

本次集成不是新做一套 AI 基建，而是在现有 `Customer Pulse` 与 `Follow-up Orchestrator` 的 provider abstraction 上，启用真实 `DeepSeek` 生成能力，并保持：

- request-scoped tenant mode 优先
- RBAC 强校验
- evidenceRefs 安全裁剪
- audit / execution log / metric 全链路可追溯
- 外发消息仍然只生成草稿，必须人工确认，禁止自动发送

## 当前接入点

真实 DeepSeek 目前覆盖 3 个生成点：

1. `Customer Pulse action card`
   - `summary`
   - `whyNow`
   - evidence-backed explanation
   - `draftText`
   - `handoffSummary`
2. `Customer Pulse reply draft`
   - 仅在 `actionType=generate_reply_draft` 且 `confidence >= 0.75` 时产出
3. `Follow-up Orchestrator`
   - `handoffSummary`
   - manager / assignment / escalation explanation

## 配置项

全部配置继续从现有系统设置读取，不要求把密钥写进代码。

基础 DeepSeek 配置：

- `DEEPSEEK_ENABLED`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_ROUTER_MODEL`
- `DEEPSEEK_EXECUTION_MODEL`
- `DEEPSEEK_REASONER_MODEL`
- `DEEPSEEK_TIMEOUT_SECONDS`

Customer Pulse 相关：

- `ai_customer_pulse`
- `CUSTOMER_PULSE_DEEPSEEK_USE_REASONER`
- `CUSTOMER_PULSE_ALLOWED_ACTION_TYPES`
- `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS`
- `CUSTOMER_PULSE_TENANT_MODE`
- `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`
- `CUSTOMER_PULSE_FLAG_POLICY_JSON`

Follow-up Orchestrator 相关：

- `ai_followup_orchestrator`
- `FOLLOWUP_ORCHESTRATOR_DEEPSEEK_USE_REASONER`

## 模型选择

默认模型选择策略：

- `Customer Pulse` 默认走 `DEEPSEEK_EXECUTION_MODEL`
- `Follow-up Orchestrator` 默认走 `DEEPSEEK_EXECUTION_MODEL`
- 当前建议默认值保持 `deepseek-chat`

可选 reasoner 开关：

- `CUSTOMER_PULSE_DEEPSEEK_USE_REASONER=true` 时，`Customer Pulse` 显式改走 `DEEPSEEK_REASONER_MODEL`
- `FOLLOWUP_ORCHESTRATOR_DEEPSEEK_USE_REASONER=true` 时，`Follow-up Orchestrator` 显式改走 `DEEPSEEK_REASONER_MODEL`

默认不启用 reasoner，原因：

- 当前外放阶段更关注稳定性、延迟与成本可控
- `deepseek-chat` 已能满足 MVP 所需的结构化解释、草稿和 handoff 生成
- reasoner 适合后续用于复杂 handoff / manager explanation 的受限灰度

## OpenAI-compatible 调用方式

DeepSeek 继续走现有 OpenAI-compatible `/chat/completions` 客户端，不新增平行 SDK 层。

关键调用约束：

- `response_format={"type":"json_object"}`
- prompt 明确要求只输出一个 JSON object
- 所有生成都经由现有 `call_deepseek_agent(...)` 进入统一日志与审计链路

## Structured JSON 合同

Customer Pulse 当前要求模型输出以下字段：

```json
{
  "summary": "string",
  "actionType": "generate_reply_draft | create_followup_task | update_followup_segment | update_tags | set_followup_reminder",
  "actionTitle": "string",
  "whyNow": "string",
  "evidenceRefs": [
    {
      "sourceType": "string",
      "sourceId": "string"
    }
  ],
  "draftText": "string",
  "confidence": 0.0,
  "handoffSummary": "string",
  "safeFieldUpdates": {
    "followupSegment": "string",
    "nextFollowupAt": "string",
    "addTagIds": [],
    "removeTagIds": []
  }
}
```

约束：

- `actionType` 只能从 rule-based 候选和系统白名单中选择
- `evidenceRefs` 只能引用 `allowedEvidenceRefs`
- `draftText` 在低置信度或非回复动作时必须为空
- `handoffSummary` 仅作为内部说明，不允许包含未授权原文
- `safeFieldUpdates` 仅允许安全字段

## 回退策略

以下情况统一回退到现有 rule-based 建议：

- API error
- timeout
- invalid response json
- invalid output json
- confidence too low
- evidenceRefs 非法
- 输出命中 guardrail

回退后保证：

- 页面仍能看到 rule-based action card
- 外发草稿不会自动补全为不可信 AI 内容
- `ai_payload` 保留 `fallback_reason`、`error_message`、`provider`、`request_id`

## 安全与隔离

真实 DeepSeek 接入后，以下约束保持不变：

- 外部租户必须使用 `request_scoped` tenant mode
- `legacy_internal` 仅允许内部环境
- card/list/detail/evidence/action executor 全部 tenant-scoped
- 无 evidence 权限时，只返回裁剪后的 `evidenceRefs`，不返回原始文本
- AI 输出和执行结果都打审计标签，例如 `ai_suggested`、`human_confirmed`、`human_edited`

## 测试覆盖

本次新增或补强的集成测试覆盖：

- DeepSeek provider 正常返回并落库 trace
- invalid json output 自动降级
- timeout 自动降级
- 无 evidence 权限时不泄露原始证据
- dual tenant 下输出不串租户

完整质量门仍通过：

- `make check`
- `pytest -q`
- `Customer Pulse e2e`
- `perf gate`

## 已知限制

1. 当前仍依赖现有 OpenAI-compatible HTTP client，而不是引入新的 SDK 封装；这是刻意保持最小爆炸半径。
2. `deepseek-reasoner` 已预留开关，但默认关闭，尚未作为外放默认模型。
3. 低置信度下仍以 rule-based 卡片兜底，不会生成可外发草稿。

## 外部租户建议

建议先开启：

- action card 的 `summary`
- `whyNow`
- evidence-backed explanation
- 低风险的 `handoffSummary`

建议继续默认关闭或受限灰度：

- `deepseek-reasoner`
- 低置信度建议展示
- 所有涉及外发草稿的大范围批量使用场景

对外放租户的推荐顺序：

1. 先开 `summary + whyNow + evidenceRefs`
2. 再开单卡 `draftText` 草稿生成
3. 最后灰度 `handoffSummary / manager explanation`
