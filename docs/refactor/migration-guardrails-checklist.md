# Migration Guardrails Checklist

日期：2026-04-17

状态：Mandatory during refactor

用途：

- 作为重构期间的硬规则清单
- 作为 code review / 提交前自查 / 回归测试的统一标准

## 1. 总原则

重构期间所有新改动必须满足：

1. 先收口入口，再拆内部大模块
2. 先新增 application API，再切调用方
3. 不允许把 legacy 文件继续当作“临时放逻辑的地方”
4. 不允许为了省事绕过 application service

## 2. 硬规则

### 2.1 `services.py`

- `wecom_ability_service/services.py` 禁止新增业务实现
- 只允许：
  - re-export
  - 兼容 wrapper
  - monkeypatch / DI glue
- 禁止：
  - raw SQL
  - 直接 `requests`
  - 新的业务规则
  - 新的跨 context 聚合

PR 自查：

- [ ] 这次改动没有在 `services.py` 新增业务逻辑
- [ ] 如果改了 `services.py`，只是缩小职责或增加兼容导出

### 2.2 `mcp_adapter.py`

- `wecom_ability_service/mcp_adapter.py` 只保留 transport
- 只允许：
  - Bearer / internal auth
  - JSON-RPC request / response
  - tool schema 暴露
  - 调用正式 MCP dispatch application API
- 禁止：
  - 直接 import `customer_center.service`
  - 直接 import `customer_timeline.service`
  - 直接 import `services.py`
  - 直接执行业务逻辑

PR 自查：

- [ ] `mcp_adapter.py` 中没有新增业务编排
- [ ] 新工具逻辑落在 application dispatch，而不是 transport

### 2.3 Controller

- HTTP controller 禁止直接 `requests`
- HTTP controller 禁止直接 SQL
- HTTP controller 禁止直接 import `repo.py`
- HTTP controller 禁止直接 import 跨 context 的 `service.py`
- HTTP controller 必须只做：
  - parse request
  - 调 application service
  - build response

适用目录：

- `wecom_ability_service/http/`

PR 自查：

- [ ] controller 里没有 `requests.`
- [ ] controller 里没有 `get_db().execute(...)`
- [ ] controller 里没有业务规则判断分叉

### 2.4 Domain

- domain 禁止 import Flask `request`
- domain 禁止 import Flask `session`
- domain 禁止 import Flask `current_app`
- domain 禁止 import `http.*`
- domain 禁止跨 context import 对方 `repo.py` / `service.py`

适用目录：

- `wecom_ability_service/domains/`

说明：

- 历史遗留代码可以暂时保留，但本轮 touched file 不允许新增这类依赖
- 如果必须保留旧依赖，必须在 PR 里明确写出“为什么本次未消除”

PR 自查：

- [ ] 本次 touched 的 domain 文件没有新增 Flask 依赖
- [ ] 本次 touched 的 domain 文件没有新增跨 context 直连

### 2.5 Read Model

- read model 禁止承接写逻辑
- read model 禁止：
  - `INSERT`
  - `UPDATE`
  - `DELETE`
  - 外发第三方 HTTP
  - 决策业务状态迁移

适用目录：

- `wecom_ability_service/customer_center/`
- `wecom_ability_service/customer_timeline/`

PR 自查：

- [ ] `customer_center/` 改动没有新增写路径
- [ ] `customer_timeline/` 改动没有新增写路径
- [ ] read model 只做聚合、过滤、排序、投影

### 2.6 新功能接入

- 新功能必须通过 application service 接入
- 禁止新功能直接挂在：
  - `services.py`
  - `mcp_adapter.py`
  - `customer_center/service.py`
  - `customer_timeline/service.py`
  - `domains/admin_console/service.py`
  - `domains/admin_console/customer_profile_service.py`

PR 自查：

- [ ] 新增 use case 有明确 application API
- [ ] 没有把新功能塞进 legacy 文件

## 3. 冻结文件清单

以下文件从现在开始视为历史兼容层，只能减法，不能加法：

- `wecom_ability_service/services.py`
- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/customer_center/service.py`
- `wecom_ability_service/customer_center/pulse_service.py`
- `wecom_ability_service/customer_center/customer_profile_service.py`
- `wecom_ability_service/customer_timeline/service.py`
- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/domains/admin_console/service.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py`

规则：

- 可以把逻辑迁出
- 可以保留 wrapper
- 不可以继续长大

## 4. PR Review Checklist

每个相关 PR 至少逐项打勾：

- [ ] 本次改动符合 Wave 1，只做入口收口，没有提前拆大模块
- [ ] 新增跨 context 调用走了正式 application API
- [ ] `services.py` 没有新增业务实现
- [ ] `mcp_adapter.py` 没有新增业务实现
- [ ] controller 没有直接 `requests`
- [ ] controller 没有直接 SQL
- [ ] touched domain 文件没有新增 `request/session/current_app`
- [ ] `customer_center/` 和 `customer_timeline/` 没有新增写逻辑
- [ ] 新增入口有对应 contract test 或复用现有 contract test
- [ ] 如果保留了 legacy import，PR 中说明了淘汰路径

## 5. 已落地自动化门禁

本次 preflight 已落地以下自动化门禁：

- `tests/test_refactor_guardrails.py::test_http_controllers_do_not_add_requests_dependency`
  - 规则：controller 禁止新增 `requests`
  - 方式：历史白名单 + 禁止新增
- `tests/test_refactor_guardrails.py::test_http_controllers_do_not_execute_sql_directly`
  - 规则：controller 禁止直接 SQL
  - 方式：pytest 架构测试
- `tests/test_refactor_guardrails.py::test_legacy_service_imports_do_not_expand`
  - 规则：禁止新增 direct import legacy `service.py` / `services.py` / `customer_timeline` wrapper / `mcp_adapter` 私有函数
  - 方式：pytest 架构测试 + 历史白名单

运行方式：

```bash
python3 -m pytest -q tests/test_refactor_guardrails.py
```

说明：

- 这三个门禁当前采用“现状白名单 + 禁止新增”的策略
- 目的不是一次性清理全部历史依赖，而是先把基线钉住，防止新债继续进入

## 6. 建议的静态检查命令

以下命令可作为提交前检查：

```bash
rg -n "requests\\." wecom_ability_service/http wecom_ability_service/mcp_adapter.py
```

```bash
rg -n "get_db\\(|\\.execute\\(" wecom_ability_service/http
```

```bash
rg -n "from flask import .*request|from flask import .*session|from flask import .*current_app|\\brequest\\b|\\bsession\\b|\\bcurrent_app\\b" wecom_ability_service/domains
```

```bash
rg -n "from .*http\\.|import .*http\\." wecom_ability_service/domains
```

```bash
rg -n "from .*customer_center\\.service|from .*customer_timeline\\.service|from .*services import" \
  wecom_ability_service/http \
  wecom_ability_service/mcp_adapter.py \
  wecom_ability_service/domains/admin_console
```

```bash
rg -n "INSERT INTO|UPDATE |DELETE FROM" wecom_ability_service/customer_center wecom_ability_service/customer_timeline
```

## 7. 必须保留的回归测试

任何触达 Wave 1 范围的 PR，至少要跑：

- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_http_registration_contract.py`
- `tests/contract/test_crm_contract.py`

如果改动涉及 customer automation，还要加跑：

- `tests/test_marketing_automation.py`
- `tests/test_api.py` 中对应 customer / mcp / admin 段

## 8. 例外处理

原则上不设永久例外。

如果本次不得不保留 legacy 依赖，必须同时满足：

1. 只限历史文件，不能扩散到新文件
2. PR 描述里写清楚保留原因
3. 写明下一步迁移出口
4. 不得新增第二个同类例外

不允许的“例外”理由：

- “改 application service 太麻烦”
- “先放到 services.py 以后再说”
- “MCP 里顺手写一下更快”
- “admin 页面只是内部用，不算正式入口”

## 9. Wave 1 结束标志

只有同时满足以下条件，才算 Wave 1 收口完成：

1. `/api/customers*` 和 `/api/customers/<id>/timeline` 全部走 application service
2. `/mcp` 只剩 transport
3. `services.py` 只剩 compatibility shim
4. admin customer shell 不再直连 read model implementation
5. guardrail tests 能稳定拦住新增违规方向
