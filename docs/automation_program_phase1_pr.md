# 标题

自动化运营 Phase 1：引入 automation_program 顶层结构并完成默认方案兼容

## 背景

当前“自动化运营”虽然在导航上是一个一级模块，但真实实现已经包含多层工作面、共享资源和模块运行时能力。继续以单例入口承载所有能力，会让后续多方案隔离、默认方案兼容和运行时边界都变得越来越难维护。

本次 PR 的目标不是一次性做完完整多方案引擎，而是完成 Phase 1：

- 引入 `automation_program` 顶层对象
- 自动化运营入口先进入方案列表
- 当前单例能力整体收口到默认方案
- 仅对 workflow / execution 做最小 program 化
- 保持 shared / runtime 能力继续是模块级

## 本次改动

### 后台结构

- `/admin/automation-conversion` 改为“自动化运营方案列表”
- 新增默认方案：
  - `program_code = signup_conversion_v1`
  - `program_name = 默认自动化转化方案`
- 新增方案内路由：
  - `overview`
  - `operations`
  - `flow-design`
  - `member-ops`
  - `executions`

### 信息架构变化

- 自动化运营入口先到方案列表
- 方案内页面顶部增加 program context
- shared 与 runtime 从方案内能力中拆出，保持模块级
- 旧单例入口全部兼容跳到默认方案

### UI polish 补充

- 方案列表页右上角统一为“共享资源 / 运行时中心 / 新建方案”动作区
- “新建方案”不再默认铺在页面中间，默认首屏聚焦 summary cards 和方案列表
- 方案列表改为 card + table 的管理列表，默认方案也作为普通行统一展示
- 每行主入口统一为“编辑”，直接进入方案工作面，不再同时展示“进入”和单独“编辑”
- 方案基础信息支持编辑 `program_name` 和 `description`
- 方案内 program context header 增加“编辑方案信息”入口，并保留复制、启用或停用、归档操作

### 数据模型变化

- 新增 `automation_program`
- `automation_workflow` 增加 `program_id`
- `automation_workflow_execution` 增加 `program_id`
- DB init / migration 中增加默认方案 bootstrap 和历史数据 backfill

### 路由兼容策略

- 当前使用 `/admin/automation-conversion/programs/<program_id>/overview`
- 当前使用 `/admin/automation-conversion/programs/<program_id>/operations`
- 当前使用 `/admin/automation-conversion/programs/<program_id>/flow-design`
- 当前使用 `/admin/automation-conversion/programs/<program_id>/member-ops`
- 旧 `/admin/automation-conversion/overview` 已下线，不再注册
- 旧 `/admin/automation-conversion/operations` 已下线，不再注册
- 旧 `/admin/automation-conversion/flow-design` 已下线，不再注册
- 旧 `/admin/automation-conversion/member-ops` 已下线，不再注册
- 旧 `/admin/automation-conversion/agent-config` 已下线，当前使用 `/admin/automation-conversion/shared/agents`
- 旧 `/admin/automation-conversion/run-center` 已下线，当前使用 `/admin/automation-conversion/runtime`

## 数据模型变化

新增表：

- `automation_program`

新增字段：

- `automation_workflow.program_id`
- `automation_workflow_execution.program_id`

backfill 策略：

- 历史 workflow 回填到默认方案
- 历史 execution 优先按 workflow 推导 program，再补到默认方案

## 不在本次范围

- 不做完整跨方案成员流转
- 不引入 `automation_program_member`
- 不重构 `automation_member` 唯一约束
- 不 program 化 `auto-reply`
- 不把 `agent-config` 私有化到方案内
- 不把 `model-infra` 私有化到方案内
- 不对 default channel 做全量 program 化
- 不做跨方案频控

## 风险与回滚

风险：

- 旧单例 UI 入口已下线，依赖旧入口直出的脚本需要改到 program-scoped canonical route
- workflow / execution 的接口虽然已支持最小 program 过滤，但个别返回字段仍可能保留旧单例形态
- shared / runtime 页面虽然完成了归位，但后续仍需继续做人工 UAT

回滚方式：

- 回退本 PR 即可恢复旧单例入口
- 回滚不依赖旧入口；旧 route 不再提供重定向
- 默认方案数据本身不影响回滚，只会被回退后的单例逻辑重新视为全局数据
