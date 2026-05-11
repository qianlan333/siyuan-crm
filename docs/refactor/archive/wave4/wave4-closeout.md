# Wave 4 Closeout

日期：2026-04-21

## 正式判断

按 2026-04-21 最新两份回单合并判断，Wave 4 的唯一阻塞 gate 已清绿。Wave 4 的目标是让 `automation_engine` 从 legacy `services.py` + `domains/automation_conversion/*` / `domains/marketing_automation/*` / `domains/outbound_webhook/*` 的混合 owner，收口到正式 `application/automation_engine/*`，并完成第一轮内部 owner 拆分。当前仓库状态已经满足这个目标。

正式结论：Wave 4 已 completed and closed。

## 主线验收结果

| 主线 | formal application API 是否已建立 | primary caller 是否已切走 legacy automation 主入口 | `services.py` 是否已不再承担主要入口 | guardrail / contract 是否已覆盖 | 结论 |
| --- | --- | --- | --- | --- | --- |
| admin/read-write caller cutover | 是，`wecom_ability_service/application/automation_engine/queries.py` 与 `commands.py` 已建立 config、batch、retry、activation、marketing truth 入口 | 是，`http/admin_config.py`、`http/customer_automation.py`、`http/background_jobs.py`、`http/sidebar.py`、`domains/admin_jobs/service.py` 已切到 application owner | 是，只保留 compatibility wrapper | 是，`tests/test_refactor_guardrails.py` 与 HTTP / API 回归已覆盖 | 通过 |
| member state | 是，activation / callback / state-write 已有正式 command owner | 是，background callback / activation 这类跨 context caller 已切到 application owner | 是 | 是，caller guardrail 已覆盖 background / sidebar / admin jobs bypass | 通过 |
| signup conversion | 是，batch read / feedback / ack 已有正式 query / command owner | 是，customer automation、admin config、sidebar 等外层 caller 已不再以 `services.py` 为默认 owner | 是 | 是，Wave 4 contract 与现有 HTTP 回归已冻结主线 | 通过 |
| outbound webhook / retry | 是，list / count / retry / run-due 已进入正式 query / command | 是，customer automation 与 admin jobs 已切到 application owner | 是 | 是，Wave 1 + Wave 4 guardrail 已覆盖 | 通过 |
| workflow runtime | formal public contract 没有继续扩到完整 workflow admin surface，但 runtime / execution / router 的内部 owner 已建立 | 外层 primary caller 不再由 `services.py` 承担；同 context workflow transport 仍保留 façade | 是 | 是，closeout gate 已补齐 workflow/runtime 兼容回归 | 通过 |
| message dispatch | formal context owner 由 `application/automation_engine/*` 承接其上游 caller，内部 dispatch owner 已拆出 | 是，对外 primary caller 已不再直接暴露 dispatch 细节为 owner | 是 | 是，marketing automation 主回归与 API 子集回归已覆盖 | 通过 |

## 最终通过的测试结果

### 1. Wave 4 closeout gate 关键测试

- `./.venv311/bin/python -m pytest -q tests/test_automation_engine_application_contract.py`
  - `3 passed`
- `./.venv311/bin/python -m pytest -q tests/test_automation_conversion_v1.py -k "workflow or execution or dashboard"`
  - `44 passed, 143 deselected`

### 2. 合并两份回单后的最终回归

- `./.venv311/bin/python -m pytest -q tests/test_http_registration_contract.py`
  - `5 passed`
- `./.venv311/bin/python -m pytest -q tests/test_refactor_guardrails.py`
  - `10 passed`
- `./.venv311/bin/python -m pytest -q tests/test_marketing_automation.py`
  - `39 passed`
- `./.venv311/bin/python -m pytest -q tests/test_admin_jobs_console.py`
  - `15 passed`
- `./.venv311/bin/python -m pytest -q tests/test_api.py -k "automation_conversion or sidebar_signup_tag_mark or questionnaire_submit_webhook"`
  - `7 passed, 110 deselected`
- `./.venv311/bin/python -m pytest -q tests/test_api.py -k "marketing_automation or automation_conversion or activation_webhook or webhook_deliveries"`
  - `2 passed, 115 deselected`

### 3. 测试结论

最终通过结果已经覆盖：

- application delegate seam 一致性
- workflow/runtime 兼容主路径
- HTTP registration contract
- refactor guardrails
- marketing automation 回归
- admin jobs console automation 回归
- automation 相关 API 子集回归

因此，Wave 4 目前不存在新的唯一红灯。

## 仍保留的非阻塞例外

以下问题仍存在，但都不再阻塞 Wave 4 正式关单：

- `wecom_ability_service/services.py` 的 automation compatibility wrappers 仍保留
- `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` 仍保留 automation legacy bridge
- `wecom_ability_service/domains/admin_console/service.py` 的 automation `service_paths` 仍指向 `services.py`
- `wecom_ability_service/http/customer_automation.py::_candidate_context` 仍是兼容聚合点
- `wecom_ability_service/http/automation_conversion.py` 仍保留同 context legacy façade
- `wecom_ability_service/domains/marketing_automation/service.py` 中 config / preview / recompute / truth 仍未进一步细拆
- `wecom_ability_service/domains/automation_conversion/orchestration_service.py` 中 agent orchestration / review façade 仍较重
- `wecom_ability_service/domains/automation_conversion/workflow_runtime.py` 与 `workflow_service.py` 仍是 legacy delegate target
- `wecom_ability_service/domains/outbound_webhook/service.py` 中 runtime / transport helper 仍留在旧 service
- `wecom_ability_service/domains/tasks/service.py::dispatch_wecom_task` 仍是 automation runtime 的下游 transport 依赖

这些例外的详细记录见：

- [automation-engine-closeout.md](/Users/qianlan/Downloads/CRM%20开发/AI-CRM%20开发/docs/refactor/automation-engine-closeout.md)
- [automation-engine-remaining-exceptions-ledger.md](/Users/qianlan/Downloads/CRM%20开发/AI-CRM%20开发/docs/refactor/automation-engine-remaining-exceptions-ledger.md)
- [automation-engine-primitive-boundary.md](/Users/qianlan/Downloads/CRM%20开发/AI-CRM%20开发/docs/refactor/automation-engine-primitive-boundary.md)

## Wave 4 关单结论

Wave 4 的 formal owner、primary caller cutover、internal owner 第一轮拆分、compatibility gate 和关键回归都已经到位。

唯一阻塞项已清零，因此 Wave 4 已 completed and closed。
