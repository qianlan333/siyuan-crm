# Phase 1 Execution Plan

日期：2026-04-17

范围：

- 只规划 Wave 1
- 只做入口收口
- 不直接进入 `user_ops` / `questionnaire` / `automation_conversion` / `customer_pulse` 的大拆分

目标：

1. 把 `customer_center` / `customer_timeline` 定义成正式 read model
2. 把 `services.py` 收敛为 compatibility shim
3. 把 `mcp_adapter.py` 收敛为 transport
4. 让 HTTP controllers 只调用 application service

非目标：

- 不改数据模型主归属
- 不做大规模 schema 迁移
- 不拆 `domains/user_ops/service.py`
- 不拆 `domains/questionnaire/service.py`
- 不拆 `domains/automation_conversion/*`
- 不拆 `domains/customer_pulse/service.py`
- 不拆 `domains/followup_orchestrator/service.py`

## 1. Wave 1 交付物

Wave 1 完成后必须交付：

- `wecom_ability_service/application/customer_read_model/` 正式读入口
- `wecom_ability_service/application/integration_gateway/` 的 MCP dispatch 入口
- `wecom_ability_service/application/platform_foundation/` 的 internal auth / runtime tool 入口
- `http/customer_center.py`、`http/customer_timeline.py`、`http/customer_automation.py` controller-only
- `domains/admin_console/service.py`、`domains/admin_console/customer_profile_service.py` 不再直连 read model implementation
- `mcp_adapter.py` 不再直接 import `customer_center.service`、`customer_timeline.service`、`services.py`
- `services.py` 只剩兼容 re-export / shim

## 2. 执行步骤

### Step 1. 建立 application 包骨架，不改业务语义

目标：

- 先给 Wave 1 需要的入口建正式命名空间
- 保持现有对外 HTTP / MCP 契约完全不变

建议修改文件：

- 新增 `wecom_ability_service/application/__init__.py`
- 新增 `wecom_ability_service/application/customer_read_model/__init__.py`
- 新增 `wecom_ability_service/application/customer_read_model/dto.py`
- 新增 `wecom_ability_service/application/customer_read_model/queries.py`
- 新增 `wecom_ability_service/application/integration_gateway/__init__.py`
- 新增 `wecom_ability_service/application/integration_gateway/mcp_dispatch.py`
- 新增 `wecom_ability_service/application/platform_foundation/__init__.py`
- 新增 `wecom_ability_service/application/platform_foundation/auth_queries.py`
- 新增 `wecom_ability_service/application/platform_foundation/mcp_runtime_queries.py`

完成标准：

- 新包可被 import
- 新 query / command 先只转调旧实现，不改变返回结构
- 旧调用方还未切换时，现网行为不变

主要风险：

- DTO 命名和字段边界还没固化，容易把旧实现细节直接搬进 application 层
- 一开始就把 application 层写成“第二个 services.py”

回滚方案：

- 这一阶段是纯新增文件
- 如果命名不合适，直接删新包或回滚新增文件，不影响现有入口

测试与人工验收点：

- 运行现有 customer / MCP contract 测试，确认新增包不破坏 import
- 本地起服务，至少验证 `/api/customers`、`/api/customers/<id>`、`/mcp` 仍可启动

### Step 2. 把 customer_center / customer_timeline 收进正式 application API

目标：

- 把 read model 的“正式入口”从包内 `service.py` 收口到 `application/customer_read_model/queries.py`
- 保持老函数签名兼容，但它们退化为 wrapper

建议修改文件：

- 修改 `wecom_ability_service/customer_center/__init__.py`
- 修改 `wecom_ability_service/customer_center/service.py`
- 修改 `wecom_ability_service/customer_timeline/__init__.py`
- 修改 `wecom_ability_service/customer_timeline/service.py`
- 视情况修改 `wecom_ability_service/customer_center/pulse_service.py`
- 仅在必要时微调 `wecom_ability_service/customer_center/repo.py`
- 仅在必要时微调 `wecom_ability_service/customer_timeline/repo.py`

完成标准：

- `ListCustomersQuery` 覆盖原 `list_customers`
- `GetCustomerDetailQuery` 覆盖原 `get_customer_detail`
- `GetCustomerTimelineQuery` 覆盖原 `get_customer_timeline`
- `GetCustomerChatContextQuery` 能统一 customer detail + recent messages + timeline 摘要
- `customer_center/service.py` 和 `customer_timeline/service.py` 不再承载新的跨 context 协调逻辑

主要风险：

- `customer_center` 详情里存在标签刷新、marketing summary、pulse fallback，容易在抽象过程中丢字段
- `customer_timeline` 有 tenant access / degraded fallback，容易在 application 层重复或遗漏

回滚方案：

- 保留旧 `list_customers` / `get_customer_detail` / `get_customer_timeline` 符号
- application query 只做包装；若回滚，直接让调用方继续回到旧函数
- 不做 schema 变更，因此没有数据回滚

测试与人工验收点：

- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/contract/test_crm_contract.py`
- `tests/test_api.py` 中 customer center / timeline 相关回归
- 人工验收：
  - `GET /api/customers`
  - `GET /api/customers/<external_userid>`
  - `GET /api/customers/<external_userid>/timeline`

### Step 3. 先收口 customer 相关 HTTP controllers

目标：

- 把 controller 从“直接调实现”改成“只调 application API”
- 干掉 controller 里的临时聚合逻辑

建议修改文件：

- 修改 `wecom_ability_service/http/customer_center.py`
- 修改 `wecom_ability_service/http/customer_timeline.py`
- 修改 `wecom_ability_service/http/customer_automation.py`
- 仅保留 `wecom_ability_service/customer_center/routes.py` 的参数解析职责
- 仅保留 `wecom_ability_service/customer_timeline/routes.py` 的参数解析职责

完成标准：

- `http/customer_center.py` 只解析参数并调用 `ListCustomersQuery` / `GetCustomerDetailQuery`
- `http/customer_timeline.py` 只解析参数并调用 `GetCustomerTimelineQuery`
- `http/customer_automation.py` 不再自己拼 `_candidate_context`
- controller 中不再 import：
  - `customer_center.service`
  - `customer_timeline.service`
  - `services.py`
  - `repo.py`

主要风险：

- `signup_conversion_batch_detail` 当前会把客户详情、recent messages、timeline 拼到候选上下文里，切换时最容易出现字段缺失
- controller 里的错误码和旧响应格式可能在改造时意外变化

回滚方案：

- 每个 controller 独立切换
- 一旦某个入口不稳定，只回滚对应 controller 到旧实现
- application query 保留，因此不会影响其他入口继续改造

测试与人工验收点：

- `tests/test_api.py` 中：
  - customer center list/detail
  - customer timeline
  - signup conversion batch detail
- `tests/test_marketing_automation.py` 中批次候选上下文相关用例
- 人工验收：
  - `/api/customers/automation/signup-conversion/batches`
  - `/api/customers/automation/signup-conversion/batches/<batch_id>`

### Step 4. 收口 admin customer profile 和 admin customer shell

目标：

- 先收口最容易继续扩写的后台 customer 入口
- 避免 admin shell 直接绑定 read model implementation 与 MCP 私有函数

建议修改文件：

- 修改 `wecom_ability_service/domains/admin_console/service.py`
- 修改 `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- 修改 `wecom_ability_service/http/admin_customers.py`
- 如有必要，修改 `wecom_ability_service/http/admin_mcp.py`

完成标准：

- admin customer 列表 / 详情统一调用 `application/customer_read_model/*`
- `domains/admin_console/service.py` 不再直接 import：
  - `customer_center.service`
  - `customer_timeline.service`
  - `mcp_adapter` 私有函数
- `domains/admin_console/customer_profile_service.py` 只做 admin 页面 view-model 组装，不再作为新的 read model 实现入口

主要风险：

- admin customer profile 被 marketing / automation / pulse 多处依赖，改动后容易引起联动测试失败
- 一些测试当前 monkeypatch `domains.admin_console.customer_profile_service`，需要保留兼容函数名

回滚方案：

- 保留原函数名与返回字段
- 只把函数内部实现切到 application API
- 若 admin 页面抖动，只回滚 admin shell，不影响 `/api/customers*` 正式 contract

测试与人工验收点：

- `tests/test_admin_customer_profile_console.py`
- `tests/test_admin_mcp_console.py`
- `tests/test_marketing_automation.py` 中 monkeypatch customer profile 的回归
- 人工验收：
  - `/admin/customers`
  - `/admin/customers/<external_userid>`
  - `/admin/mcp`

### Step 5. 把 mcp_adapter.py 缩成 transport

目标：

- 让 `mcp_adapter.py` 只保留：
  - 鉴权
  - JSON-RPC 编码
  - tool schema 暴露
  - 调用 application dispatch

建议修改文件：

- 修改 `wecom_ability_service/mcp_adapter.py`
- 修改 `wecom_ability_service/http/internal_auth.py` 或新增 `application/platform_foundation/auth_queries.py`
- 修改 / 新增 `wecom_ability_service/application/integration_gateway/mcp_dispatch.py`
- 修改 / 新增 `wecom_ability_service/application/platform_foundation/mcp_runtime_queries.py`

完成标准：

- `mcp_adapter.py` 不再直接 import：
  - `customer_center.service`
  - `customer_timeline.service`
  - `services.py`
  - `domains.automation_conversion.*`
- `TOOL_DEFS` 可以保留在 transport 侧，但 tool 执行逻辑迁到 application dispatch
- `/mcp` 的现有请求 / 返回 schema 不变

主要风险：

- MCP tool 很多，容易把 Wave 1 变成大拆分
- `get_customer_context` 目前有 legacy timeline signature fallback，迁移时最容易回归

回滚方案：

- 先只迁移 Wave 1 必需的 customer read tools
- 高风险 write tool 暂时保留旧逻辑，但统一走一个 dispatch 入口
- 如果某个 tool 回归，只回滚该 tool 的 dispatch 映射，不回滚整个 transport

测试与人工验收点：

- `tests/test_mcp_business_tools.py`
- `tests/test_mcp_recent_chat_dump.py`
- `tests/test_api.py` 中 `/mcp` 相关回归
- `tests/contract/test_crm_contract.py`
- 人工验收：
  - `POST /mcp initialize`
  - `POST /mcp tools/list`
  - `POST /mcp tools/call resolve_customer`
  - `POST /mcp tools/call get_customer_context`

### Step 6. 把 services.py 收敛成 compatibility shim

目标：

- 停止 `services.py` 再次成为新总线
- 用显式 re-export 替代隐式业务实现

建议修改文件：

- 修改 `wecom_ability_service/services.py`
- 修改 `wecom_ability_service/routes.py`
- 修改 `wecom_ability_service/archive_adapter.py`
- 视情况修改仍依赖 `services.py` 的少量入口文件
- 视情况新增 architecture guardrail tests

完成标准：

- `services.py` 只包含：
  - re-export
  - backward-compatible wrapper
  - 少量 monkeypatch / DI glue
- `services.py` 不再新增 raw SQL
- `services.py` 不再新增第三方 HTTP 调用
- Wave 1 范围内的新调用方全部从 `services.py` 移除

主要风险：

- 现有测试大量 `from wecom_ability_service.services import ...`
- 贸然删 symbol 会放大影响面

回滚方案：

- Wave 1 不删公开 symbol
- 先保留 symbol，只把其内部实现切到 application API
- 若回滚，只需恢复 wrapper 指向，不涉及数据迁移

测试与人工验收点：

- `tests/test_service_layer_layout.py`
- `tests/test_api.py`
- `tests/test_marketing_automation.py`
- `tests/test_user_ops_api.py`
- `tests/test_admin_config.py`
- 人工验收：
  - 服务正常启动
  - 旧 import 不报错
  - 关键 customer / mcp 入口契约不变

## 3. 风险总表

| 风险 | 影响 | 控制策略 |
| --- | --- | --- |
| customer detail / timeline 字段漂移 | OpenClaw / admin 页面回归 | 先建 application wrapper，严格跑 contract tests |
| admin customer profile 被多模块共享 | 改一处炸多处 | 保留旧函数名，只切内部实现 |
| MCP tool 范围过大 | Wave 1 失控 | 只迁移 customer read 相关 tool，其他 tool 先挂在统一 dispatch 下 |
| `services.py` 使用面过广 | 小改动变全局风险 | 不删 symbol，只改调用方向 |
| controller 改造时混入业务逻辑 | Wave 1 目标失焦 | 每个 controller 都只准做 parse + call + response |

## 4. 回滚原则

Wave 1 的回滚必须遵守以下原则：

1. 不做 schema 级不可逆迁移
2. 先新增 application wrapper，再切调用方
3. 旧函数签名先保留，不在 Wave 1 删除
4. 每一步都可以单独 git revert，不要求整波回滚
5. 任何 contract 漂移都优先回滚 wiring，不回滚数据

## 5. 测试清单

### 5.1 自动化测试

Wave 1 至少应覆盖：

- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_mcp_recent_chat_dump.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/test_admin_mcp_console.py`
- `tests/test_service_layer_layout.py`
- `tests/test_http_registration_contract.py`
- `tests/contract/test_crm_contract.py`
- `tests/test_api.py` 中 customer / mcp / admin 相关回归

### 5.2 人工验收

至少手工验证以下入口：

1. `GET /api/customers`
2. `GET /api/customers/<external_userid>`
3. `GET /api/customers/<external_userid>/timeline`
4. `GET /api/customers/automation/signup-conversion/batches`
5. `GET /api/customers/automation/signup-conversion/batches/<batch_id>`
6. `GET /admin/customers`
7. `GET /admin/customers/<external_userid>`
8. `GET /admin/mcp`
9. `POST /mcp` 的 `initialize`
10. `POST /mcp` 的 `tools/list`
11. `POST /mcp` 的 `resolve_customer`
12. `POST /mcp` 的 `get_customer_context`

## 6. Wave 1 明确不进入的范围

以下只允许做“接 application API”的薄改，不允许做模块内部大拆：

- `wecom_ability_service/domains/user_ops/`
- `wecom_ability_service/domains/questionnaire/`
- `wecom_ability_service/domains/automation_conversion/`
- `wecom_ability_service/domains/customer_pulse/`
- `wecom_ability_service/domains/followup_orchestrator/`

如果某一步需要进入这些目录，只允许：

- 改 import 方向
- 增加兼容 wrapper
- 替换 read model 调用入口

不允许：

- 拆子模块
- 重新定义领域模型
- 扩写新业务逻辑

