# Wave 3 Questionnaire PR Plan

日期：2026-04-20

## 1. 目标

Wave 3 questionnaire 不做一次性大拆。后续实施必须按小 PR 串行推进，并且每一刀都满足：

- 不改 path
- 不改核心 JSON key
- 不改 submit / external push / admin 主错误语义
- 不进入 `automation_conversion` / `customer_pulse` / `followup_orchestrator` 内部拆分

## 2. 推荐 PR 顺序

## PR 1：Questionnaire Contract Pack + Freeze Alignment

- 目标
  - 固化 questionnaire 的 scope、formal contracts、caller map、test freeze、PR plan
  - 对齐 Wave 3 唯一口径
- 涉及文件
  - `docs/refactor/wave3-questionnaire-scope.md`
  - `docs/refactor/wave3-questionnaire-contracts.md`
  - `docs/refactor/wave3-questionnaire-callers-map.md`
  - `docs/refactor/wave3-questionnaire-test-plan.md`
  - `docs/refactor/wave3-questionnaire-pr-plan.md`
- 不涉及文件
  - 任何 `wecom_ability_service/*.py`
  - 任何测试文件
- 风险
  - 风险主要是口径不统一，而不是行为回归
- 回滚方式
  - 回退文档即可
- 必跑测试
  - 无

## PR 2：Questionnaire Application Skeleton + services shim delegation

- 目标
  - 建立 `application/questionnaire/*` 最小 skeleton
  - 把 `services.py` 的 questionnaire 兼容符号先转到 formal application API
  - 不切 caller
- 涉及文件
  - `wecom_ability_service/application/questionnaire/__init__.py`
  - `wecom_ability_service/application/questionnaire/dto.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
  - `wecom_ability_service/application/questionnaire/_legacy_delegate.py`
  - `wecom_ability_service/services.py`
- 不涉及文件
  - `wecom_ability_service/http/public_questionnaires.py`
  - `wecom_ability_service/http/admin_questionnaires.py`
  - `wecom_ability_service/http/admin_questionnaire_console.py`
  - `wecom_ability_service/domains/automation_conversion/*`
- 风险
  - 如果 skeleton 反向 import `http/*` 或把 application 写成第二个 `services.py`，后续会立即失控
- 回滚方式
  - 回退 application skeleton 与 `services.py` 对 questionnaire 的 wrapper 指向
- 必跑测试
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`
  - 建议新增 `tests/test_questionnaire_application_contract.py`

## PR 3：Public / Submit Cutover

- 目标
  - 把 `http/public_questionnaires.py` 改成只调 formal questionnaire API
  - `http/questionnaire_support.py` 保留 transport-only
  - 把 `submit_questionnaire` 的正式 owner 提升到 application/questionnaire
- 涉及文件
  - `wecom_ability_service/http/public_questionnaires.py`
  - `wecom_ability_service/http/questionnaire_support.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
  - 如必要：`wecom_ability_service/domains/questionnaire/service.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_questionnaires.py`
  - `wecom_ability_service/http/admin_questionnaire_console.py`
  - `wecom_ability_service/domains/admin_console/service.py`
  - `wecom_ability_service/domains/automation_conversion/*`
- 风险
  - OAuth/session/openid/unionid/respondent_key 优先级
  - duplicate submit
  - mobile binding / SCRM apply side effect 漏触发
- 回滚方式
  - 回退 public caller 到 legacy `services.submit_questionnaire`
  - 保留 application contract 文件不删
- 必跑测试
  - `tests/test_questionnaire_identity_resolution.py`
  - `tests/test_api.py -k "questionnaire and (oauth or submit or external_push or webhook)"`
  - `tests/test_automation_facade_guards.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## PR 4：Admin CRUD / Export / Preflight Cutover

- 目标
  - 把 `http/admin_questionnaires.py` 改成只调 formal questionnaire API
  - 收口 list/detail/create/update/disable/delete/export/latest-debug/preflight
- 涉及文件
  - `wecom_ability_service/http/admin_questionnaires.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
  - 如必要：`wecom_ability_service/domains/questionnaire/preflight_service.py`
- 不涉及文件
  - `wecom_ability_service/http/public_questionnaires.py`
  - `wecom_ability_service/http/admin_questionnaire_console.py`
  - `wecom_ability_service/domains/admin_console/service.py`
- 风险
  - admin payload 结构和 export 内容最容易出现静默漂移
  - preflight 里跨 context 可用性检查容易被遗漏
- 回滚方式
  - admin controller 回退到 legacy `services.py`
- 必跑测试
  - `tests/test_api.py -k "admin_questionnaire or questionnaire_preflight or questionnaire_export"`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## PR 5：Questionnaire External Push Console Cutover

- 目标
  - 把 external push payload/log/retry owner 提升到 formal questionnaire API
  - 让 `http/admin_questionnaire_console.py` 和 `domains/admin_console/service.py` 不再直连 questionnaire legacy retry
- 涉及文件
  - `wecom_ability_service/http/admin_questionnaire_console.py`
  - `wecom_ability_service/domains/admin_console/service.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
  - 如必要：`wecom_ability_service/domains/questionnaire/service.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_questionnaires.py`
  - `wecom_ability_service/http/public_questionnaires.py`
  - `wecom_ability_service/domains/automation_conversion/*`
- 风险
  - external push retry summary 漂移
  - admin console page filters / failed_current 逻辑漂移
  - submit 后外推日志链断裂
- 回滚方式
  - 回退 admin console caller 到 legacy questionnaire retry helpers
- 必跑测试
  - `tests/test_api.py -k "questionnaire_external_push or questionnaire_submit_webhook"`
  - `tests/test_admin_console_phase4.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## PR 6：Questionnaire Closeout + Remaining Exceptions Ledger

- 目标
  - 缩 `services.py` 的 questionnaire shim
  - 列出仍保留的相邻 consumer 例外
  - 判断 questionnaire 是否具备进入内部模块拆分前的稳定状态
- 涉及文件
  - `wecom_ability_service/services.py`
  - `docs/refactor/wave3-questionnaire-closeout.md`
  - `docs/refactor/questionnaire-exceptions-ledger.md`
  - 如必要：`tests/test_refactor_guardrails.py`
- 不涉及文件
  - `automation_conversion` 内部模块
  - `customer_pulse`
  - `followup_orchestrator`
- 风险
  - 误删 legacy reader 或 compatibility shim
  - 相邻 context 仍有隐式 import，closeout 结论失真
- 回滚方式
  - 回退 `services.py` 缩面和 closeout 文档
- 必跑测试
  - `tests/test_questionnaire_identity_resolution.py`
  - `tests/test_api.py -k "questionnaire or admin_questionnaire"`
  - `tests/test_admin_console_phase4.py`
  - `tests/test_automation_facade_guards.py`
  - `tests/test_marketing_automation.py -k "questionnaire"`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## 3. 为什么按这个顺序

### 3.1 先 contract，再 skeleton，再 caller

Questionnaire 现在最大的问题不是“实现文件太大”，而是：

- caller 面太散
- side effect 太多
- identity / automation / external push 全部混在一个入口

所以必须先把 contract 固化，再建 skeleton owner，再切 caller。

### 3.2 public / submit 先于 admin / external push

原因：

- submit 是 Wave 3 的核心混合点
- 只有先把 submit owner 固化，admin console 那些 external push / latest debug / export 才有稳定依赖面

### 3.3 external push 单独成 PR

原因：

- 它不只是 submit 内部 helper，还牵涉：
  - log payload
  - retry policy
  - admin console 页面
  - batch retry 汇总

把 external push 单独切，可以避免 submit PR 里同时改 public path 和 admin console。

## 4. 本轮明确不做的事

- 不在 Wave 3 第一批里拆 `domains/questionnaire/service.py` 成多个文件
- 不在 questionnaire PR 中顺手拆 `automation_conversion`
- 不在 questionnaire PR 中重构 `admin_console` 全 context
- 不做 schema / SQL migration

## 5. 结论

Wave 3 questionnaire 的正确推进顺序是：

1. contract
2. skeleton owner
3. public / submit cutover
4. admin CRUD / export / preflight cutover
5. external push admin console cutover
6. closeout

只有按这个顺序，才能在不破坏 Wave 2 已完成成果的前提下，把 questionnaire 从 legacy mixed service 拉回正式 application owner。
