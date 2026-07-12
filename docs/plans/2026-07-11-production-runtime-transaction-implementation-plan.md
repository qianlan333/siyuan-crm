# Production Runtime Transaction Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 AI-CRM 固化为唯一、可事务化发布的生产源，并在 CI 和部署期消除 Secret 迁移半发布与 systemd 漂移。

**Architecture:** 先把线上已验证的 R00-R02/Secret Store 基线合入 AI-CRM，再让 `production_runtime_units.json` 成为 desired state，由 manager 统一静默、安装、恢复、退役和验证 unit。部署 workflow 负责跨仓库主机锁与 fail-closed transaction，独立 canary 负责验证新进程实际加载了 Secret 与企微登录配置。

**Tech Stack:** Python 3.12、pytest、systemd、GitHub Actions、Bash、FastAPI health/auth routes。

---

### Task 1: 同步线上安全基线到 AI-CRM

**Files:**
- Merge: `AI-CRM-ID-refactor/main@970da6c` into this branch
- Resolve: `.github/workflows/deploy.yml`
- Resolve: `aicrm_next/public_product/h5_wechat_pay.py`
- Resolve: `aicrm_next/questionnaire/h5_write.py`
- Resolve: `docs/ci/test_scope_manifest.yml`
- Resolve: `tests/test_deploy_workflow_contract.py`
- Resolve: `tests/test_select_test_scope.py`

**Steps:**
1. 执行 `git merge --no-ff id-refactor/main`，记录冲突。
2. 对业务文件保留 AI-CRM `814542a` 的手机号校验，同时接入 R02 安全 API。
3. 对 deploy/runtime 测试保留 AI-CRM callback overlay retirement，并吸收 Secret Store/bundle/exact-SHA 逻辑。
4. 运行手机号、callback retirement、Secret Store 与 deploy contract 目标测试。
5. 提交同步基线。

### Task 2: 用测试定义 systemd desired-state

**Files:**
- Modify: `tests/test_runtime_units_autostart.py`
- Modify: `tests/test_deploy_workflow_contract.py`
- Modify: `deploy/production_runtime_units.json`
- Modify: `deploy/aicrm-archive-sync.service`
- Modify: `scripts/ops/manage_production_runtime_units.py`

**Steps:**
1. 先写失败测试：approval timer 必须参与 stop；retired unit 必须 disable/stop/reset；Web unit 必须安装；env service 必须 `User=ubuntu`；ExecStart 入口必须存在。
2. 运行目标测试并确认在旧实现上失败。
3. 扩展 manifest，声明 primary web、retired timer/service 和 approval 生命周期。
4. 实现静态 unit 校验、approval 迁移静默/按 enabled 恢复、retired 收敛和 Web fragment 安装。
5. 运行目标测试并提交。

### Task 3: 事务化生产 deploy workflow

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Modify: `tests/test_deploy_workflow_contract.py`

**Steps:**
1. 先写失败 contract：workflow concurrency、主机 `flock`、mutation/commit 标志、EXIT fail-closed、Web 在 Alembic 前停止、Secret reconcile 后才启动。
2. 运行 contract 并确认失败。
3. 实现 workflow 与主机双层锁，并把 bundle 临时路径绑定 run ID/attempt；旧仓库 publisher 作为上线前退役项。
4. 从已验证 release 解出 controller，在任何工作树变更前安装持久 `ConditionPathExists` guard 并静默运行时。
5. 实现只在 mutation 已开始且未 commit 时触发的 cleanup trap；失败重新创建 guard，不能依赖重启即失效的 runtime mask。
6. 将 stash/reset 放到 quiesce 之后；公网 exact-SHA 后才标记 commit。
7. 运行 contract 并提交。

### Task 4: 新进程 Secret 与企微登录 canary

**Files:**
- Create: `scripts/ops/check_runtime_secret_readiness.py`
- Create: `tests/test_runtime_secret_readiness.py`
- Modify: `.github/workflows/deploy.yml`
- Modify: `docs/runbooks/app_setting_secret_cutover_zh.md`

**Steps:**
1. 写失败测试：health Secret 标志为假、release SHA 不一致、企微 start 回到 `auth_error`、跳转非官方域名、内层 callback 非指定公网 URL 或标记真实外呼时均失败。
2. 实现不跟随重定向的只读 checker，输出只包含状态/host/布尔值，不输出 state 或 Secret。
3. 在 Web health 后、worker 恢复前执行 checker。
4. 更新 runbook 的事务顺序与失败处理。
5. 运行目标测试并提交。

### Task 5: 全量验证与 GitHub 交付

**Files:**
- Verify all changed files

**Steps:**
1. 运行 `pytest` 目标测试、架构 gates、Alembic heads 和 selector tests。
2. 运行仓库全量或 CI 等价测试；修复仅与本变更相关的问题。
3. 检查 diff、Secret/PII 扫描、工作区状态。
4. 推送 `codex/production-runtime-contract-guard` 到 `qianlan333/AI-CRM`。
5. 创建中文 PR，按 Summary / Architecture boundary / Safety / Verification / Risk / Next action 描述。
6. 等待 PR CI，通过后合并；确认 main CI、Deploy to Production、线上 exact SHA、登录 canary和 systemd desired-state。
