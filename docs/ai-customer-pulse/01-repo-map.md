# AI Customer Pulse 仓库地图

这份地图只解释“当前仓库每个主要目录负责什么”，方便后续把 `AI Customer Pulse` 挂到现有结构里，而不是另起一套平行实现。

> 2026-05 note: this early Pulse map predates the PG-only cleanup. Current AI-CRM runtime requires PostgreSQL; any SQLite references in older acceptance notes are historical local-test context.

## 1. 顶层目录

| 目录 / 文件 | 职责 |
| --- | --- |
| `app.py` | CLI 入口，支持 `init-db`、`run`、删除问卷提交 |
| `wecom_ability_service/` | 主 Flask 应用，核心业务代码都在这里 |
| `openclaw_service/` | OpenClaw 适配层，偏 CRM client / tool / service，不是主站 HTTP 层 |
| `docs/` | 现有设计、契约、runbook、验收文档 |
| `scripts/` | 同步、回填、迁移、demo seed、runner 脚本 |
| `tests/` | 单元测试、接口测试、契约测试 |
| `deploy/` | systemd / 部署参考 |
| `.github/workflows/` | CI 配置 |

## 2. `wecom_ability_service/`

这是主业务目录。

### 2.1 根文件

| 路径 | 职责 |
| --- | --- |
| `wecom_ability_service/__init__.py` | 创建 Flask app，装载 config、db、logging、observability、routes、MCP |
| `wecom_ability_service/routes.py` | 主蓝图注册入口 |
| `wecom_ability_service/http/__init__.py` | HTTP 模块注册说明与装配 |
| `wecom_ability_service/db.py` | PostgreSQL 初始化与连接 |
| `wecom_ability_service/schema.sql` | 历史 SQLite schema 归档，不作为当前 runtime source |
| `wecom_ability_service/schema_postgres.sql` | Postgres schema |
| `wecom_ability_service/services.py` | 兼容 facade，承接旧 import，不应继续承载新业务核心逻辑 |
| `wecom_ability_service/mcp_adapter.py` | MCP HTTP 入口、工具注册、权限 scope、OpenClaw 读写适配 |
| `wecom_ability_service/wecom_client.py` | WeCom API client |
| `wecom_ability_service/observability.py` | request_id、后台 job 上下文、日志增强 |

### 2.2 `http/`

控制器层。职责是解析请求、校验输入、调用 service、返回 JSON 或模板。

关键模块：

| 目录 / 文件 | 职责 |
| --- | --- |
| `http/admin_dashboard.py` | 工作台页面与状态接口 |
| `http/admin_customers.py` | 客户列表、客户详情、customer profile API、Pulse API |
| `http/admin_user_ops.py` | 用户运营页、批量发送、导出、DND |
| `http/automation_conversion.py` | 自动化转化页面、Run Center、SOP、agent orchestration、reply monitor |
| `http/admin_jobs.py` | 同步任务页、archive/callback/batch/deferred/webhook 操作 |
| `http/admin_config.py` | 配置中心、app settings、MCP tools、routing |
| `http/admin_audit.py` | 审计页与审计查询接口 |
| `http/public_questionnaires.py` | H5 问卷页面、提交、微信 OAuth |
| `http/sidebar.py` | 企微侧边栏能力，单客户动作入口 |
| `http/tasks.py` | WeCom 任务创建接口 |
| `http/tags.py` | 标签管理接口 |
| `http/internal_auth.py` | internal token 与 admin action token |

### 2.3 `domains/`

业务服务层。当前全部遵循 `service.py + repo.py` 的 simple layout。

| 子域 | 职责 |
| --- | --- |
| `admin_dashboard` | 工作台卡片、todos、导航 |
| `admin_jobs` | 同步任务、批次、deferred jobs、webhook 运行视图 |
| `admin_audit` | 后台治理与操作日志查询 |
| `admin_config` | 配置中心、app settings、MCP tool 开关、审计落库 |
| `admin_console` | 后台页面级 read model、预览动作、customer profile 聚合 |
| `archive` | 聊天归档、sync runs、message batches |
| `automation_conversion` | 自动化转化主域：成员池、reply monitor、SOP、agent config/output、run center |
| `automation_state` | 自动化状态纯规则与共享常量 |
| `callbacks` | 企微 callback 业务处理 |
| `class_user` | 报名状态 current/history |
| `contacts` | 联系人快照与 WeCom 联系人同步 |
| `group_chats` | 客户群快照 |
| `identity` | people、bindings、openid/unionid/external_userid 解析 |
| `marketing_automation` | 营销状态机、客户分层、转化状态计算 |
| `outbound_webhook` | webhook 投递与重试 |
| `questionnaire` | 问卷建模、提交、打分、外推 |
| `routing_config` | owner role、路由规则、标签映射 |
| `tags` | 标签规则、实时标签快照与本地同步 |
| `tasks` | 发送任务 dispatch、feedback 持久化 |
| `user_ops` | 运营名单、导入、免打扰、批量发送、deferred job |

### 2.4 `customer_center/`

客户聚合读模型。

| 文件 | 职责 |
| --- | --- |
| `service.py` | 客户列表/详情聚合，组装 owner、binding、identity、tags、marketing summary |
| `repo.py` | 客户聚合底层查询 |
| `dto.py` | customer DTO |
| `pulse_service.py` | 单客户 `AI Customer Pulse`，已挂 `ai_customer_pulse` flag |

适合挂载：

- 单客户视角的 Pulse
- 证据拼接
- 客户详情增强字段

不适合直接承载：

- 运营级多客户收件箱

### 2.5 `customer_timeline/`

客户统一事件流聚合层。

| 文件 | 职责 |
| --- | --- |
| `service.py` | 聚合 message、status_change、questionnaire_submit、wecom_event、marketing_state_change、value_segment_change、openclaw_dispatch |
| `repo.py` | timeline 各来源表查询 |
| `dto.py` | timeline DTO |

这是后续做 Pulse evidence 和活动历史的首选读层。

### 2.6 `infra/`

共享基础设施层。

| 文件 | 职责 |
| --- | --- |
| `settings.py` | `app_settings` 读写、mask、alias |
| `constants.py` | 跨域常量 |
| `helpers.py` | 通用 helper |
| `wecom_runtime.py` | 运行时 WeCom 封装 |
| `wechat_oauth.py` | 微信 OAuth HTTP helper |

### 2.7 `templates/` 与 `static/`

| 路径 | 职责 |
| --- | --- |
| `templates/admin_console/` | 后台 HTML 模板 |
| `templates/sidebar_bind_mobile.html` | 企微侧边栏页面 |
| `templates/questionnaire_h5_page.html` | H5 问卷页 |
| `static/admin_console/` | 后台页面 JS/CSS |
| `static/admin_console/customer_profile.js` | 客户详情页前端，已含 Pulse 渲染逻辑 |

## 3. `openclaw_service/`

这是 OpenClaw 侧的适配层，不是 CRM 主站页面层。

| 目录 | 职责 |
| --- | --- |
| `integrations/crm/` | CRM client、config、errors |
| `services/` | OpenClaw 读取 CRM 上下文的服务 |
| `tools/` | OpenClaw 工具注册与调用 |
| `cli/` | 当前仅有 chat context CLI bridge |
| `feishu/` | 飞书适配 |

当前结论：

- `openclaw_service` 没有真实 conversation runtime / session runtime / orchestration runtime。
- 如果未来要把 Pulse 深度接进 OpenClaw，不应假设这里已有会话主循环。

## 4. `docs/`

现有文档已经覆盖不少仓库事实，建议优先复用。

| 文档 | 作用 |
| --- | --- |
| `docs/project_map.md` | 仓库总览 |
| `docs/customer_center_api.md` | 客户聚合读接口说明 |
| `docs/customer_timeline_api.md` | timeline 聚合契约 |
| `docs/openclaw_crm_read_contract.md` | OpenClaw 依赖的 CRM 读契约 |
| `docs/user_ops_v2.md` | 用户运营页口径 |
| `docs/automation_conversion_*` | 自动化转化的验收、配置矩阵、runbook |
| `docs/openclaw_chat_context.md` | OpenClaw 读取客户聊天上下文 |
| `docs/openclaw_real_runtime_entry_assessment.md` | 说明当前没有更深的 OpenClaw runtime |

## 5. `scripts/`

这些脚本代表现有的定时任务 / 运维入口。

| 脚本 | 职责 |
| --- | --- |
| `run_incremental_archive_sync.py` | 聊天归档增量同步 runner |
| `run_marketing_automation_backfill.py` | 营销自动化回填 |
| `run_message_activity_sync.py` | 消息活跃同步 |
| `run_owner_lead_pool_backfill.py` | owner lead pool 回填 |
| `seed_automation_conversion_demo.py` | 自动化转化 demo 数据与本地联调 |
| `migrate_sqlite_to_postgres.py` | 数据库迁移 |
| `backup_postgres.sh` / `restore_postgres.sh` | 备份恢复 |

说明：

- 自动化转化的部分 runner 不是脚本文件，而是通过 HTTP `run-due` 接口 + cron 调度驱动。

## 6. `tests/`

测试已经形成较完整的仓库事实护栏。

| 区域 | 重点 |
| --- | --- |
| `tests/test_admin_customer_profile_console.py` | 客户详情页、Pulse、自动化侧栏 |
| `tests/test_marketing_automation.py` | 营销状态、分层、dispatch |
| `tests/test_customer_timeline_api.py` | timeline 聚合契约 |
| `tests/test_admin_jobs_console.py` | jobs page、审计、webhook retry |
| `tests/test_automation_conversion_v1.py` | 自动化转化大部分页面、reply monitor、agent outputs、SOP |
| `tests/contract/` | 对外契约护栏 |

如果后续做 Pulse 正式开发，新增代码最好落在这些现有测试带里，而不是单开一套陌生框架。

## 7. 与 AI Customer Pulse 最相关的目录

### 一级相关

- `wecom_ability_service/customer_center/`
- `wecom_ability_service/customer_timeline/`
- `wecom_ability_service/domains/admin_console/`
- `wecom_ability_service/domains/automation_conversion/`
- `wecom_ability_service/domains/marketing_automation/`
- `wecom_ability_service/static/admin_console/customer_profile.js`
- `wecom_ability_service/templates/admin_console/customer_detail.html`

### 二级相关

- `wecom_ability_service/domains/user_ops/`
- `wecom_ability_service/http/sidebar.py`
- `wecom_ability_service/http/internal_auth.py`
- `wecom_ability_service/infra/settings.py`
- `wecom_ability_service/domains/admin_dashboard/`
- `wecom_ability_service/domains/admin_jobs/`

## 8. 对后续接入的结构建议

如果后面正式做 `AI Customer Pulse`，目录上最稳妥的落点是：

1. 单客户能力继续放 `customer_center/pulse_service.py`，因为这里已经有 flag 和 evidence 逻辑。
2. 列表级收件箱读模型优先放 `domains/automation_conversion/`，因为 AI 输出、reply monitor、SOP、队列都在这个域。
3. 页面层优先加在：
   - `/admin/automation-conversion/runtime` 新 subtab
   - `/admin/customers/<external_userid>` 详情增强
   - `/admin` todo 汇总提醒

不建议：

- 在 `services.py` 堆新逻辑
- 在 `http/` 里直接拼 SQL
- 在 `openclaw_service/` 里先造一个并不存在的 conversation runtime
