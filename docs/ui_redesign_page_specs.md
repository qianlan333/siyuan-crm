# UI Redesign Page Specs

原则：

- 只改 UI / 交互层，不改业务逻辑、接口语义、路由语义、数据模型。
- 不破坏当前瘦身、SSO、automation_program Phase 1 结构。
- 所有页面规格以当前仓库真实模板和真实路由为准。

## Phase A：后台壳层与基础组件

| 页面 | 目标样式 | 关键组件 | 交互变化 | 不改动的业务逻辑 |
| --- | --- | --- | --- | --- |
| `/login` | 登录 hero + 双入口登录面板 | Hero、企微登录按钮、break-glass 区块、只读审计表 | 结构更清晰，按钮更突出 | 企业微信 SSO、break-glass、表单提交、跳转参数 |
| `/admin/api-docs` | 文档 hub + section cards | 文档目录、模块卡片、兼容说明 | 首屏改成文档入口面板 | 文档内容、链接、分组语义 |
| `placeholder`（403/404/410） | 状态页 hero + CTA | 状态标题、说明、保留入口、提示表格 | 更适合承载 sunset / denied / not found | 状态码、文案语义、入口目标 |
| `admin shell` | 蓝灰后台壳层 | sidebar、topbar、breadcrumbs、page header | 统一全站后台骨架 | 导航结构、RBAC 控制、路由 |
| `config shell` | list + editor 模式壳层 | tab、列表区、编辑区、sticky aside | 配置页统一阅读节奏 | 配置项字段、提交路径 |

## Phase B：自动化运营全页改造

| 页面 | 目标样式 | 关键组件 | 交互变化 | 不改动的业务逻辑 |
| --- | --- | --- | --- | --- |
| `/admin/automation-conversion` | Hero + summary cards + program table | 方案摘要卡、方案列表、行内动作 | 从纯列表升级为方案总览工作台 | program create/copy/activate/pause/archive |
| `/admin/automation-conversion/programs/<id>/overview` | Program hero + KPI + 摘要区块 | program context、KPI、池子用户表、执行摘要表 | 首屏信息更聚焦 | overview API、统计口径、默认方案跳转 |
| `/admin/automation-conversion/programs/<id>/operations` | Hero + workflow summary + table | Hero、筛选、任务流表、row actions | 列表页只保留列表与动作，不再混排编辑器 | workflows list/activate/pause/delete API |
| `/admin/automation-conversion/programs/<id>/operations/workflows/new` | 两步式编辑工作区 | step strip、基础表单、Agent 绑定卡 | 明确“先建任务流，再去节点页” | 创建任务流字段、提交 API、保存后跳转 |
| `/admin/automation-conversion/programs/<id>/operations/workflows/<workflow_id>/edit` | 两步式编辑工作区 | step strip、基础表单、Agent 绑定卡 | 更清晰地区分基础信息和节点配置 | 编辑字段、保存 API、进入 nodes 逻辑 |
| `/admin/automation-conversion/programs/<id>/operations/workflows/<workflow_id>/nodes` | Node workspace | 节点列表、节点编辑卡、触发方式区块 | 节点页只做节点，不再混排任务流基础表单 | node list/create/update/delete API |
| `/admin/automation-conversion/programs/<id>/executions` | Batch table + detail panel | 批次列表、过滤器、批次明细、执行项动作 | 批次详情和发送项明细统一成双区结构 | executions list/detail/items API、补发动作 |
| `/admin/automation-conversion/programs/<id>/flow-design` | 分段设置工作区 | section nav、阶段模型、问卷规则、SOP、渠道入口 | 从旧设置散点升级成统一工作区 | save_settings、默认渠道入口、发布逻辑 |
| `/admin/automation-conversion/programs/<id>/member-ops` | 内容运营型工作区 | 成员列表、批量动作区、只读上下文卡 | 将发送动作和成员信息明确拆区 | manual send、focus batch、阶段语义 |
| `/admin/automation-conversion/shared/agents` | Shared config workspace | Agent 列表、draft/published 对比、模板区 | 与 program 页视觉统一，但语义明确为 shared | draft 保存、模板数据、welcome channel 配置 |
| `/admin/automation-conversion/shared/profile-segments` | Shared config workspace | 画像模板列表、明细、编辑面板 | 与 shared agents 一致，聚焦模板 | profile segment template 配置 |
| `/admin/automation-conversion/shared/model-infra` | Runtime-like infra workspace | model KPI、基础设施信息、协议块 | 视觉归入 runtime / shared 体系 | model-infra tab 语义 |
| `/admin/automation-conversion/runtime` | Runtime hero + tab cards | tab、KPI、概况卡 | 首屏变成运行中心仪表板 | runtime tab 结构 |
| `/admin/automation-conversion/runtime/sync` | runtime sub-workspace | sync KPI、状态说明、缺失项 | 更适合快速诊断 | sync 状态和配置判断 |
| `/admin/automation-conversion/runtime/router` | runtime sub-workspace | router subtab、协议块、配置提示 | 协议信息更清晰可读 | router 协议、字段、提交 |
| `/admin/automation-conversion/runtime/logs` | runtime sub-workspace | logs KPI、失败提示、入口链接 | 从占位文本升级成结构化板块 | logs 入口语义 |
| `/admin/automation-conversion/runtime/debug` | runtime sub-workspace | debug code block、lookup 区 | 调试信息更易读 | debug 查询逻辑 |

## Phase C：配置中心与问卷后台改造

| 页面 | 目标样式 | 关键组件 | 交互变化 | 不改动的业务逻辑 |
| --- | --- | --- | --- | --- |
| `/admin/config` | overview cards + quick links | summary cards、配置入口卡 | 首屏从普通列表改成入口总览 | 各子页路由 |
| `/admin/wecom-tags` | two-column management table | group list、tag table、capacity indicator | 集中管理企微客户标签 | 企微 tag_id、mark_tag、标签选择器兼容结构 |
| `/admin/config/app-settings` | snapshot list + editor aside | masked rows、editable rows、settings form | 阅读和编辑边界更清楚 | setting__* 字段、确认逻辑 |
| `/admin/config/login-access` | 企微成员授权页 | member list、授权编辑器、登录审计 | 明确表达“企微成员授权”语义 | RBAC、角色字段、保存路径 |
| `/admin/questionnaires` | 内容管理列表 | 搜索、状态筛选、列表、row actions | 更偏 CMS，而不是 automation 工作台 | 列表加载、启停、复制链接 |
| `/admin/questionnaires/new` | 问卷编辑工作台 | 顶栏、题目编辑、评分规则、实时预览 | 统一到蓝灰内容编辑器风格 | 新建字段、保存接口、预览逻辑 |
| `/admin/questionnaires/<id>` | 问卷编辑工作台 | 顶栏、题目编辑、结果预览、发布状态 | 同上 | 编辑、启停、导出、提交数据展示 |
| `/admin/questionnaires/external-push-logs` | 结果管理页 | filter、summary、结果表、detail | 用结果管理风格呈现失败补发 | filter、retry、batch retry |
| `/admin/questionnaires/<id>/external-push-logs` | 单问卷结果管理页 | filter、summary、结果表、detail | 同上 | 单问卷补发逻辑 |

## Phase D：问卷 H5 与侧边栏端改造

| 页面 | 目标样式 | 关键组件 | 交互变化 | 不改动的业务逻辑 |
| --- | --- | --- | --- | --- |
| `/s/<slug>`（授权门页） | zip 基准的 H5 auth gate | Hero、授权 CTA、环境提示 | 授权动作更突出、留白更充足 | OAuth 起点 URL、环境判断 |
| `/s/<slug>`（填写页） | zip 基准的 H5 form | Hero、问题卡、提交按钮、错误提示 | 表单阅读节奏更清晰 | `questionnaire-form` DOM、submit action、diagnostics |
| `/s/<slug>/submitted` | H5 success state | success card、标题、说明 | 视觉更轻、更直接 | 路由、文案语义 |
| `/s/<slug>`（非微信环境） | 微信内打开阻断页 | state card、说明文案 | 更接近 zip 的简单阻断态 | 非微信判断逻辑 |
| `/sidebar/bind-mobile` | zip 基准的 sidebar 单客户页 | 绑定手机号卡、自动化动作卡、标签卡、问卷答案卡 | 更清晰地区分“绑定动作”和“单客运营动作” | DOM id、data-* url、jssdk、单客动作接口 |

## 不在本轮改业务的明确边界

- 不改 API path、query、body、response schema。
- 不改数据库 schema 与数据模型。
- 不改 automation_program Phase 1 的 program / workflow / node 拆分结构。
- 不改 SSO / RBAC 主逻辑。
- 不改问卷提交、已提交判断、外推补发、sidebar 动作的业务判断。
