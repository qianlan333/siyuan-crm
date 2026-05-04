# 自动化运营方案 Phase 1 可落地蓝图

## 1. 目标

Phase 1 的目标不是一次性实现完整多方案自动化运营引擎，而是在当前单例自动化运营模块上加一层可落地的顶层 program 化结构。

固定命名：

- 中文：自动化运营方案
- 内部名：`automation_program`

Phase 1 只解决：

- 自动化运营入口从“直接进入单例工作面”改为“先进入方案列表”
- 当前单例自动化运营归入一个默认方案
- 方案内先承载当前最核心的业务工作面：`overview`、`operations`、`flow-design`、`member-ops`、`executions`
- 保持共享资源和模块运行时能力不急于方案化
- 为后续逐步引入 `program_id` 和多方案成员模型预留清晰边界

Phase 1 不做完整跨方案成员流转，不做跨方案频控，不改造自动接话和 Agent 配置为方案私有，也不重写当前执行引擎。

### 本次落地状态

当前 Phase 1 已按最小可交付范围落地：

- 新增 `automation_program` 顶层对象，并 bootstrap 默认方案 `signup_conversion_v1` / `默认自动化转化方案`
- `/admin/automation-conversion` 已变为自动化运营方案列表
- 方案内已新增 `overview`、`operations`、`flow-design`、`member-ops`、`executions` 路由壳层
- 旧 `overview`、`operations`、`flow-design`、`member-ops` 入口已下线，不再注册
- 旧 workflow / executions 全局入口已下线，当前使用 program-scoped route
- 旧 `agent-config` 入口已下线，当前入口为 `/admin/automation-conversion/shared/agents`
- 旧 `run-center` 入口已下线，当前入口为 `/admin/automation-conversion/runtime`
- `automation_workflow` 和 `automation_workflow_execution` 已加入 `program_id`，历史数据 backfill 到默认方案
- `auto-reply`、reply monitor、router callbacks、message activity sync、runtime/log/debug/sync 仍保持模块级运行时能力

## 2. 当前自动化运营真实能力拆分

当前自动化运营控制器主要在 `wecom_ability_service/http/automation_conversion.py`，领域逻辑主要在 `wecom_ability_service/domains/automation_conversion/`。现有能力需要先拆成三类。

### A. 方案内能力

Phase 1 推荐纳入 `automation_program` 内的页面和 API，都是“某个方案的业务定义、成员状态或执行结果”。

页面：

- `/admin/automation-conversion/programs/<program_id>/overview`
  - 当前由 `admin_automation_program_overview()` 渲染
  - 读取 `get_overview_payload()`、dashboard、消息活跃同步摘要、reply monitor 摘要等
  - Phase 1 方案内只承载和该方案相关的摘要

- `/admin/automation-conversion/programs/<program_id>/operations`
  - 当前由 `admin_automation_program_operations()` 渲染
  - 包含 workflow registry、workflow 列表、workflow detail、执行入口
  - 是 Phase 1 方案内最核心的“运营编排”工作面

- `/admin/automation-conversion/programs/<program_id>/operations/workflows/new`
  - 新建任务流
  - Phase 1 挂在某个 program 下创建

- `/admin/automation-conversion/programs/<program_id>/operations/workflows/<workflow_id>/edit`
  - 编辑任务流
  - Phase 1 校验 workflow 属于当前 program

- `/admin/automation-conversion/programs/<program_id>/operations/workflows/<workflow_id>/nodes`
  - 节点配置
  - 当前关联 `automation_workflow_node`、`automation_workflow_node_content`、`automation_workflow_node_content_variant`

- `/admin/automation-conversion/programs/<program_id>/executions`
  - 执行记录
  - 当前作为方案级执行记录页

- `/admin/automation-conversion/programs/<program_id>/flow-design`
  - 当前包含阶段模型、问卷规则、SOP 剧本、全局规则、默认渠道入口、发布管理
  - Phase 1 只把阶段模型、问卷规则、SOP、全局规则视为方案内
  - 默认渠道设置暂不 program 化，先作为共享资源保留

- `/admin/automation-conversion/programs/<program_id>/member-ops`
  - 当前包含成员列表、阶段详情、批量动作和手动触达
  - Phase 1 先在默认方案上下文中读取现有 `automation_member`
  - 不实现真正多方案成员并行

API：

- `/api/admin/automation-conversion/dashboard`
- `/api/admin/automation-conversion/member`
- `/api/admin/automation-conversion/member/*`
- `/api/admin/automation-conversion/stage/<stage_key>/*`
- `/api/admin/automation-conversion/sop/*`
- `/api/admin/automation-conversion/workflows*`
- `/api/admin/automation-conversion/workflow-nodes*`
- `/api/admin/automation-conversion/executions*`
- `/api/admin/automation-conversion/execution-items*`

Phase 1 建议对这些 API 增加“可选 program 上下文”的设计，但不要一次性强制所有内部实现改完。旧 API 不带 `program_id` 时默认落到默认方案。

### B. 共享资源能力

Phase 1 保持模块级共享，不塞进每个方案。

页面 / 能力：

- `/admin/automation-conversion/shared/agents`
  - 当前页面聚合 Agent 编排、分层模板、欢迎语 / 二维码、大模型配置
  - Phase 1 不作为方案内页面
  - 后续建议拆成共享资源中心

- Agent 配置
  - `automation_agent_config`
  - `automation_agent_prompt_registry`
  - `automation_agent_skill_registry`
  - `automation_agent_llm_call_log`

- Profile segment templates
  - `automation_profile_segment_template`
  - `automation_profile_segment_category`
  - `automation_profile_segment_option_mapping`

- Default channel settings
  - 当前由 `get_default_channel_settings_payload()`、`save_default_channel_settings()`、`generate_default_channel_qr()` 支撑
  - Phase 1 暂不把默认渠道拆到每个 program

- Model infra settings
  - 当前由 `get_model_infra_payload()`、`save_model_infra_settings()`、`test_model_infra_connection()` 支撑
  - 保持模块级共享

共享资源可以被方案引用，但 Phase 1 不做资源私有化。

### C. 模块运行时能力

Phase 1 保持模块级运行时，不方案化。

页面 / 能力：

- `/admin/automation-conversion/auto-reply`
  - 自动化应答页面
  - 当前依赖 reply monitor、review outputs、Agent outputs
  - Phase 1 保持模块级

- `/admin/automation-conversion/runtime`
  - 当前包含运行概况、数据同步、执行日志 / 审计、模型基础设施、Agent Orchestration、调试
  - Phase 1 不整体放入方案内
  - 后续可拆为“方案运行”和“模块运行时中心”

- Reply monitor
  - `automation_reply_monitor_config`
  - `automation_reply_monitor_queue`
  - `run_reply_monitor_capture()`
  - `run_due_reply_monitor()`

- Router callbacks
  - `handle_agent_router_callback()`
  - `list_router_pending_callbacks()`
  - `run_router_pending_callback_check()`
  - `replay_router_callback()`

- Message activity sync
  - `automation_message_activity_sync_run`
  - `automation_message_activity_sync_item`
  - `run_message_activity_sync()`

- Jobs / due runner
  - `run_registered_due_jobs()`
  - `run_due_conversion_workflows()`
  - `run_due_sop()`
  - `run_due_focus_send_batches()`
  - `/api/admin/automation-conversion/jobs/run-due`

- Runtime logs / debug
  - Agent run/output 查询
  - debug payload
  - router replay
  - model infra diagnostics

## 3. 推荐信息架构

### 一级入口

- 左侧一级导航仍然只有“自动化运营”
- 点击“自动化运营”后进入自动化运营方案列表
- 路由：`/admin/automation-conversion`

### 方案列表页能力

方案列表页是 Phase 1 新增的顶层入口，建议能力：

- 新建方案
  - Phase 1 可以只允许从默认方案复制，或创建空白草稿但不完整可运行

- 复制方案
  - 推荐 Phase 1 支持“从默认方案复制配置壳层”
  - 不复制历史成员、执行记录、运行日志

- 启用 / 停用
  - 方案状态：`draft / active / paused / archived`
  - Phase 1 启停可以先只影响页面和后续写入，不强制接管所有 runtime runner

- 归档
  - 归档后不允许进入写操作
  - 旧数据保留

- 进入方案
  - 进入方案后展示该方案二级导航

- 方案摘要
  - 成员数
  - workflow 数
  - active workflow 数
  - 最近运行时间
  - 最近执行状态
  - 最近更新时间

Phase 1 中非默认方案的摘要可以先只统计已 program 化表；默认方案可以从现有单例表兼容读取。

### 进入方案后的二级导航

Phase 1 方案内二级导航只保留：

- 概览
- 流程设计
- 成员运营
- 运营编排
- 执行记录

说明：

- “运营编排”对应原 `operations`
- `workflow new/edit/nodes` 是“运营编排”下的子页面
- `executions` 可以作为独立二级导航，也可以先作为“运营编排”内 tab；建议产品上保留独立“执行记录”，便于验收和排障

### 模块级入口

推荐在自动化运营模块内保留两个模块级入口，但不放进方案内二级导航：

- 共享资源
  - 推荐路由：`/admin/automation-conversion/shared`
  - 子路由：
    - `/admin/automation-conversion/shared/agents`
    - `/admin/automation-conversion/shared/profile-segments`
    - `/admin/automation-conversion/shared/default-channel`
    - `/admin/automation-conversion/shared/model-infra`
  - 当前以 `/admin/automation-conversion/shared/agents` 作为共享 Agent 配置入口

- 运行时中心
  - 推荐路由：`/admin/automation-conversion/runtime`
  - 子路由：
    - `/admin/automation-conversion/runtime/sync`
    - `/admin/automation-conversion/runtime/reply-monitor`
    - `/admin/automation-conversion/runtime/router`
    - `/admin/automation-conversion/runtime/debug`
    - `/admin/automation-conversion/runtime/logs`
  - 当前以 `/admin/automation-conversion/runtime` 作为模块运行时入口

## 4. 推荐路由

### Phase 1 主路由

- `GET /admin/automation-conversion`
  - 渲染自动化运营方案列表

- `GET /admin/automation-conversion/programs/new`
  - 新建方案页

- `POST /admin/automation-conversion/programs`
  - 创建方案
  - Phase 1 可支持 `create_blank` 或 `copy_from_program_id`

- `GET /admin/automation-conversion/programs/<program_id>/overview`
  - 方案概览

- `GET /admin/automation-conversion/programs/<program_id>/operations`
  - 方案运营编排

- `GET /admin/automation-conversion/programs/<program_id>/operations/workflows/new`
  - 方案内新建 workflow

- `GET /admin/automation-conversion/programs/<program_id>/operations/workflows/<workflow_id>/edit`
  - 方案内编辑 workflow

- `GET /admin/automation-conversion/programs/<program_id>/operations/workflows/<workflow_id>/nodes`
  - 方案内 workflow 节点配置

- `GET /admin/automation-conversion/programs/<program_id>/executions`
  - 方案执行记录

- `GET /admin/automation-conversion/programs/<program_id>/flow-design`
  - 方案流程设计

- `GET /admin/automation-conversion/programs/<program_id>/member-ops`
  - 方案成员运营

### 共享资源路由建议

- `GET /admin/automation-conversion/shared`
  - 共享资源中心首页

- `GET /admin/automation-conversion/shared/agents`
  - 复用当前 agent-config 中 Agent 相关能力

- `GET /admin/automation-conversion/shared/profile-segments`
  - 画像分层模板

- `GET /admin/automation-conversion/shared/default-channel`
  - 默认渠道设置

- `GET /admin/automation-conversion/shared/model-infra`
  - 模型基础设施设置

Phase 1 可以不一次拆完页面，只要明确 Agent 配置是共享资源，不是方案内页面。

### 模块运行时路由建议

- `GET /admin/automation-conversion/runtime`
  - 模块运行时中心

- `GET /admin/automation-conversion/runtime/sync`
  - message activity sync

- `GET /admin/automation-conversion/runtime/reply-monitor`
  - reply monitor

- `GET /admin/automation-conversion/runtime/router`
  - router callbacks

- `GET /admin/automation-conversion/runtime/debug`
  - debug

- `GET /admin/automation-conversion/runtime/logs`
  - runtime logs

Phase 1 可以继续复用当前运行中心模板，只需产品口径明确其是模块级运行时中心。

### 旧路由下线策略

以下旧方案内入口已下线，不再作为当前操作入口：

- `/admin/automation-conversion/overview`
  - 当前使用 `/admin/automation-conversion/programs/<program_id>/overview`

- `/admin/automation-conversion/operations`
  - 当前使用 `/admin/automation-conversion/programs/<program_id>/operations`

- `/admin/automation-conversion/flow-design`
  - 当前使用 `/admin/automation-conversion/programs/<program_id>/flow-design`

- `/admin/automation-conversion/member-ops`
  - 当前使用 `/admin/automation-conversion/programs/<program_id>/member-ops`

- `/admin/automation-conversion/auto-reply`
  - 当前仍保留为自动化应答页面入口；reply-monitor 的浏览器 POST 已迁移到 `/admin/automation-conversion/auto-reply/reply-monitor/*`

以下 workflow / executions 旧全局入口已下线，不再作为当前操作入口：

- `/admin/automation-conversion/operations/workflows/new`
- `/admin/automation-conversion/operations/workflows/<workflow_id>/edit`
- `/admin/automation-conversion/operations/workflows/<workflow_id>/nodes`
- `/admin/automation-conversion/operations/executions`

以下旧深层页面入口已下线，不再作为当前操作入口：

- `/admin/automation-conversion/settings`
- `/admin/automation-conversion/sop`
- `/admin/automation-conversion/stage/<stage_key>`
- `/admin/automation-conversion/model-infra`
- `/admin/automation-conversion/debug`
- `/admin/automation-conversion/preview`
- `/admin/automation-conversion/agent-config`
- `/admin/automation-conversion/run-center`

当前共享资源和运行时入口直接使用：

- `/admin/automation-conversion/shared/agents`
- `/admin/automation-conversion/shared/model-infra`
- `/admin/automation-conversion/runtime`
- `/admin/automation-conversion/runtime/debug`

API 兼容策略：

- Phase 1 不强制替换所有 API path
- 新增 program-aware API 时可先使用 `/api/admin/automation-conversion/programs/<program_id>/...`
- 旧 API 不带 program 时，默认使用默认方案

## 5. 数据模型建议（只收敛，不实现）

### A. 必新增

Phase 1 必须新增 `automation_program`。

原因：

- 没有顶层 program 表，就无法稳定表达方案列表、方案状态、默认方案、旧路由跳转目标
- 仅靠 `automation_key` 或 `scenario_key` 无法覆盖页面、workflow、SOP、成员运营等完整方案概念

Phase 1 必须 bootstrap 默认方案。

默认方案用于承接当前单例自动化运营：

- `program_code = 'signup_conversion_v1'`
- `program_name = '默认自动化转化方案'`
- `status = 'active'`

推荐最小字段：

- `id`
- `program_code`
- `program_name`
- `description`
- `status`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

可选字段：

- `config_json`
- `questionnaire_id`

Phase 1 不建议把过多绑定字段直接塞进 `automation_program`，避免之后拆共享资源时再迁移。

### B. Phase 1 暂不直接改的表

以下表 Phase 1 先不要直接改或不要强制 program 化：

- `automation_member`
  - 当前 `external_contact_id` 全局唯一
  - 直接改会牵动成员动作、SOP 进度、workflow execution、reply monitor、Agent output 等链路
  - Phase 1 先让默认方案托底，不做完整多方案成员并行

- `automation_reply_monitor_config`
- `automation_reply_monitor_queue`
  - Phase 1 保持模块级运行时
  - 先不解决同一外部联系人跨方案自动接话冲突

- `automation_agent_config`
- `automation_agent_prompt_registry`
- `automation_agent_skill_registry`
- `automation_agent_llm_call_log`
- `automation_agent_run`
- `automation_agent_output`
- `automation_agent_output_export_job`
- `automation_agent_skill_call_audit`
  - Phase 1 保持共享资源 / 运行日志
  - 后续可以给 run/output 加 `program_id` 做归因，但不作为 Phase 1 必须项

- `automation_profile_segment_template`
- `automation_profile_segment_category`
- `automation_profile_segment_option_mapping`
  - Phase 1 保持共享资源

- `automation_channel`
  - Phase 1 暂不 program 化
  - 当前 default channel settings 仍保留模块级
  - 后续如果方案需要独立二维码，再引入 `program_id` 或 `automation_program_channel`

- `automation_message_activity_sync_run`
- `automation_message_activity_sync_item`
  - Phase 1 保持模块级运行时

- `outbound_webhook_deliveries`
  - Phase 1 不动
  - 后续通过 `source_key/source_id/payload_json` 或显式 `program_id` 做归因

### C. Phase 1 推荐先挂 `program_id` 的表

只列最小集，避免 Phase 1 变成大规模 schema 重构。

| 表 | Phase 1 判断 | 理由 |
| --- | --- | --- |
| `automation_workflow` | Phase 1 必动 | 运营编排是方案内核心资产；新建/编辑 workflow 必须属于某个方案。 |
| `automation_workflow_audience` | Phase 1 可不动 | 可通过 `workflow_id -> automation_workflow.program_id` 推导，不必第一阶段直接加。 |
| `automation_workflow_execution` | Phase 1 可不动 | 当前执行引擎不重写；可先通过 `workflow_id` 推导默认方案。若新增方案不真正执行，Phase 1 不必加。 |
| `conversion_dispatch_log` | Phase 2 再动 | 当前依赖 `automation_key` 和 message batch；Phase 1 不做跨方案派发隔离。 |
| `customer_marketing_state_current` | Phase 2 再动 | 成员模型 Phase 1 不完整多方案化，客户状态先继续默认方案兼容。 |
| `customer_marketing_state_history` | Phase 2 再动 | 同上，历史状态等成员模型明确后再迁移。 |
| `automation_sop_pool_config` | Phase 1 可不动 | Phase 1 flow-design 可在默认方案下读取旧全局 SOP；新方案可先不支持完整运行。 |
| `automation_sop_template` | Phase 1 可不动 | 同上，若要复制方案配置，可先复制到旧结构但仅默认方案有效；正式多方案 SOP Phase 2 再加。 |
| `automation_sop_progress` | Phase 2 再动 | 强绑定成员；成员模型不动时不应先改。 |
| `automation_sop_batch` | Phase 2 再动 | 运行时批次，执行引擎 Phase 1 不重写。 |
| `automation_sop_batch_item` | Phase 2 再动 | 同上。 |

Phase 1 最小建议：

- 新增 `automation_program`
- 给 `automation_workflow` 增加 nullable `program_id`
- backfill 现有 workflows 到默认方案
- 新建 workflow 必须写默认或当前 `program_id`
- `automation_workflow.workflow_code` 的唯一约束 Phase 1 可以先不改；如果要允许不同方案同 code，Phase 2 再调整为 `(program_id, workflow_code)`

如果担心只动 `automation_workflow` 会造成“方案内 operations 只有部分真实隔离”，可以把 Phase 1 的表改动压缩到只新增 `automation_program`，workflow program 化放 Task 3。产品上先体现方案壳层和默认方案托底。

## 6. 默认方案迁移策略

### 默认方案命名建议

- `program_code = 'signup_conversion_v1'`
- `program_name = '默认自动化转化方案'`
- `description = '由历史单例自动化运营迁移生成的默认方案'`
- `status = 'active'`

### 当前单例自动化运营如何整体归入默认方案

Phase 1 不做全表强迁移，采用“默认方案上下文 + 兼容读取”：

- 当前所有未带 `program_id` 的页面和 API 视为默认方案
- 当前 `automation_member`、`customer_marketing_state_*`、`automation_sop_*`、`reply_monitor_*` 等仍按现状读取
- 已经加 `program_id` 的表，例如 `automation_workflow`，backfill 到默认方案
- 新写入的 program-aware 记录写默认方案或当前方案

### 旧入口下线后的当前入口

以下旧页面路由已下线，不再注册：

- `/admin/automation-conversion/overview`
- `/admin/automation-conversion/operations`
- `/admin/automation-conversion/flow-design`
- `/admin/automation-conversion/member-ops`

当前操作入口统一使用：

- `/admin/automation-conversion/programs/<program_id>/overview`
- `/admin/automation-conversion/programs/<program_id>/operations`
- `/admin/automation-conversion/programs/<program_id>/flow-design`
- `/admin/automation-conversion/programs/<program_id>/member-ops`

旧 API 不带 program 时：

- 默认使用默认方案
- 响应中可以增加 `program_id`、`program_code` 方便前端识别

### 新建方案从空白还是从默认方案复制

Phase 1 推荐两种模式都保留，但默认推荐“从默认方案复制”：

- 空白方案
  - 适合创建草稿
  - Phase 1 能力有限，很多页面可能为空

- 从默认方案复制
  - 适合业务快速复用当前配置
  - Phase 1 只复制方案元信息和 workflow 壳层
  - 不复制成员、执行记录、SOP 进度、派发日志、Agent run/output

Phase 1 验收时，应明确新建方案不代表完整运行引擎已经多方案隔离。

### 哪些统计先从默认方案兼容读取

默认方案统计可从现有单例表兼容读取：

- 成员数：`automation_member`
- workflow 数：`automation_workflow`
- 最近运行时间：`automation_workflow_execution` 或 SOP / focus batch 最新时间
- SOP 最近执行：`automation_sop_batch`
- 派发记录：`conversion_dispatch_log`

非默认方案统计：

- Phase 1 只统计已经带 `program_id` 的 workflow
- 成员数可以先显示 `0` 或“暂未接入多方案成员”
- 最近运行时间可以显示 `-`

## 7. Phase 1 不做的事

Phase 1 明确不做：

- 不做完整跨方案成员流转
- 不做同一用户跨方案并行状态落库
- 不做跨方案频控
- 不做 auto-reply program 化
- 不做 reply monitor program 化
- 不做 router callbacks program 化
- 不做 message activity sync program 化
- 不做 agent-config program 化
- 不做 profile segment templates program 化
- 不做 model infra program 化
- 不做 default channel settings program 化
- 不做大规模 schema 重构
- 不修改 `/mcp` 相关协议和工具
- 不删除旧 `automation_key / scenario_key`
- 不删除旧路由
- 不重写 `run_due_*` 调度器
- 不调整 `automation_member.external_contact_id` 全局唯一约束

## 8. 开发拆分建议

### Task 1：方案列表壳层 + 默认方案 + 路由兼容

目标：

- 建立 `automation_program` 顶层对象
- 自动 bootstrap 默认方案
- `/admin/automation-conversion` 渲染方案列表
- 旧页面路由跳默认方案

改哪些文件：

- `wecom_ability_service/schema.sql`
- `wecom_ability_service/schema_postgres.sql`
- `wecom_ability_service/http/automation_conversion.py`
- `wecom_ability_service/domains/automation_conversion/`
  - 新增 `program_repo.py` 或放入现有 repo
  - 新增 `program_service.py` 或放入现有 service
- `wecom_ability_service/templates/admin_console/`
  - 新增方案列表模板
  - 新增方案内二级导航 partial
- `tests/`
  - 新增 Phase 1 program 路由和默认方案测试

动哪些表：

- 新增 `automation_program`
- 不改其他大表

验收标准：

- `/admin/automation-conversion` 显示方案列表
- 初始数据库自动有默认方案
- 默认方案可进入 program-scoped overview / operations / flow-design / member-ops
- 旧 `/admin/automation-conversion/overview` 已下线，不再注册
- 旧 `/admin/automation-conversion/operations` 已下线，不再注册
- 旧 `/admin/automation-conversion/flow-design` 已下线，不再注册
- 旧 `/admin/automation-conversion/member-ops` 已下线，不再注册
- 共享资源和运行时使用 canonical 入口，旧 `agent-config` / `run-center` 不再作为可用页面入口

### Task 2：方案内页面壳层 program 化

目标：

- 给方案内页面加 `program_id` 上下文
- 不要求所有底层查询都完成多方案隔离
- 默认方案继续兼容当前单例数据

改哪些文件：

- `wecom_ability_service/http/automation_conversion.py`
  - 新增 program route handlers
  - 页面 context 注入 `program`
  - 旧 route redirect 到默认方案
- `wecom_ability_service/templates/admin_console/automation_conversion_*`
  - 增加方案标题、方案状态、方案内二级导航
- `wecom_ability_service/domains/automation_conversion/service.py`
  - overview/member/flow-design payload 接受可选 program context
- `wecom_ability_service/domains/automation_conversion/workflow_service.py`
  - operations payload 接受可选 program context
- `tests/`
  - 方案内页面渲染测试

动哪些表：

- 不强制新增表
- 可继续只依赖 Task 1 的 `automation_program`

验收标准：

- 进入默认方案后只看到方案内二级导航：概览、流程设计、成员运营、运营编排、执行记录
- 默认方案 overview 正常打开
- 默认方案 operations 正常打开
- 默认方案 flow-design 正常打开
- 默认方案 member-ops 正常打开
- 非默认空白方案页面不 500，能显示空状态或默认提示

### Task 3：最小数据 program 化

目标：

- 只把 Phase 1 必要的 workflow 资产挂到 program
- 不动成员模型和 runtime 队列

改哪些文件：

- `wecom_ability_service/schema.sql`
- `wecom_ability_service/schema_postgres.sql`
- `wecom_ability_service/domains/automation_conversion/workflow_repo.py`
- `wecom_ability_service/domains/automation_conversion/workflow_service.py`
- `wecom_ability_service/http/automation_conversion.py`
- `tests/`

动哪些表：

- `automation_workflow`
  - 增加 nullable `program_id`
  - backfill 到默认方案

可选但不建议 Phase 1 必动：

- `automation_workflow_execution`
  - 如果执行记录必须按方案过滤，可先通过 `workflow_id` join 推导，不急于加字段

验收标准：

- 新建 workflow 时写入当前 `program_id`
- 方案 operations 只展示当前方案 workflow
- 默认方案能看到历史 workflow
- 旧 workflow API 不带 program 时仍使用默认方案
- 不破坏现有 workflow node、execution、MCP workflow 读取

## 9. 最终附一页“简版结论”

### A. Phase 1 的 program 化边界

Phase 1 只把自动化运营入口、方案列表、默认方案、方案内页面壳层，以及最小 workflow 资产纳入 `automation_program`。

方案内页面只包括：

- 概览
- 流程设计
- 成员运营
- 运营编排
- 执行记录

### B. Phase 1 的共享资源边界

以下保持模块级共享：

- shared agents
- Agent prompt / skill registry
- profile segment templates
- default channel settings
- model infra settings

### C. Phase 1 的运行时边界

以下保持模块级运行时：

- auto-reply
- reply monitor
- router callbacks
- message activity sync
- jobs / due runner
- runtime / debug / logs

### D. Phase 1 必新增对象

必须新增：

- `automation_program`

必须 bootstrap：

- 默认方案 `signup_conversion_v1`

Phase 1 建议最小 program 化：

- `automation_workflow.program_id`

### E. Phase 1 当前保留和已下线入口

当前使用 program-scoped 入口：

- `/admin/automation-conversion/programs/<program_id>/overview`
- `/admin/automation-conversion/programs/<program_id>/operations`
- `/admin/automation-conversion/programs/<program_id>/flow-design`
- `/admin/automation-conversion/programs/<program_id>/member-ops`

仍保留：

- `/admin/automation-conversion/auto-reply`

已下线旧入口：

- `/admin/automation-conversion/overview`
- `/admin/automation-conversion/operations`
- `/admin/automation-conversion/flow-design`
- `/admin/automation-conversion/member-ops`
- `/admin/automation-conversion/operations/workflows/new`
- `/admin/automation-conversion/operations/workflows/<workflow_id>/edit`
- `/admin/automation-conversion/operations/workflows/<workflow_id>/nodes`
- `/admin/automation-conversion/operations/executions`

共享和运行时能力直接使用 canonical 入口，不再兼容旧 `agent-config` / `run-center` 页面。

### F. Phase 1 不做的事

Phase 1 不做：

- 完整跨方案成员流转
- 跨方案频控
- auto-reply program 化
- agent-config program 化
- model infra program 化
- default channel settings program 化
- 大规模 schema 重构
- `/mcp` 相关改造
- 执行引擎重写
- `automation_member` 全局唯一约束调整
