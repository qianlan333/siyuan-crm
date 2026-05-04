# Customer Pulse Quality Gates

更新时间：2026-04-11

## 目标

在不引爆全仓的前提下，为 `customer_pulse` 相关改动建立最小但真实可执行的质量门，并把 lint / typecheck / build / pytest / 性能基线接入统一入口与 CI。

## 当前门禁入口

### 统一入口

- `python scripts/run_customer_pulse_quality_gates.py`
- `make check`

统一脚本顺序：

1. `scripts/run_lint.py`
2. `scripts/run_typecheck.py`
3. `scripts/run_build.py`
4. `pytest -q tests/test_customer_pulse_inbox.py`
5. `pytest -q tests/test_customer_pulse_quality_gates.py`

### CI

- `.github/workflows/ci.yml`
- Job 名称：`customer-pulse-quality`
- 安装：`pip install -r requirements.txt ruff mypy`
- 执行：`python scripts/run_customer_pulse_quality_gates.py`

## 覆盖范围

### Lint

`ruff` 当前覆盖：

- `wecom_ability_service/domains/customer_pulse/`
- `wecom_ability_service/db.py`
- `wecom_ability_service/infra/settings.py`
- `wecom_ability_service/domains/admin_config/service.py`
- `wecom_ability_service/domains/admin_dashboard/service.py`
- `wecom_ability_service/http/admin_customer_pulse.py`
- `wecom_ability_service/http/admin_console.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- `wecom_ability_service/http/admin_customers.py`
- `scripts/run_lint.py`
- `scripts/run_typecheck.py`
- `scripts/run_build.py`
- `scripts/run_customer_pulse_quality_gates.py`
- `scripts/seed_customer_pulse_demo.py`
- `tests/test_customer_pulse_inbox.py`
- `tests/test_customer_pulse_quality_gates.py`

额外自定义文本检查覆盖：

- `wecom_ability_service/`
- `tests/`
- `scripts/`
- `docs/ai-customer-pulse/`

检查项：

- Python 语法/pyflakes 错误
- merge marker
- trailing whitespace
- 关键源码中的 tab 字符

### Typecheck

`mypy` 当前覆盖的是可稳定维护的边界层与门禁脚本：

- `wecom_ability_service/domains/customer_pulse/access.py`
- `wecom_ability_service/domains/customer_pulse/ai_recommendation.py`
- `wecom_ability_service/http/admin_customer_pulse.py`
- `wecom_ability_service/http/admin_console.py`
- `wecom_ability_service/domains/admin_dashboard/service.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- `wecom_ability_service/http/admin_customers.py`
- `wecom_ability_service/domains/admin_config/service.py`
- `wecom_ability_service/infra/settings.py`
- `scripts/run_lint.py`
- `scripts/run_typecheck.py`
- `scripts/run_build.py`
- `scripts/run_customer_pulse_quality_gates.py`
- `scripts/seed_customer_pulse_demo.py`
- `tests/test_customer_pulse_inbox.py`
- `tests/test_customer_pulse_quality_gates.py`

说明：

- `customer_pulse/service.py` 与 `customer_pulse/repo.py` 仍是动态风格较重的路径，当前不纳入 `mypy` 硬门禁
- 这两条核心路径改由 `py_compile + build smoke + pytest + perf baseline` 兜底

### Build / Smoke

`scripts/run_build.py` 当前执行：

- `compileall`：`wecom_ability_service/`、`tests/`、`scripts/`
- Flask app create/import smoke
- SQLite `init_db()` smoke
- `GET /admin/customer-pulse`
- `GET /api/admin/customer-pulse`
- `GET /api/admin/customer-pulse/stats`
- `GET /api/internal/customer-pulse/inbox`（带 internal token）
- `GET /api/internal/customer-pulse/stats`（带 internal token）

### E2E / Integration

- `tests/test_customer_pulse_inbox.py`

覆盖内容：

- AI 推荐、rule-based fallback、evidenceRefs
- 4 类 action 执行与撤销
- 写回 timeline / activity / follow-up
- request-scoped tenant
- feature gate rollout policy（global / tenant / role）
- RBAC
- 审计、反馈、metric、guardrail
- ops stats API 与跨租户 / 越权安全计数

### 性能与查询基线

- `tests/test_customer_pulse_quality_gates.py`

带量场景：

- tenant A：`1000` 张 action cards
- tenant B：`260` 张 action cards
- 两个 tenant 共存，且包含同一个 `external_userid`

当前基线断言：

- 列表页数据构建：`<= 12` 条 SQL，`< 2500ms`
- 卡片详情：`<= 8` 条 SQL，`< 1200ms`
- evidence 展开：`<= 6` 条 SQL，`< 1200ms`
- 次租户列表：`<= 6` 条 SQL，`< 1200ms`

说明：

- 列表页基线包含真实 exposure metric 写入
- 当前已将 `card_exposed` 从逐卡写入改为批量写入，避免列表页再次出现埋点型 N+1
- 基线以 `service` 真实读写路径为准，不依赖 mock repository

## 当前未覆盖项

- 全仓 lint / typecheck / build 仍未统一纳入；本次只对 `customer_pulse` 及直接依赖路径设门
- `customer_pulse/service.py`、`customer_pulse/repo.py` 还没有进入 `mypy` 硬门禁
- 浏览器级前端 e2e 还没有独立 runner；当前以 Flask test client 的集成流作为最小 e2e
- PostgreSQL 真机性能基线尚未单独建立；当前 perf test 基于 SQLite

## 推荐使用方式

本地开发：

```bash
make check
```

只跑 perf / query baseline：

```bash
./.venv310/bin/python -m pytest -q tests/test_customer_pulse_quality_gates.py
```

只跑 customer pulse 主回归：

```bash
./.venv310/bin/python -m pytest -q tests/test_customer_pulse_inbox.py
```
