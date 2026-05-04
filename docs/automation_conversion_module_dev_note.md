# 自动化转化模块开发说明

## 页面与入口

### 自动化运营当前入口总览

页面入口：

- `/admin/automation-conversion`：自动化运营方案列表
- `/admin/automation-conversion/programs/<program_id>/overview`：数据概览
- `/admin/automation-conversion/programs/<program_id>/operations`：自动化运营
- `/admin/automation-conversion/programs/<program_id>/flow-design`：流程设计
- `/admin/automation-conversion/programs/<program_id>/member-ops`：成员运营
- `/admin/automation-conversion/programs/<program_id>/executions`：执行记录
- `/admin/automation-conversion/shared/agents`：模型 / Agent 配置
- `/admin/automation-conversion/shared/model-infra`：共享模型基础设施
- `/admin/automation-conversion/runtime/debug`：运行调试

浏览器表单 / browser-safe POST：

- `/admin/automation-conversion/programs/<program_id>/overview/signup-tag/apply`
- `/admin/automation-conversion/programs/<program_id>/overview/message-activity-sync/run`
- `/admin/automation-conversion/auto-reply/reply-monitor/toggle`
- `/admin/automation-conversion/auto-reply/reply-monitor/capture`
- `/admin/automation-conversion/auto-reply/reply-monitor/run-due`
- `/admin/automation-conversion/programs/<program_id>/member-ops/stage/<stage_key>/send`

internal API：

- `/api/admin/automation-conversion/model-settings`
- `/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview`
- `/api/admin/automation-conversion/stage/<stage_key>/manual-send`
- `/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches`
- `/api/admin/automation-conversion/message-activity-sync/run`
- `/api/admin/automation-conversion/reply-monitor/capture`
- `/api/admin/automation-conversion/reply-monitor/run-due`

注意事项：

- browser-safe POST 使用后台 session + admin action token。
- internal API 使用 internal token，不作为浏览器页面直接调用入口。
- member-ops stage send 仍保留 no-JS multipart form 兜底入口；manual-send API 不承担页面 multipart 实际发送。
- 旧 route 不再提供兼容 redirect。

当前模块使用方案列表、方案内页面、共享资源入口和 runtime 入口。旧 `overview`、`operations`、`flow-design`、`member-ops`、`settings`、`sop`、`stage/<stage_key>`、`model-infra`、`debug`、`preview`、`agent-config`、`run-center` 页面入口已下线。

## 核心数据结构

- `automation_member`：自动化转化成员主表，记录问卷状态、当前大人群等
- `automation_member_audience_entry`：成员进入三类大人群的历史记录
- `automation_workflow`：任务流
- `automation_workflow_audience`：任务流适用人群
- `automation_workflow_agent_binding`：任务流 Agent 直绑关系
- `automation_workflow_node`：线性节点
- `automation_workflow_node_content_variant`：手动分层录入内容明细
- `automation_workflow_execution` / `automation_workflow_execution_item`：执行批次与单用户执行明细
- `automation_profile_segment_template` / `automation_profile_segment_category` / `automation_profile_segment_option_mapping`：基础画像分层模板

## 任务流 / 节点 / Agent 直绑

- 任务流只支持三类大人群：`pending_questionnaire`、`operating`、`converted`
- 任务流分层依据只支持：`none`、`profile`、`behavior`
- 任务流生成方式只支持：
  - `manual_layered`
  - `auto_layered_rewrite`
  - `personalized_single`
- 任务流统一使用 `agent_bindings`
  - `manual_layered`：不绑定 Agent
  - `auto_layered_rewrite`：每个分层类别直接绑定 1 个 `agent_code`
  - `personalized_single`：直接绑定 1 个 `agent_code`
- 节点只做线性配置：名称、目标人群、第几天、时间、标准版内容

## 节点执行链路

- 调度入口：`POST /api/admin/automation-conversion/jobs/run-due`
- 当前 due job：`conversion_workflow`
- 运行逻辑：
  - 先同步成员当前所属大人群
  - 轮询启用中的任务流和节点
  - 命中“当前任务流 + 目标人群 + 进入该人群第 N 天”的成员
  - 生成内容并发送
  - 记录 execution / execution_item / send_record_id / generation_summary
- 失败或未命中时统一回落 `standard_content_text`

## 复用的旧 AI / Lobster 能力

- `orchestration_service.py` 中的 Agent 配置、draft、publish、run、output、review 能力
- 模型调用层与 Prompt 执行链
- 自动化应答 reply monitor / router
- 发送留痕与 `user_ops_send_records`

## 已收口 / 已删除的旧自动化运营概念

- 自动化转化模块内不再暴露：
  - SOP
  - stage
  - focus-send
  - member_ops
  - run_center
  - Agent 池
- `/api/admin/automation-conversion/agent-pools*` 已移除
- 深层旧页面路由和旧一级 alias 已下线，不再注册兼容 redirect

## 当前明确风险

- 旧 SOP / stage 相关 service 与测试代码仍在仓库中，后续可继续做仓内减重，但这次不碰 Lobster 老链路
- 本地空数据环境下，概览、执行记录、评审输出会显示真实空态
- 任务流真实发送依赖外部企微配置；未配置时执行链仍会留痕，但发送会失败
- Postgres 迁移已按 schema 和 db 初始化逻辑收口，仍建议上线前做一次独立数据库演练
