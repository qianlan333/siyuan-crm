# Sidebar Progressive Loading Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除侧边栏首屏请求风暴、重复面板请求和请求级连接池自锁，使七模块工作台按需、可恢复地加载。

**Architecture:** 保留现有 Next 路由和页面结构，在现有 `requestPanelJson` 上增加 single-flight，并取消重型自动预取与面板自动重试。后端让侧边栏 DB dependency 在 handler 结束时归还连接，并把完整工作台读取拆成可复用的轻量客户快照，避免 panel 重建 profile/workflow 与未使用的活动流。

**Tech Stack:** FastAPI 0.139、SQLAlchemy 2、原生 JavaScript、pytest、Node VM 行为测试。

---

### Task 1: 锁定前端请求调度契约

**Files:**
- Modify: `tests/test_sidebar_workbench_frontend.py`
- Modify: `tests/test_sidebar_jssdk_frontend_contract.py`
- Create: `tests/frontend/sidebar_progressive_loading.test.mjs`
- Modify: `aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js`
- Modify: `aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html`
- Modify: `package.json`

**Step 1: 写失败的静态契约测试**

新增断言，要求脚本包含 `panelRequests` single-flight Map、JSSDK config 的页面内请求/结果 Map、面板请求 `retryCount: 0`、`data-retry-tab` 手动重试，并且不再调用 `prefetchTabs(["questionnaires", "orders", "periodic_orders"])`。

**Step 2: 写失败的行为测试**

在 Node VM 中提取/加载请求调度 helper，用可计数的 fake fetch 同时请求相同 tab/url：

```js
const [first, second] = await Promise.all([
  requestPanelJson("questionnaires", url),
  requestPanelJson("questionnaires", url),
]);
assert.equal(fetchCalls, 1);
assert.deepEqual(first, second);
```

同时断言失败后 pending key 被清理，下一次手动调用会产生一条新请求；JSSDK config 还需证明相同完整 URL 并发及后续读取只 fetch 一次、带/不带 `external_userid` 使用不同缓存 key、owner token 过期前自动淘汰且无有效 TTL 时不保留 settled payload。慢请求测试还要覆盖 workbench ready 前不发重型 panel，以及素材子类型失败重试、切类型和切主页签竞态。

**Step 3: 运行测试并确认失败**

Run: `.venv/bin/python -m pytest -q tests/test_sidebar_workbench_frontend.py`

Expected: FAIL，缺少渐进加载契约。

Run: `node --test tests/frontend/sidebar_progressive_loading.test.mjs`

Expected: FAIL，缺少可测试的 single-flight 调度 helper。

**Step 4: 最小实现**

- 在 state 中加入 `panelRequests`。
- 在 state 中加入 `jssdkConfigRequests` / `jssdkConfigCache`，两个 JSSDK 调用入口复用同一完整 URL 的请求与结果；resolved cache 按 `expires_in` 提前 30 秒过期、最多保留 5 分钟，无有效 TTL 时只做 single-flight；失败后删除 pending，不做跨页面持久化。
- `requestPanelJson` 先读已完成缓存，再按 `external_userid + tab + url` 复用 pending Promise，并在 `finally` 删除 key。
- panel 默认 `retryCount: 0`；workbench/JSSDK 可保留各自显式策略。
- 删除 `loadWorkbench()` 后的三路自动预取。
- workbench 进入 `ready/degraded_ready` 前禁用并拦截非画像页签。
- `switchTab()` 只在当前 active tab 渲染结果；失败时渲染 `data-retry-tab` 按钮。
- 素材子类型复用独立切换入口，失败显示手动重试，并用发起时的主页签/子类型阻止旧响应覆盖当前界面。
- 点击重试时复用 `switchTab(tab)`，不启动整条 boot。
- 更新静态资源版本，确保生产浏览器获取新脚本。

**Step 5: 运行测试并确认通过**

Run: `.venv/bin/python -m pytest -q tests/test_sidebar_workbench_frontend.py tests/test_sidebar_jssdk_frontend_contract.py`

Expected: PASS。

Run: `node --test tests/frontend/sidebar_progressive_loading.test.mjs`

Expected: PASS，11 个生产函数行为场景覆盖 panel/JSSDK single-flight、token TTL、ready 门禁、手动恢复和页签/素材竞态。

**Step 6: Commit**

```bash
git add aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js \
  aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html \
  tests/test_sidebar_workbench_frontend.py tests/test_sidebar_jssdk_frontend_contract.py \
  tests/frontend/sidebar_progressive_loading.test.mjs package.json
git commit -m "fix: 侧边栏改为渐进式按需加载"
```

### Task 2: 在 PII 审计前归还侧边栏请求连接

**Files:**
- Modify: `aicrm_next/customer_read_model/api.py`
- Modify: `tests/test_customer_read_model_request_scope.py`

**Step 1: 写失败测试**

为 request-scope helper 注入一个 audit repository；`record_pii_access()` 断言 fake session 已关闭。访问 `/api/sidebar/v2/orders`，期望 audit 发生时 `session.closed is True`。

**Step 2: 运行测试并确认失败**

Run: `.venv/bin/python -m pytest -q tests/test_customer_read_model_request_scope.py -k sidebar_v2`

Expected: FAIL，默认 request scope 在 middleware audit 后才清理。

**Step 3: 最小实现**

将使用 request-scoped SQLAlchemy session 的侧边栏 v2 handler 改为：

```python
db: Session = Depends(get_db, scope="function")
```

覆盖 workbench、questionnaires、other-staff-messages、products、orders、periodic-orders 及 remark 写路径；不修改无需该 session 的 material 路径。

**Step 4: 运行测试并确认通过**

Run: `.venv/bin/python -m pytest -q tests/test_customer_read_model_request_scope.py tests/test_pii_audit_contract.py`

Expected: PASS，审计观察到连接已归还，fail-closed PII 契约不变。

**Step 5: Commit**

```bash
git add aicrm_next/customer_read_model/api.py tests/test_customer_read_model_request_scope.py
git commit -m "fix: 在侧边栏审计前释放请求连接"
```

### Task 3: 复用轻量客户快照

**Files:**
- Modify: `aicrm_next/customer_read_model/dto.py`
- Modify: `aicrm_next/customer_read_model/application.py`
- Modify: `aicrm_next/customer_read_model/sidebar_v2.py`
- Create: `aicrm_next/customer_read_model/sidebar_customer_resolution.py`
- Modify: `tests/test_sidebar_v2_api.py`
- Modify: `tests/test_customer_read_model_request_scope.py`

**Step 1: 写失败测试**

- 断言 workbench context request 标记 `include_activity=False`。
- fake repo 计数，断言 workbench、questionnaire、orders、periodic-orders 不调用 `list_timeline`/`list_recent_messages`。
- 断言 panel 的客户解析不调用 `get_profile_fields` 或 `get_workflow_title_for_customer`，但 owner scope、手机号 overlay 和现有响应字段不变。

**Step 2: 运行测试并确认失败**

Run: `.venv/bin/python -m pytest -q tests/test_sidebar_v2_api.py tests/test_customer_read_model_request_scope.py -k 'sidebar and (activity or snapshot or periodic or orders or questionnaire)'`

Expected: FAIL，当前 panel 仍通过完整 workbench 获取 customer。

**Step 3: 最小实现**

- `CustomerContextRequest` 增加默认 `True` 的 `include_activity`。
- `GetCustomerContextQuery` 在其为 `False` 时跳过 timeline/messages，返回空集合与 `skipped` adapter contract。
- `SidebarWorkbenchReadModel` 抽出 `_customer_snapshot()`，返回 customer、context、diagnostics 及极少见 profile-only 回退值；`__call__()` 只在快照上追加 profile/workflow，并避免 profile-only 路径重复读取。
- 将纯 display-name/mobile/binding-source 合并逻辑抽到 `sidebar_customer_resolution.py`，使 `sidebar_v2.py` 保持在 1500 行 runtime module 门禁以下。
- `customer_with_overlay()` 改为直接调用快照，不再调用 `__call__()`。
- sidebar `_context()` 传 `include_activity=False`，live fallback 同样不读取 activity。

**Step 4: 运行测试并确认通过**

Run: `.venv/bin/python -m pytest -q tests/test_sidebar_v2_api.py tests/test_customer_read_model_request_scope.py tests/test_sidebar_readonly_next_native.py`

Expected: PASS，查询计数下降，owner/identity fallback 契约保持。

**Step 5: Commit**

```bash
git add aicrm_next/customer_read_model/dto.py aicrm_next/customer_read_model/application.py \
  aicrm_next/customer_read_model/sidebar_v2.py aicrm_next/customer_read_model/sidebar_customer_resolution.py tests/test_sidebar_v2_api.py \
  tests/test_customer_read_model_request_scope.py
git commit -m "perf: 精简侧边栏客户上下文读取"
```

### Task 4: 集成验证与发布

**Files:**
- Verify: `docs/architecture/route_ownership_manifest.yml`
- Verify: `docs/ci/test_scope_manifest.yml`
- Modify if required: `docs/ci/test_scope_manifest.yml`
- Modify if required: `tests/test_select_test_scope.py`

**Step 1: 运行聚焦回归**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_sidebar_workbench_frontend.py \
  tests/test_sidebar_jssdk_frontend_contract.py \
  tests/test_next_sidebar_workbench_routes.py \
  tests/test_sidebar_v2_api.py \
  tests/test_customer_read_model_request_scope.py \
  tests/test_sidebar_readonly_next_native.py \
  tests/test_pii_audit_contract.py
```

Expected: PASS。

**Step 2: 运行前端行为与静态检查**

Run: `node --test tests/frontend/sidebar_progressive_loading.test.mjs`

Run: `git diff --check`

Expected: PASS / 无输出。

**Step 3: 运行架构与性能门禁**

Run: `bash scripts/ci/run_architecture_gates.sh --mode full`

Run: `.venv/bin/python tools/check_sidebar_profile_next_owner_readiness.py`

Run: `.venv/bin/python tools/check_critical_read_performance.py --report test-results/critical-read-performance.json`

Expected: PASS；无新增 legacy、fixture 或 route ownership 漂移。性能 checker 会重建基准数据，只允许由完整 CI 的隔离 PostgreSQL 执行，禁止指向生产或共享数据库。

**Step 4: 提交计划/清单调整**

将 `tests/frontend/sidebar_progressive_loading.test.mjs` 纳入 `customer_read_model_sidebar` scope 的 `frontend_tests`，确保选择式 CI 会实际执行新增行为测试。
同时纳入 `frontend_p1` 和 `package.json` 的 `test:frontend:all`，使完整前端回归不会遗漏，并用 selector 单测锁定生产 JS 与测试文件两种变更路径。

```bash
git add docs/plans/2026-07-14-sidebar-progressive-loading-design.md \
  docs/plans/2026-07-14-sidebar-progressive-loading-implementation.md \
  docs/ci/test_scope_manifest.yml tests/test_select_test_scope.py
git commit -m "docs: 记录侧边栏加载优化验证方案"
```

**Step 5: 发布与生产验证**

- Push `codex/optimize-sidebar-progressive-loading-20260714`。
- 创建中文 PR，按 Architecture Skill 输出 Summary / Architecture boundary / Safety / Verification / Risk / rollback / Next action。
- CI 通过后合并并等待生产发布。
- 验证 `/health`、`/sidebar/bind-mobile`、各 sidebar v2 API、5001 socket backlog、QueuePool timeout 日志，以及一次真实企微侧边栏快速切换页签的请求数量。
