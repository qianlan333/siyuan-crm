# Wave 4 Automation Engine PR Plan

日期：2026-04-21

## 1. 目标

Wave 4 不做一次性大拆 `marketing_automation` 或 `automation_conversion` 内部模块。

后续实施必须按小 PR 串行推进，并且每一刀都满足：

- 不改 path
- 不改核心 JSON key
- 不改 activation / callback / retry / due runner 主错误语义
- 不进入 `user_ops` / `questionnaire` / `customer_pulse` / `followup_orchestrator` 内部拆分
- 先建 formal application owner，再切 caller，再收紧 shim / guardrail

## 2. 推荐 PR 顺序

## PR 1：Automation Contract Pack + Freeze Alignment

- 目标
  - 固化 automation 的 scope、formal contracts、caller map、test freeze、PR plan
  - 对齐 Wave 4 唯一口径
- 涉及文件
  - `docs/refactor/wave4-automation-scope.md`
  - `docs/refactor/wave4-automation-contracts.md`
  - `docs/refactor/wave4-automation-callers-map.md`
  - `docs/refactor/wave4-automation-test-plan.md`
  - `docs/refactor/wave4-automation-pr-plan.md`
- 不涉及文件
  - 任何 `wecom_ability_service/*.py`
  - 任何测试文件
- 风险
  - 风险主要是 contract 口径不统一
- 回滚方式
  - 回退文档即可
- 必跑测试
  - 无

## PR 2：Automation Application Skeleton + services shim delegation

- 目标
  - 扩展 `application/automation_engine/*` 成正式 skeleton
  - 把 `services.py` 中 automation 兼容符号先转到 formal application API
  - 不切 caller
- 涉及文件
  - `wecom_ability_service/application/automation_engine/__init__.py`
  - `wecom_ability_service/application/automation_engine/dto.py`
  - `wecom_ability_service/application/automation_engine/queries.py`
  - `wecom_ability_service/application/automation_engine/commands.py`
  - `wecom_ability_service/application/automation_engine/_legacy_delegate.py`
  - `wecom_ability_service/services.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_config.py`
  - `wecom_ability_service/http/customer_automation.py`
  - `wecom_ability_service/http/automation_conversion.py`
  - `wecom_ability_service/http/background_jobs.py`
- 风险
  - skeleton 写成第二个 `services.py`
  - application 层反向 import `http/*`
- 回滚方式
  - 回退 application skeleton 与 `services.py` 的 wrapper 指向
- 必跑测试
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`
  - 建议新增 `tests/test_automation_application_contract.py`

## PR 3：Signup Conversion / Activation / Outbound Retry Cutover

- 目标
  - 收口 Wave 1 已触及但 owner 仍不完整的 automation 边缘入口
  - 先切 `admin_config`、`customer_automation`、`admin_jobs`
- 涉及文件
  - `wecom_ability_service/http/admin_config.py`
  - `wecom_ability_service/http/customer_automation.py`
  - `wecom_ability_service/domains/admin_jobs/service.py`
  - `wecom_ability_service/application/automation_engine/queries.py`
  - `wecom_ability_service/application/automation_engine/commands.py`
  - 如必要：`tests/test_refactor_guardrails.py`
- 不涉及文件
  - `wecom_ability_service/http/automation_conversion.py`
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/http/background_jobs.py`
- 风险
  - signup conversion preview / recompute payload 漂移
  - activation webhook 后续 member sync 漏掉
  - outbound retry list/count/filter 漂移
- 回滚方式
  - caller 回退到 legacy `services.py` / Wave 1 skeleton
- 必跑测试
  - `tests/test_marketing_automation.py -k "signup_conversion_config or preview or recompute or activation_webhook or webhook"`
  - `tests/test_admin_config.py -k "marketing_automation or automation_conversion"`
  - `tests/test_admin_jobs_console.py -k "webhook"`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## PR 4：Marketing Truth / Member State / Callback Cutover

- 目标
  - 收口 manual marketing truth 写入口与 member-state callback 入口
  - 切 `sidebar`、`admin_support`、`background_jobs`，并 formalize `http/automation_conversion.py` 的 overview/member/stage/member-op 面
- 涉及文件
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/http/admin_support.py`
  - `wecom_ability_service/http/background_jobs.py`
  - `wecom_ability_service/http/automation_conversion.py`
  - `wecom_ability_service/application/automation_engine/queries.py`
  - `wecom_ability_service/application/automation_engine/commands.py`
  - `tests/test_refactor_guardrails.py`
  - 如必要：`tests/test_automation_facade_guards.py`
- 不涉及文件
  - workflow CRUD / execution 详细切换
  - SOP / focus send / reply monitor
  - agent orchestration
- 风险
  - `mark_enrolled` / `unmark_enrolled` 的 class_user side effect
  - qrcode callback 的 welcome/tag/SOP 副作用
  - `tests/test_automation_facade_guards.py` 里旧 direct-binding 断言会失效
- 回滚方式
  - caller 回退到 legacy `services.*` / `domains.automation_conversion.service.*`
  - formal contract 文件保留不删
- 必跑测试
  - `tests/test_marketing_automation.py -k "enrolled or webhook"`
  - `tests/test_automation_conversion_v1.py -k "member or stage or qrcode"`
  - `tests/test_user_ops_api.py -k "qrcode_automation_raises"`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## PR 5：Workflow CRUD / Audience / Execution Cutover

- 目标
  - 把 workflow admin model、audience sync、execution read、dashboard 收口到 formal automation API
  - 只切 workflow 这条主线
- 涉及文件
  - `wecom_ability_service/http/automation_conversion.py`
  - `wecom_ability_service/application/automation_engine/queries.py`
  - `wecom_ability_service/application/automation_engine/commands.py`
  - 如必要：`tests/test_automation_application_contract.py`
  - 如必要：`tests/test_refactor_guardrails.py`
- 不涉及文件
  - SOP / focus send / reply monitor
  - agent orchestration / router callback
  - `http/admin_config.py`
- 风险
  - workflow editor payload / node editor payload 漂移
  - execution detail / item detail 页面结构漂移
  - audience sync 因依赖 questionnaire / recent messages / user_ops payload 而出隐式回归
- 回滚方式
  - workflow caller 回退到 `workflow_service.py` / `workflow_runtime.py`
- 必跑测试
  - `tests/test_automation_conversion_v1.py -k "workflow or execution or dashboard or profile_segment"`
  - `tests/test_run_automation_conversion_due_jobs_script.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`

## PR 6：SOP / Focus Send / Reply Monitor / Due Runner Cutover

- 目标
  - 把 automation runtime 的第二大块收口到 formal automation API
  - 统一 SOP、focus send、reply monitor、registered due jobs 的 caller owner
- 涉及文件
  - `wecom_ability_service/http/automation_conversion.py`
  - `wecom_ability_service/application/automation_engine/queries.py`
  - `wecom_ability_service/application/automation_engine/commands.py`
  - 如必要：`tests/test_refactor_guardrails.py`
  - 如必要：`tests/test_automation_facade_guards.py`
- 不涉及文件
  - workflow CRUD / execution
  - agent orchestration
  - `http/admin_config.py`
- 风险
  - SOP 日历锚点 / 锁 / 幂等
  - focus-send batch/item 失败隔离
  - reply monitor quiet hours / queue merge / dispatch gap
  - `run_registered_due_jobs` multiplexer 因 action 拆分而丢 job
- 回滚方式
  - runtime caller 回退到 `domains.automation_conversion.service`
- 必跑测试
  - `tests/test_automation_conversion_v1.py -k "sop or focus_send or reply_monitor or due_jobs_api_runs_registered"`
  - `tests/test_run_automation_sop_script.py`
  - `tests/test_run_automation_conversion_due_jobs_script.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`

## PR 7：MCP / Admin Console Cleanup + Automation Closeout

- 目标
  - 收口 `application/integration_gateway/mcp_dispatch.py`、`domains/admin_console/service.py` 中剩余 automation bypass
  - 产出 Automation Engine closeout 文档与例外台账
- 涉及文件
  - `wecom_ability_service/application/integration_gateway/mcp_dispatch.py`
  - `wecom_ability_service/domains/admin_console/service.py`
  - `wecom_ability_service/services.py`
  - `docs/refactor/automation-closeout.md`
  - `docs/refactor/automation-remaining-exceptions-ledger.md`
  - 如必要：`tests/test_refactor_guardrails.py`
- 不涉及文件
  - agent orchestration / model infra
  - `customer_pulse`
  - `followup_orchestrator`
- 风险
  - MCP tool payload / admin tool metadata 漂移
  - 误删 legacy shim 导致 console tool / test monkeypatch 失效
- 回滚方式
  - 回退 `mcp_dispatch.py` / `admin_console/service.py` caller 指向
  - closeout 文档单独回退
- 必跑测试
  - `tests/test_mcp_business_tools.py -k "conversion or marketing"`
  - `tests/test_automation_conversion_v1.py`
  - `tests/test_marketing_automation.py`
  - `tests/test_admin_jobs_console.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## 3. 为什么按这个顺序

### 3.1 先切外围 caller，再动 `http/automation_conversion.py`

外围 caller 包括：

- `admin_config`
- `customer_automation`
- `admin_jobs`
- `sidebar`
- `admin_support`
- `background_jobs`

这些入口更小、更稳定，而且已经在 Wave 1 / Wave 2 有 formal application owner 的推进经验。先切它们，能把 Automation Engine 的 contract 稳住，再去碰最大的 `http/automation_conversion.py`。

### 3.2 workflow 与 SOP/runtime 分成两刀

虽然它们都在 `automation_conversion` 域里，但风险完全不同：

- workflow 主线偏 CRUD + audience + execution read
- SOP / focus / reply-monitor 主线偏 due runner + transport dispatch + async callback

把这两块拆开，可以避免一个 PR 同时改 admin editor、execution read、due runner。

### 3.3 MCP / admin console 最后收尾

原因：

- MCP / admin console 不是 automation 的 primary behavior owner
- 它们主要是消费面和 tool registry 面
- 只有当前面 formal automation API 稳定下来，MCP / admin console 才适合一起收尾

## 4. 本轮明确不做的事

- 不在 Wave 4 里先拆 `domains/automation_conversion/service.py` 内部模块
- 不在 Wave 4 里重构 `domains/tasks/service.py` 全 context
- 不在 Wave 4 里顺手改 `customer_pulse` / `followup_orchestrator`
- 不把 agent orchestration / model infra 混进第一批 automation owner 收口
- 不做 schema / SQL migration

## 5. 结论

Wave 4 Automation Engine 的正确推进顺序是：

1. 先把 formal contract 和 skeleton 补齐
2. 再切最外围 admin / callback / retry caller
3. 再切 `http/automation_conversion.py` 的 workflow 与 runtime 主线
4. 最后收 admin console / MCP / closeout

如果一开始就直接改 `http/automation_conversion.py` 全文件，基本会把 Wave 4 重新做成一次不可回滚的大改。
