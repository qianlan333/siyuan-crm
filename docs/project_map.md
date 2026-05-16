# Project Map

这份文档的目标是让新模型或新同事快速定位主模块，而不是把所有实现细节重复一遍。

## 顶层结构

```text
AI-CRM/
├── app.py
├── README.md
├── requirements.txt
├── deploy/
├── docs/
├── openclaw_service/
├── scripts/
├── tests/
└── wecom_ability_service/
```

## 入口链路

- [`app.py`](../app.py)
  - CLI 入口
  - 支持 `python3 app.py init-db`
  - 支持 `python3 app.py run`
- [`wecom_ability_service/__init__.py`](../wecom_ability_service/__init__.py)
  - 创建 Flask app
  - 装载配置、日志、数据库和蓝图
- [`wecom_ability_service/routes.py`](../wecom_ability_service/routes.py)
  - 当前 HTTP 蓝图装配入口
  - 向下接到 `wecom_ability_service/http/`
- [`wecom_ability_service/http/__init__.py`](../wecom_ability_service/http/__init__.py)
  - 注册所有 HTTP route 模块

## `wecom_ability_service/`

这是当前项目最核心的服务目录。

主要结构：

- [`wecom_ability_service/http/`](../wecom_ability_service/http)
  - 控制器层
  - 负责解析请求、调用服务、返回响应
- [`wecom_ability_service/domains/`](../wecom_ability_service/domains)
  - 业务层
  - 主要模块包括：
    - `admin_config`
    - `admin_console`
    - `admin_dashboard`
    - `admin_jobs`
    - `archive`
    - `callbacks`
    - `class_user`
    - `contacts`
    - `identity`
    - `marketing_automation`
    - `questionnaire`
    - `tasks`
    - `user_ops`
- [`wecom_ability_service/templates/admin_console/`](../wecom_ability_service/templates/admin_console)
  - 当前后台控制台页面
- [`wecom_ability_service/static/admin_console/`](../wecom_ability_service/static/admin_console)
  - 后台控制台静态资源
- [`wecom_ability_service/customer_center/`](../wecom_ability_service/customer_center)
  - 客户中心聚合读逻辑
- [`wecom_ability_service/customer_timeline/`](../wecom_ability_service/customer_timeline)
  - 客户时间线聚合读逻辑
- [`wecom_ability_service/mcp_adapter.py`](../wecom_ability_service/mcp_adapter.py)
  - MCP 工具入口
- [`wecom_ability_service/db/`](../wecom_ability_service/db)
  - PostgreSQL 连接、schema 初始化与迁移补齐

## `openclaw_service/`

这是 OpenClaw 相关的适配层。

重点目录：

- [`openclaw_service/integrations/crm/`](../openclaw_service/integrations/crm)
  - CRM 适配器与数据模型
- [`openclaw_service/tools/`](../openclaw_service/tools)
  - OpenClaw 工具注册
- [`openclaw_service/services/`](../openclaw_service/services)
  - CRM operator、聊天上下文等服务
- [`openclaw_service/feishu/`](../openclaw_service/feishu)
  - 飞书相关适配

## `tests/`

测试按能力拆分。

高频会看的文件：

- [`tests/test_api.py`](../tests/test_api.py)
- [`tests/test_user_ops_api.py`](../tests/test_user_ops_api.py)
- [`tests/test_marketing_automation.py`](../tests/test_marketing_automation.py)
- [`tests/test_admin_config.py`](../tests/test_admin_config.py)
- [`tests/contract/test_crm_contract.py`](../tests/contract/test_crm_contract.py)

## `scripts/`

常用脚本包括：

- [`scripts/migrate_sqlite_to_postgres.py`](../scripts/migrate_sqlite_to_postgres.py)
- [`scripts/backup_postgres.sh`](../scripts/backup_postgres.sh)
- [`scripts/run_incremental_archive_sync.py`](../scripts/run_incremental_archive_sync.py)
- [`scripts/run_marketing_automation_backfill.py`](../scripts/run_marketing_automation_backfill.py)

## `deploy/`

- [`deploy/openclaw-wecom-postgres.service`](../deploy/openclaw-wecom-postgres.service)
  - 生产服务配置参考

## 建议阅读顺序

如果任务是：

- 理解后台页面和 HTTP 注册
  - 先看 [`wecom_ability_service/http/__init__.py`](../wecom_ability_service/http/__init__.py)
  - 再看对应 `http/*.py`
  - 最后看对应 `domains/*`
- 理解用户运营或自动化转化
  - 先看 [user_ops_v2.md](user_ops_v2.md)
  - 再看 `domains/user_ops` 和 `domains/marketing_automation`
  - 最后看对应模板和测试
- 理解部署和线上环境
  - 先看 [deploy_runbook.md](deploy_runbook.md)
  - 再看 `deploy/` 和 `scripts/`
- 理解 MCP / OpenClaw
  - 先看 [mcp_usage.md](mcp_usage.md)
  - 再看 [`wecom_ability_service/mcp_adapter.py`](../wecom_ability_service/mcp_adapter.py)
  - 再看 [`openclaw_service/integrations/crm/`](../openclaw_service/integrations/crm)
