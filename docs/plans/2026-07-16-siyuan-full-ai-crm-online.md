# Siyuan Full AI-CRM Online Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将思媛仓库同步到 AI-CRM 最新主线，并补齐生产运行时、企微执行门禁、积压消费和端到端验收。

**Architecture:** 业务代码使用 `08aec40f..f38339f6` 上游增量，保留思媛身份/域名 overlay；生产 worker 使用 AI-CRM 主线 runtime manifest，通过思媛现有 merge-to-production workflow 安装和校验。未批准外呼保持 blocked，已批准企微效果类型显式 allowlist。

**Tech Stack:** FastAPI、PostgreSQL、Alembic、systemd、GitHub Actions、pytest、Node frontend contract tests。

---

### Task 1: 同步最新 AI-CRM 业务增量

**Files:**
- Modify/Create: `aicrm_next/service_period/**`
- Modify/Create: `aicrm_next/admin_config/**`
- Modify/Create: `aicrm_next/platform_foundation/auth_platform/**`
- Modify: `aicrm_next/main.py`
- Create: `migrations/versions/0121_service_period_member_grid_sharing.py`
- Modify/Create: `tests/test_service_period_*.py`
- Create: `tests/frontend/service_period_member_grid_sharing.test.mjs`

**Steps:**

1. 应用 `git diff --binary 08aec40f..aicrm/main`，保留思媛 verification route 和迁移 overlay。
2. 检查 route inventory、repository ownership 和 Alembic head 是否仍一致。
3. 运行 service-period 后端与前端合同测试。

### Task 2: 同步 AI-CRM 生产运行时清单

**Files:**
- Replace: `deploy/**`
- Modify: `scripts/ops/manage_production_runtime_units.py`
- Modify: `.github/workflows/deploy.yml`
- Modify: `.github/workflows/ci-fast.yml`
- Modify: `tests/test_active_deploy_services_next_native.py`
- Modify: `tests/test_runtime_units_autostart.py`
- Modify: `tests/test_deploy_workflow_contract.py`
- Modify: `tests/test_ci_workflow_contract.py`

**Steps:**

1. 让 `deploy/` 与 AI-CRM 主线 runtime units/manifest 一致，删除已退休的旧嵌套单元。
2. 在思媛部署 workflow 中先更新代码和 schema，再调用运行时 manager 安装主 Web、启用 worker/timer、验证健康并清理 retired units。
3. 保留思媛 merge-to-production 触发方式，不引入 AI-CRM 的 id-dev/生产 IP。
4. 增加 deploy checker，要求 callback worker、external effect worker、internal event worker 和 runtime verify 真正执行。

### Task 3: 显式配置已批准企微效果类型

**Files:**
- Modify: `scripts/ops/ensure_siyuan_production_runtime_env.py`
- Modify: `.github/workflows/deploy.yml`
- Test: `tests/test_siyuan_production_runtime_env.py`

**Steps:**

1. 先写测试，断言脚本只写非敏感运行时键并保留其他 env 内容。
2. 实现幂等 env migration，设置企微 execution mode 与主线批准的 effect type allowlist。
3. 确保未批准 Payment/OAuth/OpenClaw/MCP/Webhook 不被开启。
4. 在服务重启前执行该脚本，并输出脱敏诊断。

### Task 4: 验证代码、前端和运行时合同

**Files:**
- Verify all changed files

**Steps:**

1. 运行 `git diff --check`。
2. 运行 service-period、router、architecture、deploy、runtime、callback、external-effects focused pytest。
3. 运行 service-period frontend Node tests。
4. 运行 `python scripts/ops/manage_production_runtime_units.py --phase verify --dry-run` 及 manifest validator。

### Task 5: GitHub 发布并验证生产

**Files:**
- No additional source files unless CI exposes a bounded compatibility issue.

**Steps:**

1. 提交并推送 `codex/siyuan-full-ai-crm-online-20260716`。
2. 创建中文 PR，正文按 Summary / Architecture boundary / Safety / Verification / Risk / Next action。
3. 等待 PR CI 通过后合并，等待 main CI 与 Deploy to Production 成功。
4. SSH 验证 release SHA、Web/ingress 健康、worker/timer active、runtime allowlist 和数据库 queue 状态。
5. 观察积压回调与 effect jobs 被消费；对两个目标渠道核对新的 event/effect/attempt 证据。
