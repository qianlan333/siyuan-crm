# Wave 5 Closeout

日期：2026-04-22

## 正式判断

Wave 5 的目标是让 AI Assist 从 legacy `domains/customer_pulse/*`、`domains/followup_orchestrator/*`、`domains/admin_console/customer_profile_service.py` 与对应 admin HTTP caller 的直连 owner，收口到正式 `wecom_ability_service/application/ai_assist/*`，并完成第一轮内部 owner 拆分。

当前仓库状态已经满足这个目标。

正式结论：Wave 5 已 completed and closed。

## 主线验收结果

| 主线 | formal application API 是否已建立 | primary caller 是否已切走 legacy domain 主入口 | `services.py` 是否已不再承担主要入口 | guardrail / contract 是否已覆盖 | 结论 |
| --- | --- | --- | --- | --- | --- |
| AI Assist application owner | 是，`wecom_ability_service/application/ai_assist/{queries,commands,dto,_legacy_delegate}.py` 已建立 | 是 | 是，AI Assist 主线不依赖 `services.py` 做 formal owner | 是，`tests/test_ai_assist_application_contract.py` 与 `tests/test_refactor_guardrails.py` 已覆盖 | 通过 |
| customer pulse caller cutover | 是 | 是，`http/admin_customer_pulse.py` 与 `domains/admin_console/customer_profile_service.py` 已切到 `application/ai_assist/*` | 是 | 是，registration / profile / pulse 相关回归已覆盖 | 通过 |
| followup caller cutover | 是 | 是，`http/admin_followup_orchestrator.py` 已切到 `application/ai_assist/*` | 是 | 是，followup skeleton 与 guardrail 已覆盖 | 通过 |
| customer pulse internal split | formal owner 不变，内部 owner 已拆出 | caller 无需感知内部模块变化 | 是 | 是，pulse 行为回归已覆盖 | 通过 |
| followup internal split | formal owner 不变，内部 owner 已拆出 | caller 无需感知内部模块变化 | 是 | 是，followup 行为回归已覆盖 | 通过 |

## 最终通过的测试结果

以下为 Wave 5 PR 1–PR 5 期间最终通过、用于关单判断的回归结果汇总：

- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_ai_assist_application_contract.py -q`
  - `3 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_service_layer_layout.py -q`
  - `8 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_http_registration_contract.py -q`
  - `5 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_refactor_guardrails.py -q`
  - `12 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_admin_customer_profile_console.py -q`
  - `8 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_customer_pulse_quality_gates.py -q`
  - `1 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_customer_pulse_inbox.py -q`
  - `45 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_followup_orchestrator_skeleton.py -q`
  - `13 passed`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_api.py -k "customer_pulse" -q`
  - `1 passed, 116 deselected`
- `PYTHONPATH=. ./.venv311/bin/pytest tests/test_api.py -k "followup_orchestrator" -q`
  - `117 deselected`
  - 说明：当前仓库没有单独命名为 `followup_orchestrator` 的 `tests/test_api.py` 子集，这不是失败 gate；followup 行为冻结由 `tests/test_followup_orchestrator_skeleton.py` 承担

## 仍保留的非阻塞例外

- `http/admin_customer_pulse.py` 仍直接依赖 `domains/customer_pulse/access.py` 与部分 repo read
- `http/admin_followup_orchestrator.py` 仍复用 `domains/customer_pulse/access.py`
- `domains/admin_console/customer_profile_service.py` 仍保留 pulse / followup view-model glue
- `domains/customer_pulse/service.py` 仍保留 shared helper / runtime glue
- `domains/followup_orchestrator/service.py` 仍保留 feature gate / policy / read-scope / utility glue
- `domains/customer_pulse/ai_recommendation.py` 与 `domains/followup_orchestrator/ai_enhancement.py` 仍承担 provider/runtime 实现

这些都不再阻塞 Wave 5 正式关单。详见：

- `docs/refactor/ai-assist-closeout.md`
- `docs/refactor/ai-assist-remaining-exceptions-ledger.md`
- `docs/refactor/ai-assist-primitive-boundary.md`

## Wave 5 关单结论

Wave 5 的 formal owner、primary caller cutover、internal owner 第一轮拆分、compatibility control 和关键回归都已经到位。

因此，Wave 5 已 completed and closed。
