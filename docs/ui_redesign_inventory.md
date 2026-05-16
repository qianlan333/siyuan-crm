# UI Redesign Inventory

基线说明：

- 本文只基于当前仓库真实 controller -> template 映射整理，不按历史口头叫法或旧 PR 文案推断。
- `/admin/automation-conversion` 是方案列表；旧全局页面入口已下线，实际承载页面以 `programs/<id>` 路由为主。
- `/s/<slug>` 会根据环境分支渲染问卷填写页或“请在微信客户端打开”页。
- 侧边栏当前真实落地页面只有 `/sidebar/bind-mobile`。

## 1. 后台公共页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/login` | `wecom_ability_service/templates/admin_console/login.html` | 企业微信 SSO / break-glass 登录入口 | admin | Auth hero + dual-action login panel |
| `/admin/api-docs` | `wecom_ability_service/templates/admin_console/api_docs.html` | 后台内置 API 文档总览 | admin | Docs hub + section cards |
| `/admin` | 无独立模板，302 到 `/admin/automation-conversion` | 后台根入口重定向 | admin | Redirect only，不单独设计 |
| `403/404/410 admin 占位态` | `wecom_ability_service/templates/admin_console/placeholder.html` | 权限不足、资源不存在、模块下线等统一占位页 | admin | State page + action cluster |

## 2. 自动化运营页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/admin/automation-conversion` | `wecom_ability_service/templates/admin_console/automation_program_list.html` | 自动化运营方案列表入口 | admin | Hero + summary cards + program table |
| `/admin/automation-conversion/programs/<id>/overview` | `wecom_ability_service/templates/admin_console/automation_conversion_overview_workspace.html` | 方案概览、池子用户、执行摘要 | admin | Program hero + KPI grid + data sections |
| `/admin/automation-conversion/programs/<id>/operations` | `wecom_ability_service/templates/admin_console/automation_conversion_operations_workspace.html` | 任务流列表和行内动作 | admin | Hero + workflow summary + table/list |
| `/admin/automation-conversion/programs/<id>/operations/workflows/new` | `wecom_ability_service/templates/admin_console/automation_conversion_workflow_editor.html` | 新建任务流基础信息 | admin | Step editor workspace |
| `/admin/automation-conversion/programs/<id>/operations/workflows/<workflow_id>/edit` | `wecom_ability_service/templates/admin_console/automation_conversion_workflow_editor.html` | 编辑任务流基础信息 | admin | Step editor workspace |
| `/admin/automation-conversion/programs/<id>/operations/workflows/<workflow_id>/nodes` | `wecom_ability_service/templates/admin_console/automation_conversion_workflow_nodes.html` | 配置节点触发与内容 | admin | Node workspace + list + editor panel |
| `/admin/automation-conversion/programs/<id>/executions` | `wecom_ability_service/templates/admin_console/automation_conversion_execution_records.html` | 查看执行批次与批次内明细 | admin | Batch table + detail panel |
| `/admin/automation-conversion/programs/<id>/flow-design` | `wecom_ability_service/templates/admin_console/automation_conversion_flow_design_workspace.html` | 方案内流程设计壳层 | admin | Sectioned settings workspace |
| `/admin/automation-conversion/programs/<id>/member-ops` | `wecom_ability_service/templates/admin_console/automation_conversion_member_ops_workspace.html` | 成员列表、批量动作、上下文只读区 | admin | Content ops workspace |
| `/admin/automation-conversion/auto-reply` | `wecom_ability_service/templates/admin_console/automation_conversion_auto_reply_workspace.html` | 自动化应答工作区 | admin | Runtime / ops sub-workspace |

## 3. 配置页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/admin/config` | `wecom_ability_service/templates/admin_console/config_overview.html` | 配置中心总览 | admin | Overview cards + quick links |
| `/admin/wecom-tags` | `wecom_ability_service/templates/admin_console/config_wecom_tags.html` | 企微标签管理 | admin | Two-column management table |
| `/admin/config/app-settings` | `wecom_ability_service/templates/admin_console/config_app_settings.html` | 系统设置和敏感参数掩码展示 | admin | Snapshot list + settings editor |
| `/admin/config/login-access` | `wecom_ability_service/templates/admin_console/config_login_access.html` | 企微成员授权、角色与登录审计 | admin | Member list + authorization editor |
| `/admin/config/mcp-tools` | 无独立模板，302 到 `/admin/api-docs` | MCP 工具配置旧入口 | admin | Redirect only，不单独设计 |

## 4. 问卷后台页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/admin/questionnaires` | `wecom_ability_service/templates/admin_console/questionnaires.html` | 问卷列表、搜索、启停、分享入口 | admin | Content management list |
| `/admin/questionnaires/new` | `wecom_ability_service/templates/admin_questionnaires.html` | 新建问卷 | admin | Editor shell + live preview |
| `/admin/questionnaires/<id>` | `wecom_ability_service/templates/admin_questionnaires.html` | 编辑问卷、发布状态、提交数据 | admin | Editor shell + live preview |
| `/admin/questionnaires/external-push-logs` | `wecom_ability_service/templates/admin_console/questionnaire_external_push_logs.html` | 全局问卷外部推送结果 | admin | Result table + filter + detail |
| `/admin/questionnaires/<id>/external-push-logs` | `wecom_ability_service/templates/admin_console/questionnaire_external_push_logs.html` | 单问卷外部推送结果 | admin | Result table + filter + detail |

## 5. 问卷 H5 页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/s/<slug>`（授权通过后） | `wecom_ability_service/templates/questionnaire_h5_page.html` | 问卷填写页 | h5 | Mobile form page |
| `/s/<slug>`（微信内未授权） | `wecom_ability_service/templates/questionnaire_h5_page.html` | OAuth 授权门页 | h5 | Mobile auth gate hero |
| `/s/<slug>/submitted` | `wecom_ability_service/templates/questionnaire_h5_submitted.html` | 问卷已提交页 | h5 | Mobile success state |
| `/s/<slug>`（非微信内打开） | `wecom_ability_service/templates/open_in_wechat.html` | 微信环境拦截提示页 | h5 | Mobile blocking state |

## 6. 侧边栏页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/sidebar/bind-mobile` | `wecom_ability_service/templates/sidebar_bind_mobile.html` | 绑手机号、单客户自动化操作、标签和问卷上下文 | sidebar | Sidebar form + action cards |

## 7. Sunset 占位页

| 路由 | 模板文件 | 当前用途 | 所属端 | 推荐 UI 模板类型 |
| --- | --- | --- | --- | --- |
| `/admin/customers` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/user-ops` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/customer-pulse` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/followup-orchestrator` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/jobs` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/system` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/audit` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/class-user-management` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/class-user-backoffice` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线模块占位页 | admin | Sunset state page |
| `/admin/_legacy` 及子路由 | `wecom_ability_service/templates/admin_console/placeholder.html` | 已下线旧后台入口占位页 | admin | Sunset state page |

## 补充说明

- `/admin/automation-conversion/overview`、`/admin/automation-conversion/operations`、`/admin/automation-conversion/flow-design`、`/admin/automation-conversion/member-ops` 等旧全局入口已下线；真实 UI 按 `programs/<id>` 路由设计。
- `/admin/questionnaires/ui` 是旧 UI 入口，当前会重定向到 `/admin/questionnaires`。
