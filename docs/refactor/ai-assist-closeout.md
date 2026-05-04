# AI Assist Closeout

日期：2026-04-22

## 正式结论

Wave 5 的目标是把 AI Assist 从 legacy `domains/customer_pulse/*`、`domains/followup_orchestrator/*`、`domains/admin_console/customer_profile_service.py` 与对应 admin caller 的直连 owner，收口到正式 `wecom_ability_service/application/ai_assist/*`，并完成第一轮内部 owner 拆分。

当前仓库状态已经满足这个目标。`application/ai_assist/*` 已成为正式 owner，primary caller 已切走 legacy domain 主入口，`customer_pulse` 与 `followup_orchestrator` 也已经完成第一轮内部子模块收口。

正式结论：`ai_assist` 已 completed and closed。

## 已完成的主线

### 1. customer pulse caller cutover

- 当前 owner 文件
  - `wecom_ability_service/application/ai_assist/queries.py`
  - `wecom_ability_service/application/ai_assist/commands.py`
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- 当前结果
  - pulse inbox / detail / metrics / card action preview / execute 已统一经 `application/ai_assist/*`
  - admin customer profile 中 pulse 相关读取已经不再把 `domains/customer_pulse/service.py` 当默认入口
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/customer_pulse/service.py` 仍保留 public facade
  - `wecom_ability_service/domains/customer_pulse/__init__.py` 仍保留 compatibility export surface
- 已知技术债
  - `http/admin_customer_pulse.py` 仍直接使用 `domains/customer_pulse/access.py` 和部分 repo read 做权限/evidence glue
  - 这些属于 transport 或 same-context read glue，不阻塞 Wave 5 closeout

### 2. followup caller cutover

- 当前 owner 文件
  - `wecom_ability_service/application/ai_assist/queries.py`
  - `wecom_ability_service/application/ai_assist/commands.py`
  - `wecom_ability_service/http/admin_followup_orchestrator.py`
- 当前结果
  - followup overview / customer / my missions / team board / mission detail 已统一走 application query
  - mission preview / execute / undo / assignment 类动作已统一走 application command
  - `http/admin_followup_orchestrator.py` 不再以 `domains/followup_orchestrator/service.py` 为直接 owner
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/followup_orchestrator/service.py` 仍保留 public facade
  - `wecom_ability_service/domains/followup_orchestrator/__init__.py` 仍保留 compatibility export surface
- 已知技术债
  - `http/admin_followup_orchestrator.py` 仍复用 `domains/customer_pulse/access.py` 做租户/权限上下文 glue
  - 这是当前 AI Assist 与 Customer Pulse 共享 access layer 的现状，不阻塞 closeout

### 3. customer pulse internal split

- 当前 owner 文件
  - `wecom_ability_service/domains/customer_pulse/customer_pulse_signal_service.py`
  - `wecom_ability_service/domains/customer_pulse/customer_pulse_snapshot_service.py`
  - `wecom_ability_service/domains/customer_pulse/customer_pulse_read_service.py`
  - `wecom_ability_service/domains/customer_pulse/customer_pulse_action_service.py`
  - `wecom_ability_service/domains/customer_pulse/customer_pulse_feedback_metrics_service.py`
- 当前结果
  - signal build、snapshot materialize、read projection、action execution、feedback/metrics 已经各有清晰内部 owner
  - `domains/customer_pulse/service.py` 不再承担 pulse 主读主写入口，而是退成 facade + shared runtime glue
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/customer_pulse/service.py`
  - `wecom_ability_service/domains/customer_pulse/__init__.py`
- 已知技术债
  - `service.py` 仍保留 config/access/runtime/repo glue 和部分 shared helper
  - `ai_recommendation.py` 仍是 provider/runtime 实现，没有继续深拆

### 4. followup internal split

- 当前 owner 文件
  - `wecom_ability_service/domains/followup_orchestrator/followup_mission_read_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/followup_mission_action_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/followup_ai_enhancement_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/mission_sync_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/mission_assignment_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/mission_board_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/mission_action_service.py`
  - `wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py`
- 当前结果
  - mission read owner、mission action owner、AI enhancement owner 已明确
  - mission sync / assignment / board / action 的 shared helper 也已经从超大 `service.py` 中抽出独立 owner
  - `domains/followup_orchestrator/service.py` 已退成 facade + delegate seam
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/followup_orchestrator/service.py`
  - `wecom_ability_service/domains/followup_orchestrator/__init__.py`
- 已知技术债
  - `service.py` 仍保留 feature gate、policy、access/read-scope 和基础 utility
  - `ai_enhancement.py` 仍承担 provider/runtime 实现

## `services.py` 当前定位

- 本轮没有新增 AI Assist 的 `services.py` formal shim
- 当前状态
  - AI Assist 主线并不依赖 `services.py` 作为主要兼容入口
  - `services.py` 没有重新成为 AI Assist 的默认 owner
- 结论
  - AI Assist 的 formal owner 已稳定落在 `application/ai_assist/*`

## Closeout 判断

从 formal owner、primary caller cutover、内部 owner 第一轮拆分、compatibility control 和关键回归五个维度看，AI Assist 已达到本轮正式 closeout 条件。

正式结论：`ai_assist` 已 completed and closed。
