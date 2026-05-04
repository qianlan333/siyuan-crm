# AI Customer Pulse Inbox 验收报告

验收时间：2026-04-11
验收角色：严苛验收官 + 修复者
验收范围：A-L 全量项，含实际运行、场景模拟、写回检查、回归与修复

> 更新说明（2026-04-11）
> 本文最初记录的是“可灰度上线”版本的 A-L 验收结果。
> 随后的外放加固已经补入 request-scoped tenant boundary、deny-by-default 权限收口、tenant-aware 作业/存储和可执行质量门。
> 当前对外上线口径以 [03-rollout.md](/Users/qianlan/Downloads/aicrm-new-codex-1/docs/ai-customer-pulse/03-rollout.md) 为准。

## 最终结论

结论：可上线，推荐按双模式推进。

- `legacy_internal`
  - 继续兼容当前单租户后台管理台。
- `request_scoped`
  - 对外 SaaS 场景使用；Customer Pulse 读写链路要求显式 tenant context 和 actor context，并默认拒绝无 tenant、无权限、跨 owner、越权 evidence 访问。

当前版本已经满足：

- `ai_customer_pulse` feature flag 控制
- 基于真实表数据与 fixture/seed 的行动卡生成
- `whyNow + evidenceRefs` 证据链
- 草稿 / 任务 / 阶段/标签 / 提醒 4 类动作
- 外发消息仅生成草稿，不默认发送
- 执行写回 timeline / activity / 本地跟进状态
- 反馈学习与埋点落库
- 幂等、错误处理、撤销窗口
- request-scoped tenant boundary 与 tenant-aware recompute job
- 页面/API 动作级权限收口与后台审计
- 可执行的 lint / typecheck / build / test 门禁
- 全量回归、e2e、构建检查通过

保留风险：

- `request_scoped` 依赖外围入口稳定传递 tenant/actor 头；若接入层丢头，Customer Pulse 会按预期拒绝访问
- 当前 RBAC 仍是基于 tenant policy + 角色 allowlist + owner scope 的收口模型，不是全仓库统一 ABAC 引擎

## 修复记录

本轮验收中发现并已修复：

1. 卡片对外接口主要暴露 `evidence`，未稳定暴露 `evidenceRefs`
- 修复：在卡片 payload 中新增 `evidence_refs` / `evidenceRefs`
- 规则卡片优先从 AI `evidenceRefs` 透出；无 AI 时回退为 snapshot signals 的 `source_ref_type/source_ref_id`

2. 收件箱列表存在明显 snapshot N+1
- 现象：`build_customer_pulse_inbox_payload()` 中列表每张卡都会再次查询一次 snapshot
- 修复：新增 snapshot 批量读取并在列表构建阶段复用

3. 设计/审计文档与当前实现存在口径漂移
- 修复：在 `01-current-audit.md` 标明其为开发前基线；更新 `02-design.md` / `03-rollout.md` 的实际实现状态与回归命令

4. 缺少直接覆盖 `evidenceRefs`、widget 一致性、权限拦截的回归用例
- 修复：补充 Customer Pulse 集成测试

5. Customer Pulse 读写链路仍停留在单租户默认上下文
- 修复：新增 `CUSTOMER_PULSE_TENANT_MODE`、`CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`，并将页面、API、repo、作业、日志全链路切到 tenant-aware

6. 缺少可执行 lint / typecheck / build 质量门
- 修复：新增 `pyproject.toml`、`scripts/run_lint.py`、`scripts/run_typecheck.py`、`scripts/run_build.py` 和 `Makefile`

## A-L 验收结果

| 项 | 结果 | 结论 |
| --- | --- | --- |
| A. 文档存在且与实现一致 | PASS | `01/02/03` 均存在；已补“基线审计”说明和实现状态更新 |
| B. `ai_customer_pulse` feature flag 生效 | PASS | flag 关闭时页面占位；开启后导航、页面、API 生效 |
| C. 行动卡来自真实/fixture 数据 | PASS | 基于 `archived_messages`、`customer_marketing_state_current`、`customer_value_segment_current`、`automation_reply_monitor_queue`、`contact_tags` 等表生成 |
| D. 每张卡都有 `whyNow + evidenceRefs` | PASS | 本轮已补对外 `evidenceRefs` 暴露，并新增回归测试 |
| E. 4 类 action 支持 | PASS | 草稿、任务、阶段/标签更新、提醒均已实跑与测试 |
| F. 外发消息先预览确认 | PASS | `generate_reply_draft` 仅写 `outbound_tasks(draft_only=1)`，无默认发送 |
| G. 执行后自动回写 timeline/activity/follow-up | PASS | `customer_pulse_activity_logs`、timeline 聚合、卡片状态/提醒已写回 |
| H. 反馈与埋点落库正常 | PASS | `customer_pulse_action_feedback`、`customer_pulse_metric_events` 已验证 |
| I. 权限、租户隔离、幂等、错误处理 | PASS | `request_scoped` 下无 tenant、无 actor、跨 owner、角色不匹配统一 403；写接口继续要求 action token，internal API 继续要求 bearer token；幂等和错误处理成立 |
| J. lint / typecheck / unit test / build / e2e | PASS | 已新增 `make lint`、`make typecheck`、`make build`、`make test-customer-pulse`、`make check`，并实际跑通 |
| K. 不破坏现有主流程 | PASS | 全量回归 `581 passed`，客户详情、任务、会话、转化等既有链路未回归 |
| L. 无明显 N+1 / 性能 / 敏感数据泄漏 | PASS | 已修掉收件箱 snapshot N+1；AI 上下文仍有限窗与 PII mask；未发现新的明显泄漏面 |

## 场景验收

以下场景均已通过 fixture / integration tests 实跑：

1. 高意向客户 24h 未回复，生成会话草稿
- 结果：PASS
- 证据：`test_customer_pulse_reply_draft_execution_writes_draft_timeline_and_supports_undo`

2. 商机近似体/推进阶段停滞，建议创建任务
- 结果：PASS
- 证据：`test_customer_pulse_followup_task_execution_is_idempotent_and_reminder_is_undoable`

3. 客户缺少下次跟进时间，建议设置提醒
- 结果：PASS
- 证据：`test_customer_pulse_followup_task_execution_is_idempotent_and_reminder_is_undoable`

4. 聊天/跟进后建议更新阶段或标签
- 结果：PASS
- 证据：`test_customer_pulse_segment_and_tag_execution_support_retry_and_undo`

5. 客户详情页 AI widget 与收件箱数据一致
- 结果：PASS
- 证据：`test_customer_pulse_customer_widget_payload_matches_inbox_card`

6. 无权限用户看不到或不能执行相关 action
- 结果：PASS
- 证据：`test_customer_pulse_permission_controls_block_execute_without_action_token`、`test_customer_pulse_request_scoped_mode_requires_tenant_context`、`test_customer_pulse_request_scoped_sales_scope_and_cross_owner_action_denied`
- 说明：当前仓库对写操作继续采用 action token / internal bearer token；`request_scoped` 下读页、详情、internal API 还额外要求 tenant policy + actor scope

## 写回与落库检查

已实际验证：

- `customer_pulse_execution_logs`
  - 记录 action type、request/result payload、idempotency key、undo window、错误信息
- `customer_pulse_activity_logs`
  - 记录草稿、任务、阶段变更、标签变更、提醒、撤销等活动
- `customer_timeline`
  - 已聚合 `customer_pulse_activity_logs`
- `customer_pulse_action_feedback`
  - 已记录 `adopted`、`edited_then_sent`、`ignored`、`misjudged`、`unhelpful`
- `customer_pulse_metric_events`
  - 已记录曝光、点击、草稿确认、任务创建、阶段更新、忽略、AI 错误、写回成功/失败

## 实际执行命令

```bash
make lint
make typecheck
make build
make test-customer-pulse
make check
./.venv310/bin/python -m compileall wecom_ability_service tests scripts
./.venv310/bin/python scripts/seed_customer_pulse_demo.py --database-path /tmp/customer-pulse-acceptance.sqlite3 --init-db --write-settings
./.venv310/bin/python -m pytest -q tests/test_customer_pulse_inbox.py
./.venv310/bin/python -m pytest -q tests/test_customer_pulse_inbox.py -k "reply_draft_execution or followup_task_execution or segment_and_tag_execution or card_exposes or widget_payload_matches or permission_controls"
./.venv310/bin/python -m pytest -q tests/test_admin_customer_profile_console.py tests/test_api.py::test_customer_center_detail_customer_pulse_falls_back_to_rule_suggestion_when_ai_confidence_is_low
./.venv310/bin/python -m pytest -q -k e2e
./.venv310/bin/python -m pytest -q
```

执行结果：

- `compileall`：通过
- demo seed：通过，可重复执行
- Customer Pulse 场景集成测试：通过
- 客户详情 / API 回归：通过
- e2e：`1 passed`
- full suite：`581 passed in 287.13s`
- `make lint`：通过
- `make typecheck`：通过
- `make build`：通过
- `make test-customer-pulse`：`23 passed`
- `make check`：通过

## 剩余风险

1. `request_scoped` 模式依赖外围网关或页面容器稳定透传 tenant/actor 头；如果接入链路不规范，访问会被拒绝
2. 当前 RBAC 已收敛到 Customer Pulse 域内，但还没有推广成全仓库统一的细粒度权限框架
3. 埋点目前先落库，尚未接外部 BI/时序平台
4. `edited_then_sent` 在当前 MVP 中对草稿动作表示“改写后保存草稿”，不是最终外发回执

## 是否可上线

建议：可以上线。

上线建议边界：

- 继续通过 `ai_customer_pulse=true` 按环境、租户、角色分批开启
- 继续保持“只生成草稿，不默认发送”
- 现有管理台使用 `legacy_internal`
- 对外 SaaS 租户使用 `request_scoped` + `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`
- 先用 `03-rollout.md` 中的监控口径观察曝光、点击、草稿确认和写回成功率
- 若后续要扩大到更多租户，优先完善接入层 tenant/actor 透传与统一权限平台
