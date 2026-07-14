# Epic #67 最终验收审计

审计日期：2026-07-13
Epic 基线：`0741a8e45c7b52c8dc5b184ea33e4ef5d2f8e9cd`
业务重构审计主线：`ca3e96c4cc2e633802bcc71d4b09a9fad0ae53aa`（PR #156 合并后）

## 结论

Epic #67 的业务、安全、数据、执行链、模块、迁移、CI、Readiness 和退役验收均有可执行证据。最终审计发现并修复了一个真实遗留缺口：GitHub Actions 仍使用可变 tag 和 Node 20 runtime。审计分支已升级到官方 Node 24 版本、固定 40 位 commit SHA，并新增 fail-closed 供应链门禁。

本审计不新增业务能力、路由、页面、表或外部调用。

## 最终验证快照

- PR #156 CI run `29222548685`：8 个 PostgreSQL 分片、架构、依赖、前端、性能和聚合检查全部通过；最慢 Python 分片 6 分 42 秒。
- PR #155 CI run `29222112643`：新增真实性能作业和 8 个 PostgreSQL 分片全部通过；最慢 Python 分片 6 分 47 秒。
- 本地独立 PostgreSQL 全量回归：`3165 passed, 5 skipped`，0 failed，1933.34 秒。
- import graph：40 contexts、168 cross-context edges、0 cyclic components、0 cyclic contexts。
- runtime module size：526 files、0 oversized、上限 1500 行。
- route/runtime inventory：672 routes、638 runtime Python files、0 boundary violations。
- retired runtime scanner：654 scanned files、5 retired artifact families、0 violations。
- 依赖锁、安全审计、PII、SQL、repository/table ownership、Alembic、空库 bootstrap、runtime inventory 全部门禁通过。
- R12-E/F/G 遗留 issue #127、#129、#131 已补齐 merge SHA 和最终门禁证据后关闭；所有 Epic 子 issue 均已关闭。

## RAUTH 私有化统一鉴权验收

| 验收项 | 证据 | 结果 |
|---|---|---|
| 没有独立 auth 服务或额外 runtime unit | `deploy/production_runtime_units.json`；`tests/test_runtime_units_autostart.py`；架构图 0 新服务 | 通过 |
| 企微人员登录、Session、RBAC、CSRF、即时吊销 | `tests/test_auth_platform_sessions.py`、`test_auth_platform_postgres_sessions.py`、`test_route_policy_enforcement.py`、`test_admin_auth_*` | 通过 |
| Agent client credentials 短期 JWT；只能创建 draft，审批/启动/发送 403 | `tests/test_auth_platform_client_authentication.py`、`test_ai_assist_external_campaigns.py`、`test_auth_platform_fastapi_protocol.py` | 通过 |
| Worker/Timer 不再维护多套共享静态 Bearer | `docs/architecture/auth_credential_inventory.yml`；`scripts/ci/check_auth_credential_boundaries.py` | 通过 |
| Handler/Repository 只消费 AuthContext，不读取原始凭据 | `scripts/ci/check_auth_credential_boundaries.py`；`tests/test_auth_platform_context.py` | 通过 |
| 旧 token env/query/fallback/重复 validator 引用为 0 | auth credential boundary gate、route policy manifest、runtime inventory | 通过 |
| JWT 错签名、错 audience、过期、停用、旧 auth_version、越权 scope 均拒绝 | `tests/test_auth_platform_credentials.py`、`test_auth_platform_service.py`、`test_auth_platform_client_authentication.py` | 通过 |
| Webhook 篡改、超时、重复 event_id、错误签名均拒绝 | `tests/test_auth_platform_webhook_hmac.py`、`test_auth_platform_webhook_routes.py` | 通过 |
| 供应商企微 OAuth、支付 callback 官方协议保留 | `tests/test_auth_wecom_real_flow.py`、`test_questionnaire_oauth_*`、`test_wechat_pay_*` | 通过 |
| PostgreSQL、前端、route policy、Alembic、inventory、PII、安全、架构全绿 | PR #156 CI run `29222548685`；本地 full gates | 通过 |
| 单 release 切换，不接受旧凭据 fallback；只允许整包 rollback | RAUTH migration/runbook、auth boundary gate、Exact-SHA deploy 与 rollback contract tests | 通过 |

## Epic 总体验收

| 验收项 | 证据 | 结果 |
|---|---|---|
| 不新增用户功能、页面、业务模块或产品指标 | route inventory 保持现有能力边界；本审计与各 R00-R15 PR 均为替换/收敛 | 通过 |
| 不引入新 Customer 360、Activity、分析、Note/Task、生命周期模型 | 从 Epic 基线到当前 main 的 migration 新增行无禁止模型；现存 `_customer_360_*` helper 在基线已存在，仅在 R12 机械拆分 | 通过 |
| 页面和 API contract 兼容 | 672-route ownership/policy/runtime inventory；全量 contract/E2E 回归 | 通过 |
| 全量测试为绿 | GitHub 8 分片全绿；本地 3165 passed | 通过 |
| 匿名敏感接口拒绝 | `tests/test_admin_routes_require_auth.py`、`test_route_policy_enforcement.py`、sidebar/questionnaire negative tests | 通过 |
| 后台写操作具备 capability 权限 | route policy manifest、`tools/check_admin_route_auth.py`、RBAC/CSRF tests | 通过 |
| unionid-first 在 schema/runtime/文档/测试一致 | `scripts/ci/check_unionid_identity_contract.py`、identity resolver PostgreSQL tests、0106 schema tests | 通过 |
| fake/simulated/blocked/unknown/accepted/succeeded 不混淆 | External Effect 状态机、`tests/test_external_effects_mvp.py`、delivery/reconciliation tests | 通过 |
| callback ACK 前无非必要外部调用 | `tests/test_p1_callback_threadpool_guard.py`、`test_r05_wecom_callback_architecture.py`、callback inbox tests | 通过 |
| 支付成功不漏权益；退款成功不残留权益 | payment/refund transactional outbox、consumer fault tests、reconciliation tests | 通过 |
| 同一业务事件无重复 planner | event/effect lineage、idempotency/lease tests、order reconciliation tests | 通过 |
| terminal/blocked 不自动重试 | `tests/test_internal_event_outbox.py`、`test_internal_events_worker_allowlist.py`、External Effect scheduler tests | 通过 |
| 跨上下文直接写表为 0 | repository ownership、DB access boundary、SQL static guard | 通过 |
| 空数据库可安装当前系统 | `scripts/ops/bootstrap_database.py`、`tests/test_database_bootstrap.py`、0106 fresh DB CI | 通过 |
| Python/npm 无未接受高危公告 | hashed `requirements.lock`、npm lock、dependency-audit | 通过 |
| 部署 SHA 等于验证 SHA，失败恢复 web/worker/timer | `tests/test_deploy_workflow_contract.py`、server lock/concurrency、rollback trap、readiness | 通过 |
| 无数据库时可做基本诊断 | `tools/check_live_runtime_readiness.py`、`tests/test_live_runtime_readiness.py` | 通过 |
| 兼容层、旧表、旧 worker 有 owner 和删除决定 | route/table lifecycle manifests、retired runtime registry、`retired_forbidden` runtime units | 通过 |

## Batch 退出条件

- Batch 0：行为清单、Route Policy、安全依赖和匿名接口负向门禁均已固化。
- Batch 1：unionid-first identity lookup/resolution/binding 与 sidebar/questionnaire owner scope 已收敛。
- Batch 2：callback durable ACK、outbox、consumer lease/CAS、Effect receipt/unknown/reconciliation 与 worker exit code 已收敛。
- Batch 3：支付、退款、权益、问卷、Group Ops、broadcast projection 均有事务、幂等、故障注入和对账证据。
- Batch 4：跨上下文写表为 0；runtime Python oversized 为 0；import SCC 为 0；前端 clean build 可复现；空库可安装。
- Batch 5：高风险路径强制 full CI；8 个平衡分片将主线等待降到约 7 分钟；Exact-SHA deploy、串行锁、回滚、真实 readiness、性能基线和退役 scanner 均已落地。

## 最终审计补丁：Actions 供应链

| Action | 固定版本 | 固定 SHA |
|---|---|---|
| `actions/checkout` | v7.0.0 / Node 24 | `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` |
| `actions/setup-python` | v6.3.0 / Node 24 | `ece7cb06caefa5fff74198d8649806c4678c61a1` |
| `actions/setup-node` | v6.4.0 / Node 24 | `48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e` |
| `actions/upload-artifact` | v7.0.1 / Node 24 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| `appleboy/scp-action` | v1.0.0 | `ff85246acaad7bdce478db94a363cd2bf7c90345` |
| `appleboy/ssh-action` | v1.2.5 | `0ff4204d59e8e51228ff73bce53f80d53301dee2` |

`scripts/ci/check_github_action_pins.py` 已加入 fast architecture gates：外部 Action 使用可变 tag、未知 Action、非 40 位 SHA 或未批准 SHA 时直接失败。

## 非阻断说明

测试仍会报告来自 FastAPI/Starlette 测试客户端和 PDF SWIG 绑定的上游 deprecation warning；它们不影响 Epic 的运行时、数据、安全或发布验收。Alembic `prepend_sys_path` 的旧分隔行为已在本审计补丁中显式设置 `path_separator = os`，不再依赖弃用 fallback。
