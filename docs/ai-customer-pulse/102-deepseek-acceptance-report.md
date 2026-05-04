# DeepSeek Integration Acceptance Report

## 1. 验收范围

本次验收聚焦 `Customer Pulse` 是否已经真正接入真实 `DeepSeek`，并在当前“可受限外放”的口径下满足：

- 真实 provider 已接管 AI 生成链路，而不是 mock / no-op / 仅规则兜底
- 配置读取来自现有系统设置或运行时配置，而非硬编码
- strict JSON 输出、fallback、tenant / RBAC / audit / evidence 安全约束仍成立
- 外发消息仍然只能先草稿预览、人工确认，禁止静默发送
- 双 tenant、权限边界、现有 `Customer Pulse` 主流程不被破坏

## 2. 改动文件清单

本轮最终验收新增文件：

- `docs/ai-customer-pulse/102-deepseek-acceptance-report.md`

本轮验收未新增 DeepSeek 代码修复；验收依赖此前已落库的实现与测试。

## 3. 运行命令

文档与实现核对：

- `sed -n '1,260p' docs/ai-customer-pulse/101-deepseek-integration.md`
- `sed -n '1,220p' wecom_ability_service/domains/customer_pulse/ai_recommendation.py`
- `sed -n '1,220p' wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py`
- `sed -n '1,260p' wecom_ability_service/domains/automation_conversion/agents/llm_client.py`

配置读取检查：

- 本地 `app_settings` / 环境变量存在性检查，未输出 secret 值

质量门：

- `make check`
- `./.venv310/bin/python -m pytest -q tests/test_customer_pulse_inbox.py`
- `./.venv310/bin/python -m pytest -q tests/test_customer_pulse_quality_gates.py`
- `./.venv310/bin/python -m pytest -q`

定向场景验证：

- `./.venv310/bin/python -m pytest -q tests/test_customer_pulse_inbox.py tests/test_customer_pulse_quality_gates.py tests/test_followup_orchestrator_skeleton.py -k 'accepts_structured_output or falls_back_on_invalid_json_output or falls_back_on_provider_timeout or low_confidence or evidence_permission or outputs_isolated_across_tenants or ai_enhancement_accepts_structured_output or ai_enhancement_degrades_on_low_confidence or provider_unavailable'`

live smoke：

- 临时 app + 真实 DeepSeek key 的 Customer Pulse recompute smoke
- 临时 app + 真实 DeepSeek key 的 orchestrator handoff smoke
- 临时 app + 真实 DeepSeek key 的日志安全 smoke

## 4. 测试结果

质量门结果：

- `make check`: PASS
- `Customer Pulse e2e`: PASS, `41 passed`
- `1000 卡片 perf gate`: PASS, `1 passed`
- 全仓 `pytest -q`: PASS, `623 passed`

定向场景测试结果：

- DeepSeek structured output / fallback / low confidence / RBAC / dual tenant / orchestrator AI enhancement: PASS, `10 passed`

## 5. Live DeepSeek Smoke Test 结果

### 5.1 配置前置检查

在当前工作区可直接读取到的本地配置中：

- 本地 `data.sqlite3` 的 `app_settings` 中未发现 `DEEPSEEK_ENABLED / DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL`
- 当前 shell 环境变量中也未发现 `DEEPSEEK_ENABLED / DEEPSEEK_API_KEY`

因此，仓库当前工作区本身不带可直接复用的持久化 DeepSeek 配置。

### 5.2 本次 live smoke 的执行方式

验收过程中使用一次性临时测试 key，在临时 app 配置中注入：

- `DEEPSEEK_ENABLED=true`
- `DEEPSEEK_API_KEY=<临时测试 key>`
- `DEEPSEEK_EXECUTION_MODEL=deepseek-chat`

该 key 未写入代码、未写入文档、未写入本地数据库、未输出到日志。

### 5.3 Customer Pulse live smoke

真实调用结果：

- `customer_pulse.recompute.status_code = 200`
- `customer_pulse.ai_status = accepted`
- `customer_pulse.provider = deepseek`
- `customer_pulse.model = deepseek-chat`
- `has_summary = true`
- `has_why_now = true`
- `evidence_count = 4`
- `has_draft = true`
- `has_handoff = true`

结论：

- 真实 DeepSeek 已成功接管 `action card summary / whyNow / evidence-backed explanation`
- 真实 DeepSeek 已成功生成 `draftText`
- 真实 DeepSeek 已成功返回 `handoffSummary`

### 5.4 Orchestrator live smoke

真实调用结果：

- `orchestrator_direct.status = accepted`
- `orchestrator_direct.provider = deepseek`
- `orchestrator_direct.model = deepseek-chat`
- `has_handoff = true`
- `has_assignment_why = true`
- `has_escalation_why = true`
- `evidence_count = 4`
- `per_item_drafts = 1`

结论：

- 真实 DeepSeek 已成功跑通 `handoffSummary / manager explanation`
- 同时验证了 batchable item 的逐项草稿建议输出

### 5.5 日志安全 smoke

真实调用后落库检查结果：

- `automation_agent_run.provider = deepseek`
- `automation_agent_run.status = success`
- `automation_agent_llm_call_log.model_name = deepseek-chat`
- `automation_agent_output.output_type = next_action_suggestion`
- `final_prompt_preview` 中未发现 API key、`Authorization` header 或 secret 片段

结论：

- 真实调用有审计与运行日志
- 日志中未发现 secret 泄露

## 6. A-N 逐项 PASS / FAIL

### A. `101-deepseek-integration.md` 存在且与实现一致

- PASS

### B. Customer Pulse AI provider 已接到真实 DeepSeek，而不是 mock / no-op / 仅本地伪造

- PASS
- 证据：代码默认 provider 为 `DeepSeekPulseRecommendationProvider`；live smoke 返回 `provider=deepseek` 且 `status=accepted`

### C. DeepSeek 接入走现有系统配置读取，不存在硬编码 `api_key / base_url / model`

- PASS
- 证据：`llm_client.get_deepseek_runtime_config()` 通过 `get_setting(...)` / `current_app.config` 读取；代码中不存在硬编码真实 key / base_url / model 值

### D. 默认模型为 `deepseek-chat`；`deepseek-reasoner` 必须显式可配，不得默认误开

- PASS
- 证据：默认 `DEEPSEEK_EXECUTION_MODEL = deepseek-chat`；`CUSTOMER_PULSE_DEEPSEEK_USE_REASONER` / `FOLLOWUP_ORCHESTRATOR_DEEPSEEK_USE_REASONER` 为显式开关

### E. 真实生成链路覆盖 3 个生成点

- PASS
- `action card summary / whyNow / evidence-backed explanation`: live smoke 通过
- `reply draftText`: live smoke 通过
- `handoffSummary / manager explanation`: live smoke 通过

### F. strict JSON 输出与稳定解析成立

- PASS
- 证据：prompt 明确要求 JSON object，`response_format={"type":"json_object"}`，并有 normalize / validation / strict field checks

### G. timeout / provider error / invalid json / low confidence 时自动回退，不阻断主流程

- PASS
- 证据：定向测试通过，包括 provider timeout、invalid json output、low confidence fallback

### H. 所有输出仍然 tenant-scoped、RBAC-controlled、audit-covered

- PASS
- 证据：request-scoped tenant、权限和审计链路已有测试覆盖；live 日志也能看到 provider/model/request_id 落库

### I. `evidenceRefs` 不会泄露跨租户或越权内容

- PASS
- 证据：无 evidence 权限时只返回裁剪后的 refs；跨租户 / 越权 evidence 测试通过

### J. 外发消息仍然必须先进入草稿预览/人工确认，不能被 DeepSeek 直接静默发送

- PASS
- 证据：现有 action preview / execute 流程与测试仍要求 preview；DeepSeek 仅生成 `draftText`

### K. 双 tenant 场景下不会串租户

- PASS
- 证据：dual tenant 定向测试通过，tenant_a / tenant_b 输出、evidence、detail、log 不串用

### L. 不破坏既有 Customer Pulse 主流程

- PASS
- 证据：全仓 `pytest -q` 通过；Customer Pulse e2e / perf gate / feedback / metrics / action executor 相关测试通过

### M. 质量门全部通过

- PASS
- `make check`: PASS
- `pytest`: PASS
- `Customer Pulse e2e`: PASS
- `perf gate`: PASS

### N. 当前是否达到“可受限开启真实 DeepSeek”的标准

- PASS

## 7. 修复记录

本轮最终验收未发现新的 DeepSeek 集成代码缺陷，因此未新增修复提交。

验收期间新增的是证据补充，而不是代码修复：

- 核对文档与实现一致性
- 验证当前工作区缺少持久化 DeepSeek 配置
- 使用一次性临时测试 key 完成真实 DeepSeek smoke
- 验证日志落库但不泄露 secrets

## 8. 剩余风险

1. 当前工作区本地 `app_settings` / 环境变量中没有持久化 DeepSeek 配置；本次 live 证据来自一次性临时测试 key。部署到目标环境时，仍需确保目标环境自己的 `DEEPSEEK_ENABLED / API_KEY / BASE_URL` 已正确配置。
2. `deepseek-reasoner` 已具备显式配置开关，但尚未作为默认模型；不建议在外部租户直接默认开启。
3. 真实模型输出仍受上游 provider 波动影响，因此建议继续保留 fallback 和低置信度保守策略。

## 9. 外部租户建议开启项 / 暂不建议开启项

建议先开启：

- action card 的 `summary`
- `whyNow`
- evidence-backed explanation
- 单卡 `draftText` 生成
- `handoffSummary / manager explanation` 的受限灰度

暂不建议默认开启：

- `deepseek-reasoner`
- 低置信度建议展示
- 大批量 AI 草稿使用场景
- 任何自动发送外部消息能力

## 10. 最终结论

**可受限开启真实 DeepSeek**
