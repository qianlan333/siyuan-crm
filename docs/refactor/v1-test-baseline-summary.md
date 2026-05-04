# V1 Test Baseline Summary

日期：2026-04-22

## 目的

本文件用于汇总 V1 最终关单时已建立并被接受的测试基线。

说明：

- 这是基于 Wave 1–5 closeout 期间已通过并被接受的测试资产整理出来的总基线。
- 本次 V1 Master Closeout Pack 仅做文档收尾，没有重新跑整套仓库级全量回归。
- 若某个 wave closeout 文档里记录了该 wave 的最终通过结果，则以该结果为准。

## 基线结构

V1 的测试基线由 4 层组成：

### 1. 全局结构与门禁基线

- `tests/test_service_layer_layout.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

用途：

- 保证 application owner / service layout / HTTP route registration 稳定
- 阻止 caller 回流到 legacy `services.py` / domain service / transport bypass

### 2. Wave 1 基线

- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/contract/test_crm_contract.py`
- `tests/test_mcp_recent_chat_dump.py`
- `tests/test_conversion_service.py`
- `tests/test_admin_jobs_console.py`
- `scripts/test_wave1_smoke.sh`

Wave 1 closeout 中明确记录的结果：

- 关键入口与契约回归：`63 passed`
- `./scripts/test_wave1_smoke.sh`：`PASS`

### 3. Wave 2 基线

- `tests/test_identity_application_contract.py`
- `tests/test_questionnaire_identity_resolution.py`
- `tests/test_class_user_application_contract.py`
- `tests/test_admin_config.py`
- `tests/test_user_ops_api.py`
- `tests/test_admin_jobs_console.py`
- `tests/test_api.py` 中 identity / class_user / routing_config / user_ops / sidebar / background / admin_user_ops 相关子集

用途：

- 冻结 write path formal owner
- 验证 caller cutover 后不再旁路 legacy write
- 冻结 user_ops 主写入口统一状态

### 4. Wave 3 基线

- `tests/test_questionnaire_application_contract.py`
- `tests/test_questionnaire_identity_resolution.py`
- `tests/test_questionnaire_external_push_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_api.py` 中 questionnaire 相关子集

用途：

- 冻结 public / admin / submit / external push 四条线
- 冻结 OAuth / session / identity bridge 行为

### 5. Wave 4 基线

- `tests/test_automation_engine_application_contract.py`
- `tests/test_marketing_automation.py`
- `tests/test_automation_conversion_v1.py`
- `tests/test_admin_jobs_console.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_api.py` 中 automation 相关子集

Wave 4 closeout 中明确记录的结果：

- `tests/test_automation_engine_application_contract.py`：`3 passed`
- `tests/test_automation_conversion_v1.py -k "workflow or execution or dashboard"`：`44 passed, 143 deselected`
- `tests/test_marketing_automation.py`：`39 passed`
- `tests/test_admin_jobs_console.py`：`15 passed`
- `tests/test_api.py -k "automation_conversion or sidebar_signup_tag_mark or questionnaire_submit_webhook"`：`7 passed, 110 deselected`
- `tests/test_api.py -k "marketing_automation or automation_conversion or activation_webhook or webhook_deliveries"`：`2 passed, 115 deselected`

### 6. Wave 5 基线

- `tests/test_ai_assist_application_contract.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/test_customer_pulse_inbox.py`
- `tests/test_customer_pulse_quality_gates.py`
- `tests/test_followup_orchestrator_skeleton.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_api.py` 中 AI Assist 相关子集

Wave 5 closeout 中明确记录的结果：

- `tests/test_ai_assist_application_contract.py`：`3 passed`
- `tests/test_admin_customer_profile_console.py`：`8 passed`
- `tests/test_customer_pulse_quality_gates.py`：`1 passed`
- `tests/test_customer_pulse_inbox.py`：`45 passed`
- `tests/test_followup_orchestrator_skeleton.py`：`13 passed`
- `tests/test_api.py -k "customer_pulse"`：`1 passed, 116 deselected`
- `tests/test_api.py -k "followup_orchestrator"`：`117 deselected`
  - 说明：该模式当前没有单独命名的 `tests/test_api.py` 子集；followup 行为冻结由 `tests/test_followup_orchestrator_skeleton.py` 承担

## V1 最终测试资产清单

当前仓库中与 V1 主线直接相关、已经形成正式冻结面的测试文件包括：

- `tests/test_service_layer_layout.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/contract/test_crm_contract.py`
- `tests/test_mcp_recent_chat_dump.py`
- `tests/test_conversion_service.py`
- `tests/test_admin_jobs_console.py`
- `tests/test_identity_application_contract.py`
- `tests/test_questionnaire_identity_resolution.py`
- `tests/test_class_user_application_contract.py`
- `tests/test_admin_config.py`
- `tests/test_user_ops_api.py`
- `tests/test_questionnaire_application_contract.py`
- `tests/test_questionnaire_external_push_contract.py`
- `tests/test_automation_engine_application_contract.py`
- `tests/test_marketing_automation.py`
- `tests/test_automation_conversion_v1.py`
- `tests/test_ai_assist_application_contract.py`
- `tests/test_customer_pulse_inbox.py`
- `tests/test_customer_pulse_quality_gates.py`
- `tests/test_followup_orchestrator_skeleton.py`

辅助脚本：

- `scripts/test_wave1_smoke.sh`
- `scripts/clean_dev_state.sh`

## 基线使用建议

### 日常改动

至少运行：

- `tests/test_service_layer_layout.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

再按涉及 context 加跑对应 wave 的冻结套件。

### 触碰 formal owner / caller boundary 时

必须加跑：

- 所在 context 的 application contract test
- 所在 context 的 caller 行为测试
- 对应 `tests/test_api.py` 子集

### 触碰 closeout 文档里列出的 remaining exceptions 时

除本 context 的冻结套件外，还应补跑：

- guardrail
- registration contract
- 相关 admin / background / console 行为测试

## 总结

V1 的测试基线已经成型，当前不需要再把 Wave 1–5 作为“进行中的测试设计项目”继续扩展。

后续若有新专题，只应在：

- 继承现有全局门禁基线的前提下
- 为新专题单独定义增量冻结面
- 不回写或稀释已经完成的 V1 基线
