# Operator Business Closure Evidence Collection Runbook

Status: `READINESS_ONLY`

This runbook guides an approved operator through collecting real, redacted
business-closure evidence for the four 90%+ readiness chains. It does not
authorize real external calls by itself, does not change production
configuration, and does not replace the required operator approval window.

## 1. 总原则

- 只有 operator 可以在批准环境、批准窗口内执行真实取证。
- Git 仓库只允许提交脱敏 evidence、内部 job/event id、模板化说明和诊断输出。
- 没有真实 operator evidence 时，只能保持 `READINESS_ONLY` 或 `BLOCKED`。
- 任何链路缺关键配置、授权、token、receiver、plan、event、job、visibility 或 permission evidence 时，不能 claim `PASS_90_PLUS`。
- `scripts/diagnose_business_closure_acceptance.py` 是只读取证整形工具；它不会执行真实外呼、生产写入、migration 或 deploy/env 修改。
- 本 runbook 不新增 runtime 逻辑、不新增 route、不修改 deploy/systemd/nginx/env、不进入 P1 TypeScript 前端开发。

## 2. 禁止提交的信息

不要把以下内容写入 Git、PR body、issue comment、evidence template、截图正文或诊断样例：

- token
- secret
- corpsecret
- access_token
- Authorization header
- raw external_userid
- 手机号
- 真实 receiver 明文
- 真实订单敏感信息
- openid / unionid / cookie / session id
- 支付凭证、支付回调原始报文、签名密钥
- 任何可直接识别用户、客户、企微成员或支付凭证的信息

允许提交：

- 脱敏后的内部 id，例如 `plan_***`、`effect_job_***`、`event_***`
- operator-owned approval record 引用
- 已去除敏感信息的诊断 JSON
- 已去除敏感信息的页面状态说明
- 四个 evidence template 中要求的非敏感字段

## 3. 运行总控命令

在当前 `main` 上运行：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py --scenario all
```

总控 summary 重点读取这些字段：

- `readiness_status`: 当前链路是否仍是 readiness、blocked、已收集 evidence 或可 claim。
- `evidence_status`: 对应 evidence template 的完成状态。
- `derived_status`: 诊断脚本按证据字段推导出的业务状态。
- `blocking_reasons`: 阻止继续 claim 的明确原因。
- `missing_operator_evidence`: operator 还需要补齐的证据字段。
- `can_claim_90_plus`: 当前链路是否可以纳入 `PASS_90_PLUS`。
- `next_required_operator_action`: 下一步 operator 动作。
- `business_explanation`: 给运营/产品看的状态解释。

状态解释：

- `READINESS_ONLY`: 诊断和模板已就绪，但没有真实 operator evidence。
- `BLOCKED`: 缺关键配置、授权、token、receiver、plan、event、job 或 visibility。
- `EVIDENCE_COLLECTED`: 已有完整 evidence 字段，但还没做最终业务判定。
- `PASS_WITH_NOTES`: 证据基本完整，但存在非阻塞 note；需要 reviewer 明确接受。
- `PASS_90_PLUS`: 四条核心链路证据完整且无阻塞项。

默认没有真实 evidence 时，预期输出不是 `PASS_90_PLUS`，而是 `READINESS_ONLY` 或 `BLOCKED`。

## 4. Group Ops Gray-Send Evidence

对应模板：

```text
docs/reports/group_ops_gray_send_evidence_template.md
```

前置条件：

- operator approval 已批准。
- receiver allowlist 已在批准环境配置。
- receiver token 由 operator 持有，不提交明文。
- 灰度窗口、灰度目标和回滚口径已确认。

只读 readiness 命令：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send
```

批准环境中的 operator readiness 命令示例：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send \
  --execute \
  --receiver-token '<redacted-approved-test-receiver>' \
  --plan-id '<redacted_plan_id>' \
  --effect-job-id '<redacted_effect_job_id>' \
  --attempt-id '<redacted_attempt_id>' \
  --push-center-job-id '<redacted_push_center_job_id>'
```

必须记录的脱敏字段：

- `plan_id`
- `effect_job_id`
- `attempt_id`
- `push_center_job_id`
- `push_center_status`
- `retryable`
- `operator_action_required`
- `business_explanation`

Push Center reconciliation 路径：

```text
/api/admin/push-center/jobs/{job_id}/reconciliation
```

失败处理：

- `missing_operator_approval`: 补 operator approval；未补前保持 `READINESS_ONLY`。
- `missing_receiver_allowlist`: 补批准环境 receiver allowlist；不要提交 receiver 明文。
- `receiver_not_allowlisted`: 停止灰度，确认 receiver 是否为批准测试对象。
- `missing_push_center_visibility`: 补 Push Center reconciliation evidence。
- `failed_attempt`: 记录失败原因、`retryable`、`operator_action_required` 和下一步补偿动作。

保持 `READINESS_ONLY` 的情况：

- 没有批准窗口。
- 没有真实灰度 receiver evidence。
- 没有 effect job / attempt / Push Center job id。

进入 `PASS_WITH_NOTES` / `PASS_90_PLUS` 候选的条件：

- approval、receiver allowlist、plan、effect job、attempt、Push Center reconciliation 全部齐全。
- 没有 blocking reason。
- 失败场景已解释且 reviewer 接受为非阻塞 note。

## 5. Ops Plan -> Broadcast E2E Evidence

对应模板：

```text
docs/reports/ops_plan_to_broadcast_e2e_evidence_template.md
```

前置条件：

- 有真实 ops plan。
- 有真实审批动作或审批记录。
- 能关联 `internal_event`。
- 能关联 `consumer_run`。
- 能关联 broadcast job 或 external effect job。
- 能在 Push Center 看到 projection 或 reconciliation。

诊断命令示例：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario ops_plan_to_broadcast \
  --plan-id '<redacted_plan_id>' \
  --approval-status approved \
  --approval-event-id '<redacted_approval_event_id>' \
  --internal-event-id '<redacted_internal_event_id>' \
  --consumer-run-id '<redacted_consumer_run_id>' \
  --consumer-status succeeded \
  --broadcast-job-id '<redacted_broadcast_job_id_or_not_provided>' \
  --effect-job-id '<redacted_external_effect_job_id_or_not_provided>' \
  --push-center-job-id '<redacted_push_center_job_id>' \
  --duplicate-handling '<reused_idempotency_key_or_not_collected>'
```

必须记录的脱敏字段：

- `plan_id`
- `approval_event_id`
- `internal_event_id`
- `consumer_run_id`
- `broadcast_job_id` 或 `external_effect_job_id`
- `push_center_job_id`
- `derived_status`
- `pending_reason`
- `retryable`
- `operator_action_required`
- `business_explanation`

失败处理：

- `pending_approval`: 不能 claim；等待审批或补审批 evidence。
- `missing_internal_event`: 补 internal event reconciliation。
- `consumer_pending`: 补 consumer run/status。
- `consumer_failed`: 记录 `retryable`、失败原因、补偿动作；未解决前保持 blocked。
- `missing_business_job`: 补 broadcast job 或 external effect job id。
- `missing_push_center_visibility`: 补 Push Center reconciliation。

Duplicate approval 幂等证据：

- 记录重复审批请求或重复 approval event。
- 记录是否复用同一个 internal_event / idempotency key。
- 记录是否没有重复生成 business job。
- 将 `duplicate-handling` 填为 `reused_idempotency_key` 或等价脱敏说明。

## 6. External Orders Evidence

对应模板：

```text
docs/reports/external_orders_enablement_evidence_template.md
```

前置条件：

- `AUTOMATION_INTERNAL_API_TOKEN` 只能由 operator 在 git 外配置。
- 不得提交 token 或 Authorization header。
- 灰度来源、灰度订单和幂等规则已批准。

必须验证：

- token 未配置时是 controlled disabled。
- request token 缺失时被拒绝。
- request token 错误时被拒绝。
- valid token readiness 不写入 Git token 明文。
- 重复订单具备幂等 evidence。
- 订单能关联 customer/channel/source。
- 订单能关联 internal_event。
- 后台或诊断能看到 admin visibility。
- `reconciliation_status` 可解释。

诊断命令示例：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario external_orders \
  --request-mode valid_token \
  --order-no '<redacted_order_id>' \
  --external-order-id '<redacted_external_order_id>' \
  --idempotency-key '<redacted_idempotency_key>' \
  --customer-id '<redacted_customer_id>' \
  --channel-id '<redacted_channel_id>' \
  --source '<source_label>' \
  --internal-event-id '<redacted_internal_event_id>' \
  --admin-order-visibility '<visible|not_found|not_provided>'
```

必须记录的脱敏字段：

- `order_id` / `external_order_id`
- `idempotency_key`
- `customer_id`
- `channel_id`
- `source`
- `internal_event_id`
- `admin_order_visibility`
- `reconciliation_status`

失败处理：

- `missing_internal_token_config`: token 未配置；保持 controlled disabled。
- `missing_request_token`: 补 request token 路径 evidence；不要提交 token。
- `invalid_request_token`: 记录 auth rejection evidence。
- `token_configured_but_not_executed`: 只有 token readiness，没有订单 evidence；保持 `READINESS_ONLY`。
- `missing_order_evidence`: 补订单 id / external order id。
- `missing_idempotency_evidence`: 补重复订单和幂等 evidence。
- `missing_customer_channel_link`: 补 customer/channel/source 关联。
- `missing_internal_event`: 补 internal event。
- `missing_admin_visibility`: 补后台可见性。

External Orders 达到 90%+ 的条件：

- valid-token readiness 已验证。
- 订单、幂等、customer/channel/source、internal_event、admin visibility 全部齐全。
- 没有 token/Authorization header 泄露。
- closeout summary 中 `external_orders.can_claim_90_plus=true`。

## 7. WeCom Auth / Callback Evidence

对应模板：

```text
docs/reports/wecom_operator_auth_callback_evidence_template.md
```

前置条件：

- 真实 operator 授权只能在批准环境完成。
- callback 验签 evidence 必须脱敏。
- callback event、inbound event、idempotency、permission scope 必须有 evidence。
- 不得提交 corpsecret、access_token、raw external_userid 或手机号。

诊断命令示例：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario wecom_auth \
  --redirect-uri-expected '<expected_redirect_uri>' \
  --auth-start-status '<expected_302|verified_302>' \
  --callback-missing-code-status '<controlled_400_expected|observed_400>' \
  --callback-invalid-state-status '<controlled_400_expected|observed_400>' \
  --operator-identity-evidence '<redacted_operator_identity>' \
  --callback-signature-status '<not_provided|invalid|valid>' \
  --callback-event-id '<redacted_callback_event_id>' \
  --internal-event-id '<redacted_inbound_event_id>' \
  --idempotency-key '<redacted_idempotency_key>' \
  --duplicate-callback-handling '<not_collected|reused_idempotency_key>' \
  --permission-scope-evidence '<redacted_scope_summary>' \
  --customer-event-visibility '<visible|not_provided>' \
  --group-ops-permission-evidence '<redacted_group_ops_permission>' \
  --material-permission-evidence '<redacted_material_permission>'
```

必须记录的脱敏字段：

- `corp_id_configured`
- `agent_id_configured`
- `redirect_uri_configured`
- `auth_start_status`
- `callback_missing_code_status`
- `callback_invalid_state_status`
- `operator_identity_evidence`
- `callback_signature_status`
- `callback_event_id`
- `inbound_event_id`
- `idempotency_key`
- `duplicate_callback_handling`
- `permission_scope_evidence`
- `customer_event_visibility`
- `group_ops_permission_evidence`
- `material_permission_evidence`

失败处理：

- `missing_corp_id`: 补批准环境 corp id 配置；不提交敏感配置。
- `missing_agent_id`: 补批准环境 agent id 配置。
- `missing_redirect_uri`: 补 redirect URI readiness。
- `auth_start_not_verified`: 补 auth start 302 evidence。
- `invalid_callback_signature`: 不得入队；记录 controlled failure evidence。
- `missing_inbound_event`: 补 inbound/internal event evidence。
- `missing_permission_scope`: 补客户事件、群运营、素材权限 evidence。

达到候选状态的条件：

- operator auth readiness 完整时，可进入 `OPERATOR_AUTH_READY`。
- callback signature、callback event、inbound event、idempotency、duplicate handling、permission scope 全部齐全时，才可进入 `CALLBACK_LINKED` / `PASS_90_PLUS` 候选。

## 8. 如何填写 Evidence Template

每条链路只填写对应模板，不要把真实 secret 或原始用户标识粘贴进去：

- Group Ops gray-send:
  `docs/reports/group_ops_gray_send_evidence_template.md`
- Ops Plan -> Broadcast E2E:
  `docs/reports/ops_plan_to_broadcast_e2e_evidence_template.md`
- External Orders:
  `docs/reports/external_orders_enablement_evidence_template.md`
- WeCom Auth / Callback:
  `docs/reports/wecom_operator_auth_callback_evidence_template.md`

填写规则：

- 先贴 dry-run 或 readiness payload。
- 再贴真实 operator evidence 的脱敏 id 和状态字段。
- 每个 blocking reason 都要写“是否存在”和“下一步动作”。
- 截图必须先遮挡 token、手机号、raw external_userid、真实 receiver、订单敏感信息。
- 不确定是否敏感时，不提交，改为提交 operator-owned external reference。

## 9. 如何 Claim PASS_90_PLUS

只有以下条件全部满足，才能 claim `PASS_90_PLUS`：

- 四条链路都不能是 `READINESS_ONLY`。
- 四条链路都不能有 blocking reason。
- 四条链路都必须有完整脱敏 evidence。
- closeout summary 必须显示每条链路 `can_claim_90_plus=true`。
- 顶层 closeout summary 必须显示 `can_claim_90_plus=true`。
- 没有 operator evidence 时不能 claim。

最终确认命令：

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py --scenario all
```

如果任何链路仍显示 `BLOCKED`、`READINESS_ONLY`、`missing_operator_evidence` 非空，或 `can_claim_90_plus=false`，则不能 claim `PASS_90_PLUS`。

## 10. 回滚和安全

- 本 runbook PR 是文档-only。
- rollback 为 revert 本 PR。
- 不涉及 runtime rollback。
- 不涉及 deploy/systemd/nginx/env rollback。
- 不涉及 production DB rollback。
- 不涉及 migration rollback。

## 11. Operator 执行顺序建议

1. 先运行总控命令，记录当前缺口。
2. 收集 Group Ops gray-send evidence。
3. 收集 Ops Plan -> Broadcast E2E evidence。
4. 收集 External Orders evidence。
5. 收集 WeCom Auth / Callback evidence。
6. 填写四个 evidence template。
7. 重新运行总控命令。
8. 只有 closeout summary 满足 `PASS_90_PLUS` 规则时，才写 Business Closure 90%+ 结论。
