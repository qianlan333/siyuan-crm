# AI Assist Remaining Exceptions Ledger

日期：2026-04-22

## 非阻塞例外

### 1. `http/admin_customer_pulse.py` 仍直接依赖 `domains/customer_pulse/access.py`

- 为什么这次不拆
  - 这部分负责 request-scope tenant context、RBAC、evidence 权限与审计前置判断，属于 transport-access glue
- 类型
  - `bridge`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 如后续治理 AI Assist access layer，可抽出 `application/ai_assist` 下更稳定的 access query / adapter，而不是回退到 pulse domain service

### 2. `http/admin_customer_pulse.py` 仍直接读取部分 `domains/customer_pulse/repo.py`

- 为什么这次不拆
  - 这些读取主要用于 evidence / audit / resource lookup，不属于本轮 formal owner 收口的主读主写链
- 类型
  - `read`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 后续如继续治理 pulse evidence/read adapter，可把 repo 直读统一收入口径 query

### 3. `http/admin_followup_orchestrator.py` 仍复用 `domains/customer_pulse/access.py`

- 为什么这次不拆
  - followup 当前仍与 pulse 共用租户与 owner-scope 权限模型
- 类型
  - `bridge`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 若后续演进 shared access layer，可把 pulse/followup 共用 access payload 提升为稳定 adapter

### 4. `domains/admin_console/customer_profile_service.py` 仍保留 pulse / followup view-model glue

- 为什么这次不拆
  - 本轮目标是让 admin profile 不再作为 AI Assist read owner；页面 view-model 组装仍属于 admin console 的职责
- 类型
  - `bridge`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 若后续继续治理 admin profile 页面边界，可把页面 presenter / page adapter 继续独立

### 5. `domains/customer_pulse/service.py` 仍保留 shared helper / runtime glue

- 为什么这次不拆
  - 本轮已经拆出 signal / snapshot / read / action / feedback_metrics owner，继续深拆基础 glue 会超出 closeout 范围
- 类型
  - `shim`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 若后续继续做 pulse 内部治理，可按 `access` / `runtime` / `repo-presenter glue` 再下沉

### 6. `domains/followup_orchestrator/service.py` 仍保留 feature gate / policy / read-scope / utility glue

- 为什么这次不拆
  - PR 5 已经完成 mission sync / assignment / board / action helper owner 提升；继续拆 policy/runtime 会超出本轮最小范围
- 类型
  - `shim`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 后续如继续内部治理，可再把 `policy` / `read_scope` / `feature_gate` 抽成更稳定的 shared adapter

### 7. `domains/customer_pulse/ai_recommendation.py` 与 `domains/followup_orchestrator/ai_enhancement.py` 仍承担 provider/runtime 实现

- 为什么这次不拆
  - 本轮已经把 AI enhancement 边界 owner 建立好；provider/runtime 本身保持稳定更安全
- 类型
  - `maintenance`
- 是否阻塞 Wave 5 closeout
  - 否
- 后续归位建议
  - 若后续统一 AI provider adapter，可再考虑把 provider/mock/runtime 下沉到 infra

## 结论

上述例外都已被限制在 transport/access glue、compatibility facade、shared runtime helper 或 provider/runtime 范围内，不再阻塞 AI Assist / Wave 5 正式关单。
