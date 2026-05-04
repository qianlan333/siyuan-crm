# Customer Pulse SaaS Readiness Report

更新时间：2026-04-11
验收角色：外放前最终验收官 + 修复者
验收范围：Tenant Trust Layer for Customer Pulse

## 一句话结论

结论：可受限外放

前提：

- 仅限 `ai_customer_pulse` 开启的租户
- 对外租户仅允许 `CUSTOMER_PULSE_TENANT_MODE=request_scoped`
- 必须同时配置 rollout policy、tenant access policy、audit、metrics
- `legacy_internal` 仅保留给内部兼容链路，不对外暴露

这次验收确认的是：Customer Pulse 已经具备“多租户 SaaS 可控外放”的最小可信边界；但仓库整体仍不是全域多租户平台，因此不建议无约束全量放开。

## 本轮修复记录

### 1. 收件箱 1000 卡片场景性能回归修复

- 文件：
  - `wecom_ability_service/domains/customer_pulse/service.py`
- 修复：
  - 去掉重复的 `ai_customer_pulse` 设置查询，统一走 `_config_value()` / app config fallback
- 结果：
  - `tests/test_customer_pulse_quality_gates.py` 中 1000 卡片 inbox 查询预算恢复到门禁阈值内

### 2. build / seed / app import 循环依赖修复

- 文件：
  - `wecom_ability_service/domains/customer_pulse/__init__.py`
  - `wecom_ability_service/customer_center/__init__.py`
- 修复：
  - 把包级 eager import 改成 lazy `__getattr__`
- 结果：
  - `create_app`
  - `scripts/run_build.py`
  - `scripts/seed_customer_pulse_demo.py`
  - `make check`
  均恢复可执行

### 3. 全仓 pytest 日期脆弱用例修复

- 文件：
  - `tests/test_marketing_automation.py`
  - `tests/test_marketing_state_service.py`
- 修复：
  - 为 3 个依赖相对时间的用例补时间冻结，避免随着当前日期漂移误判为 `pool/silent`
- 结果：
  - 全仓 `pytest -q` 恢复稳定通过

## 实际执行命令

### 文档与实现核对

- 审阅：
  - `docs/ai-customer-pulse/04-tenant-auth-audit.md`
  - `docs/ai-customer-pulse/05-tenant-data-model.md`
  - `docs/ai-customer-pulse/06-rbac-matrix.md`
  - `docs/ai-customer-pulse/07-quality-gates.md`
  - `docs/ai-customer-pulse/08-external-rollout.md`
- 核对代码：
  - `wecom_ability_service/domains/customer_pulse/access.py`
  - `wecom_ability_service/domains/customer_pulse/repo.py`
  - `wecom_ability_service/domains/customer_pulse/service.py`
  - `wecom_ability_service/http/admin_customer_pulse.py`
  - `wecom_ability_service/customer_timeline/service.py`
  - `wecom_ability_service/customer_timeline/repo.py`
  - `wecom_ability_service/domains/admin_console/customer_profile_service.py`
  - `wecom_ability_service/domains/admin_dashboard/service.py`

### 质量门与回归

- `./.venv310/bin/python -m pytest -q`
  - 结果：`606 passed in 294.34s (0:04:54)`
- `make check`
  - 结果：通过
  - 覆盖：
    - `scripts/run_lint.py`
    - `scripts/run_typecheck.py`
    - `scripts/run_build.py`
    - `pytest -q tests/test_customer_pulse_inbox.py`
    - `pytest -q tests/test_customer_pulse_quality_gates.py`

### 双 tenant fixture / demo

- `./.venv310/bin/python scripts/seed_customer_pulse_demo.py --database-path <tmp> --init-db --write-settings --dual-tenant`
  - 结果：通过
  - 生成租户：
    - `tenant-alpha`
    - `tenant-beta`
  - 生成示例客户：
    - `wm_pulse_demo_tenant_a_reply`
    - `wm_pulse_demo_tenant_a_stalled`
    - `wm_pulse_demo_tenant_b_risk`
    - `wm_pulse_demo_tenant_b_reminder`

## 核心场景验收

### 1. tenant_a 只能看到 tenant_a 的 inbox / list / detail

- 结果：PASS
- 验证：
  - `test_customer_pulse_cross_tenant_card_detail_and_action_writeback_are_denied`
  - `test_customer_pulse_request_scoped_normal_request_exposes_tenant_context`

### 2. tenant_a 无法打开 tenant_b 的 card / detail / evidence

- 结果：PASS
- 验证：
  - cross-tenant card detail / preview / execute 返回 `404`
  - cross-tenant customer detail 返回 `has_card=false`
  - cross-tenant timeline 不返回对方 tenant activity

### 3. tenant_a 无法执行 tenant_b 的 draft / task / stage / tag / reminder action

- 结果：PASS
- 验证：
  - cross-tenant execute 返回 `404`
  - `customer_pulse_execution_logs` 不产生错误 tenant 写入

### 4. 有页面权限但无 evidence 权限时，卡片可见但 evidence 不可见

- 结果：PASS
- 验证：
  - `test_customer_pulse_card_view_without_evidence_permission_cannot_expand_evidence`
  - detail 中保留安全 `evidence_refs`
  - evidence 展开接口返回 `403`
  - 审计日志写入 `deny_card_evidence`
  - `access_denied` metric 增长

### 5. 有查看权限无执行权限时，按钮不可用且接口拒绝

- 结果：PASS
- 验证：
  - `test_customer_pulse_view_only_role_can_read_card_but_cannot_preview_or_execute`
  - detail payload 中 `supported_action_buttons=[]`
  - `draft_editor_available=false`
  - preview / execute 返回 `action_permission_denied`

### 6. legacy internal mode 仍可走通单租户管理台路径

- 结果：PASS
- 验证：
  - `test_customer_pulse_legacy_internal_mode_request_is_explicitly_marked`
  - payload 中显式返回：
    - `auth_mode=legacy_internal`
    - `legacy_mode=true`

### 7. action 执行后的 writeback 和 execution_log 绑定到正确 tenant

- 结果：PASS
- 验证：
  - `test_customer_pulse_cross_tenant_customer_detail_and_timeline_hide_other_tenant_evidence`
  - `test_customer_pulse_repo_tenant_filters_block_cross_tenant_snapshot_and_log_reads`
  - timeline / activity / feedback / execution_log 均按 `tenant_key` 读写

### 8. 1000 张卡片场景没有新的 N+1 或明显性能退化

- 结果：PASS
- 验证：
  - `test_customer_pulse_quality_gates_handle_bulk_multi_tenant_workloads`
  - 断言阈值：
    - tenant A inbox：1000 张卡，`query_count <= 12`，`elapsed_ms < 2500`
    - detail：`query_count <= 8`，`elapsed_ms < 1200`
    - evidence：`query_count <= 6`，`elapsed_ms < 1200`
    - tenant B inbox：`query_count <= 6`，`elapsed_ms < 1200`

## A-L 验收矩阵

| 项 | 结论 | 说明 |
| --- | --- | --- |
| A | PASS | `04-08` 文档存在，且与 access / repo / service / http / tests 当前实现一致 |
| B | PASS | Customer Pulse 读写链路已显式支持 request-scoped tenant context；无 tenant / 非法 tenant / tenant 冲突均有明确错误 |
| C | PASS | `legacy_internal` 仍可运行，且 payload / 日志中可明确区分 |
| D | PASS | list / detail / evidence / action executor / execution log / timeline writeback 全部 tenant-scoped |
| E | PASS | 页面级和动作级 RBAC 已同时在前后端生效 |
| F | PASS | `evidenceRefs` 仅返回安全字段；越权 evidence 展开被拒绝；无原始未授权文本泄露 |
| G | PASS | 审计日志与执行日志可追踪 tenant、actor、resource、action、result |
| H | PASS | lint / typecheck / build / pytest / e2e/perf 都有真实可执行命令，并在当前仓库跑通 |
| I | PASS | 已实际构造并验证双 tenant fixture，不是只测单租户 |
| J | PASS | 1000 卡片场景下 perf 门禁通过，未见新的 N+1 |
| K | PASS | 全仓 `pytest` 通过，未观察到对收件箱、widget、草稿、任务、阶段/标签、提醒、反馈、埋点的回归破坏 |
| L | PASS | 在“仅限 Customer Pulse 边界、request-scoped、feature-flag 灰度”的前提下，达到多租户 SaaS 外放最低标准 |

## 文档与实现一致性结论

### 04-tenant-auth-audit

- 一致
- 当前实现确实是 `customer_pulse_access_context` 驱动的 tenant-aware island，而不是全仓统一 tenant middleware

### 05-tenant-data-model

- 一致
- `customer_pulse_signal_events`
- `customer_pulse_snapshots`
- `customer_pulse_cards`
- `customer_pulse_feedback_logs`
- `customer_pulse_execution_logs`
- `customer_pulse_activity_logs`
- `customer_pulse_action_feedback`
  均已落 tenant-scoped 读写约束

### 06-rbac-matrix

- 一致
- 页面、列表、widget、evidence、动作、反馈的 capability 已在接口与页面层落地

### 07-quality-gates

- 一致
- `make check` 与 `scripts/run_customer_pulse_quality_gates.py` 当前可真实执行

### 08-external-rollout

- 一致
- 现有实现确实支持全局开关、tenant 灰度、role/user 细分放量、stats API 监控口径和 dual-tenant seed

## 剩余风险

### 1. 仓库整体仍是“Customer Pulse 租户可信孤岛”

- Customer Pulse 已 tenant-scoped
- 但仓库很多其他 CRM / customer / marketing / automation 路径仍保留单租户或全局事实表假设
- 结论：
  - 当前适合外放 Customer Pulse
  - 不等于整个后台已经完成平台级多租户改造

### 2. typecheck 仍是最小覆盖而非全域强约束

- `customer_pulse/service.py`
- `customer_pulse/repo.py`
  这两条动态路径仍主要依赖 compile/build/pytest/perf 兜底，而不是完整 `mypy` 强门禁

### 3. 监控是“最小可用”，不是完整运维系统

- 当前已有 stats API 与 metrics 落库
- 但真正的持续告警仍依赖外部拉取和接入，不是仓库内建的完整告警编排

### 4. `legacy_internal` 必须继续限制在内部环境

- 它用于兼容单租户后台路径
- 对外 SaaS 环境若放开 `legacy_internal`，会削弱 request-scoped tenant trust layer 的边界清晰度

## 上线建议

建议按以下边界外放：

1. 仅对明确配置 tenant policy 的租户开启
2. 对外环境强制 `request_scoped`，禁止 `legacy_internal`
3. 先放开只读能力：
   - page
   - inbox
   - widget
   - evidence
4. 再逐步放开动作能力：
   - draft
   - task
   - segment/tag
   - reminder
5. 每个新租户先跑 dual-tenant smoke 与 stats API 验证

## 最终结论

结论：可受限外放

理由：

- Tenant Trust Layer for Customer Pulse 已形成闭环：
  - request-scoped tenant context
  - tenant-scoped data access
  - page/action/evidence RBAC
  - audit / metrics / writeback traceability
  - quality gates
  - dual-tenant validation
  - bulk perf baseline
- 但仓库整体仍不是全域多租户平台，当前最稳妥的发布策略应是“限定在 Customer Pulse 边界内、按 tenant/role/user 灰度外放”，而不是无约束全量开放。
