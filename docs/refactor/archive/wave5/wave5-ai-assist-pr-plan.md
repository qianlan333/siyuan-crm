# Wave 5 AI Assist PR Plan

日期：2026-04-21

## 1. 目标

Wave 5 AI Assist 不做一次性大拆。后续实施必须按小 PR 串行推进，并且每一刀都满足：

- 不改 path
- 不改核心 JSON key
- 不改 customer pulse / followup orchestrator 的主要错误语义
- 不进入 `customer read model` / `automation engine` / `user_ops` / `questionnaire` 的内部拆分

## 2. 推荐 PR 顺序

## PR 1：AI Assist Application Owner Hardening

- 目标
  - 把 `application/ai_assist/*` 从当前单条 pulse detail skeleton 补成真正的 formal owner
  - 建立 `dto.py` / `queries.py` / `commands.py` / `_legacy_delegate.py`
  - 不切 caller
- 涉及文件
  - `wecom_ability_service/application/ai_assist/__init__.py`
  - `wecom_ability_service/application/ai_assist/dto.py`
  - `wecom_ability_service/application/ai_assist/queries.py`
  - `wecom_ability_service/application/ai_assist/commands.py`
  - `wecom_ability_service/application/ai_assist/_legacy_delegate.py`
  - 如必要：最小 runtime / adapter 文件
  - 如必要：`tests/test_ai_assist_application_contract.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/http/admin_followup_orchestrator.py`
  - `wecom_ability_service/domains/customer_pulse/*`
  - `wecom_ability_service/domains/followup_orchestrator/*`
- 风险
  - application 层如果直接 import domain internal owner，后续 caller cutover 会再次失控
- 回滚方式
  - 回退 `application/ai_assist/*` skeleton 和新 application contract test
- 必跑测试
  - `tests/test_ai_assist_application_contract.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_service_layer_layout.py`
  - `tests/test_refactor_guardrails.py`

## PR 2：Customer Pulse Caller Cutover + Admin Profile Boundary

- 目标
  - 把 `http/admin_customer_pulse.py` 改成 controller-only
  - 收口 admin customer profile 的 pulse widget boundary
  - 让 `http/admin_console.py` / `http/admin_customers.py` 的 pulse 可见性改走 formal query
- 涉及文件
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/domains/admin_console/customer_profile_service.py`
  - `wecom_ability_service/http/admin_console.py`
  - `wecom_ability_service/http/admin_customers.py`
  - `wecom_ability_service/application/ai_assist/queries.py`
  - `wecom_ability_service/application/ai_assist/commands.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_followup_orchestrator.py`
  - `wecom_ability_service/domains/followup_orchestrator/*`
  - `wecom_ability_service/domains/customer_pulse/*` 内部拆分
- 风险
  - request-scoped 多租户权限与 evidence mask 漂移
  - pulse widget 兼容 payload 漂移
  - run-due / recompute internal API 漂移
- 回滚方式
  - controller 回退到 legacy domain direct call
  - 保留 application contracts 不删
- 必跑测试
  - `tests/test_admin_customer_profile_console.py`
  - `tests/test_customer_pulse_inbox.py`
  - `tests/test_customer_pulse_quality_gates.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`
  - `tests/test_api.py -k "customer_pulse"`

## PR 3：Followup Orchestrator Caller Cutover

- 目标
  - 把 `http/admin_followup_orchestrator.py` 改成 controller-only
  - 收口 admin shell / customer profile 中 followup visibility 和 URL boundary
- 涉及文件
  - `wecom_ability_service/http/admin_followup_orchestrator.py`
  - `wecom_ability_service/http/admin_console.py`
  - `wecom_ability_service/http/admin_customers.py`
  - 如必要：`wecom_ability_service/domains/admin_console/customer_profile_service.py`
  - `wecom_ability_service/application/ai_assist/queries.py`
  - `wecom_ability_service/application/ai_assist/commands.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/domains/customer_pulse/*` 内部拆分
  - `wecom_ability_service/domains/followup_orchestrator/*` 内部拆分
- 风险
  - team board / my missions / mission detail payload 漂移
  - claim / accept / complete / undo 语义漂移
  - AI enhancement success / fallback / low-confidence degrade 漂移
- 回滚方式
  - controller 回退到 legacy domain direct call
- 必跑测试
  - `tests/test_followup_orchestrator_skeleton.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`
  - `tests/test_api.py -k "followup_orchestrator"`

## PR 4：Customer Pulse Internal Split

- 目标
  - 从 `domains/customer_pulse/service.py` 中抽离 pulse read / action / feedback / metrics 的内部 owner
  - 缩减 customer pulse 大文件，但不改 application contract
- 涉及文件
  - `wecom_ability_service/domains/customer_pulse/service.py`
  - 新建必要的：
    - `customer_pulse_read_service.py`
    - `customer_pulse_action_service.py`
    - `customer_pulse_feedback_metrics_service.py`
  - 如必要：`wecom_ability_service/application/ai_assist/queries.py`
  - 如必要：`wecom_ability_service/application/ai_assist/commands.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/http/admin_followup_orchestrator.py`
  - `wecom_ability_service/domains/followup_orchestrator/*`
- 风险
  - signal / snapshot / card 物化路径复杂，容易出静默兼容回归
  - metrics / security counters / feedback 写回最容易丢字段
- 回滚方式
  - 回退 pulse 内部 owner 抽离文件与 `service.py` facade
- 必跑测试
  - `tests/test_customer_pulse_inbox.py`
  - `tests/test_customer_pulse_quality_gates.py`
  - `tests/test_admin_customer_profile_console.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`
  - `tests/test_api.py -k "customer_pulse"`

## PR 5：Followup Mission / AI Enhancement Internal Split

- 目标
  - 从 `domains/followup_orchestrator/service.py` 中抽离 mission read / mission action / AI enhancement 的内部 owner
  - 缩减 followup 大文件，但不改 application contract
- 涉及文件
  - `wecom_ability_service/domains/followup_orchestrator/service.py`
  - `wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py`
  - 新建必要的：
    - `followup_mission_read_service.py`
    - `followup_mission_action_service.py`
    - `followup_ai_enhancement_service.py`
  - 如必要：`wecom_ability_service/application/ai_assist/queries.py`
  - 如必要：`wecom_ability_service/application/ai_assist/commands.py`
- 不涉及文件
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/domains/customer_pulse/*`
  - `wecom_ability_service/application/automation_engine/*` 对外 contract
- 风险
  - followup 当前直接依赖 pulse cards 和 pulse action，internal bridge 稍有不慎就会断
  - AI enhancement 与 automation runtime / agent output 的边界最容易扩 scope
- 回滚方式
  - 回退 followup 内部 owner 抽离文件与 `service.py` facade
- 必跑测试
  - `tests/test_followup_orchestrator_skeleton.py`
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`
  - `tests/test_api.py -k "followup_orchestrator"`

## PR 6：AI Assist Closeout / Wave 5 Closeout

- 目标
  - 收尾 AI Assist formal owner
  - 列出 remaining exceptions ledger
  - 判断 AI Assist 是否具备 closeout 条件
- 涉及文件
  - `docs/refactor/ai-assist-closeout.md`
  - `docs/refactor/ai-assist-remaining-exceptions-ledger.md`
  - `docs/refactor/ai-assist-primitive-boundary.md`
  - `docs/refactor/wave5-closeout.md`
  - 如必要：`tests/test_refactor_guardrails.py`
- 不涉及文件
  - 不继续拆新的 customer pulse / followup 子模块
  - 不进入 Wave 6
- 风险
  - closeout 结论失真
  - guardrail 缺口导致 caller 回流
- 回滚方式
  - 回退 closeout 文档和最小 guardrail 改动
- 必跑测试
  - `tests/test_http_registration_contract.py`
  - `tests/test_refactor_guardrails.py`
  - `tests/test_admin_customer_profile_console.py`
  - `tests/test_customer_pulse_inbox.py`
  - `tests/test_customer_pulse_quality_gates.py`
  - `tests/test_followup_orchestrator_skeleton.py`
  - `tests/test_api.py -k "customer_pulse or followup_orchestrator"`

## 3. 为什么按这个顺序

### 3.1 先 formal owner，再切 caller

Wave 5 当前最大的问题不是内部实现本身，而是：

- controller 直连 domain 太多
- admin shell / customer profile 也在直接摸 pulse / followup helper
- `application/ai_assist/*` 还没有稳定 delegate seam

所以必须先把 formal owner 建起来，再切 caller。

### 3.2 pulse 先于 followup

原因：

- followup 当前直接把 customer pulse cards 当 mission source
- 不先把 pulse 的 formal query / command 稳住，followup caller cutover 就没有稳定依赖面

### 3.3 internal split 放在 caller cutover 之后

原因：

- Wave 5 的首要目标是 owner 收口，而不是先拆大文件
- 只有 caller 全部切走后，internal split 才不会和 controller change 混在同一个 PR

## 4. 本轮明确不做的事

- 不在 Wave 5 里顺手回收 `customer read model` 内部实现
- 不在 Wave 5 里深拆 `automation engine` agent runtime / workflow runtime
- 不进入 `questionnaire` / `user_ops` / `customer_pulse` 之外的其它 context
- 不做 schema / SQL migration

## 5. 结论

Wave 5 AI Assist 的正确推进顺序是：

1. formal application owner
2. customer pulse caller cutover
3. followup caller cutover
4. customer pulse internal split
5. followup internal split
6. closeout

只有按这个顺序，才能在不破坏 Wave 1–4 已完成成果的前提下，把 AI Assist 从 controller / domain mixed owner 拉回正式 `application/ai_assist/*`。
