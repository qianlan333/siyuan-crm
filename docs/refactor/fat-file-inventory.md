# Fat File Inventory

日期：2026-04-17

范围：

- 扫描当前仓库已跟踪文件
- 排除 `.git/`、`.venv/`、`.venv311/`、`__pycache__/`、`.pytest_cache/` 等可重建目录
- 取当前工作树按行数排序的 Top 20 文件

方法说明：

- 行数来自当前工作树
- `30/90 天改动次数` 仅统计当前 clone 可见历史
- 当前仓库 `git rev-list --count HEAD = 1`，且 `HEAD` 为 `grafted merge commit`
- 因此下面的 `30/90 天改动次数` 只能视为“当前下载副本可见值”，不能当作真实 churn 指标
- `主要调用它的文件`、`它主要依赖的文件` 基于静态 import 图和模板 / SQL 文件名引用，足够用于治理决策，但不等于完整运行时调用图

## Top 20 Fat Files

| 路径 | 总行数 | 所属 context | 文件类型 | 最近 30/90 天改动次数 | 主要调用它的文件 | 它主要依赖的文件 | 是否为冻结文件 | 推荐动作 | 风险等级 |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| `tests/test_automation_conversion_v1.py` | 8902 | Cross-context / Regression | 聚合型 | `1 / 1*` | `pytest` discovery | `wecom_ability_service/domains/automation_conversion/service.py`<br>`wecom_ability_service/domains/automation_conversion/orchestration_service.py`<br>`wecom_ability_service/domains/automation_conversion/agents/llm_client.py` | 否 | 延后拆分 | 高 |
| `tests/test_api.py` | 5896 | Cross-context / Regression | 聚合型 | `1 / 1*` | `pytest` discovery | `wecom_ability_service/services.py`<br>`wecom_ability_service/db.py`<br>`wecom_ability_service/archive_sdk.py` | 否 | 改调用方向 | 高 |
| `wecom_ability_service/domains/customer_pulse/service.py` | 5512 | AI Assist | 聚合型 | `1 / 1*` | `scripts/seed_customer_pulse_demo.py`<br>`tests/test_customer_pulse_inbox.py`<br>`wecom_ability_service/http/background_jobs.py` | `wecom_ability_service/domains/customer_pulse/access.py`<br>`wecom_ability_service/domains/customer_pulse/ai_recommendation.py`<br>`wecom_ability_service/domains/tags/service.py` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/domains/automation_conversion/orchestration_service.py` | 4507 | Automation Engine | 聚合型 | `1 / 1*` | `wecom_ability_service/domains/automation_conversion/service.py`<br>`wecom_ability_service/domains/automation_conversion/workflow_runtime.py`<br>`wecom_ability_service/http/automation_conversion.py` | `wecom_ability_service/customer_timeline/service.py`<br>`wecom_ability_service/domains/admin_console/customer_profile_service.py`<br>`wecom_ability_service/db.py` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/domains/user_ops/service.py` | 4495 | Ops & Enrollment | 聚合型 | `1 / 1*` | `wecom_ability_service/domains/admin_jobs/service.py`<br>`wecom_ability_service/domains/admin_dashboard/repo.py`<br>`wecom_ability_service/http/ops_runtime.py` | `wecom_ability_service/db.py`<br>`wecom_ability_service/infra/constants.py`<br>`wecom_ability_service/wecom_client.py` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/domains/automation_conversion/service.py` | 4447 | Automation Engine | 聚合型 | `1 / 1*` | `wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/http/background_jobs.py`<br>`wecom_ability_service/domains/questionnaire/service.py` | `wecom_ability_service/domains/admin_console/customer_profile_service.py`<br>`wecom_ability_service/domains/automation_conversion/agents/*`<br>`wecom_ability_service/db.py` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/domains/marketing_automation/service.py` | 3760 | Automation Engine | 聚合型 | `1 / 1*` | `wecom_ability_service/customer_center/service.py`<br>`wecom_ability_service/domains/automation_conversion/service.py`<br>`wecom_ability_service/http/sidebar.py` | `wecom_ability_service/domains/archive/service.py`<br>`wecom_ability_service/domains/admin_console/customer_profile_service.py`<br>`wecom_ability_service/db.py` | 否 | 改调用方向 | 高 |
| `tests/test_user_ops_api.py` | 3735 | Cross-context / Regression | 聚合型 | `1 / 1*` | `pytest` discovery | `wecom_ability_service/services.py`<br>`wecom_ability_service/routes.py`<br>`wecom_ability_service/db.py` | 否 | 延后拆分 | 中 |
| `tests/test_customer_pulse_inbox.py` | 3364 | Cross-context / Regression | 聚合型 | `1 / 1*` | `pytest` discovery | `wecom_ability_service/domains/customer_pulse/service.py`<br>`wecom_ability_service/domains/customer_pulse/access.py`<br>`wecom_ability_service/db.py` | 否 | 延后拆分 | 中 |
| `wecom_ability_service/domains/automation_conversion/repo.py` | 3248 | Automation Engine | domain 型 | `1 / 1*` | `wecom_ability_service/domains/automation_conversion/service.py`<br>`tests/test_automation_conversion_v1.py` | `wecom_ability_service/db.py` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/db.py` | 2938 | Platform Foundation | 聚合型 | `1 / 1*` | `app.py`<br>`scripts/seed_customer_pulse_demo.py`<br>`tests/contract/test_crm_contract.py` | `wecom_ability_service/schema.sql`<br>`wecom_ability_service/schema_postgres.sql`<br>`wecom_ability_service/domains/automation_conversion/service.py` | 否 | 包 wrapper | 高 |
| `tests/test_marketing_automation.py` | 2915 | Cross-context / Regression | 聚合型 | `1 / 1*` | `pytest` discovery | `wecom_ability_service/domains/marketing_automation/service.py`<br>`wecom_ability_service/services.py`<br>`wecom_ability_service/db.py` | 否 | 延后拆分 | 中 |
| `wecom_ability_service/mcp_adapter.py` | 2772 | Integration Gateway | transport 型 | `1 / 1*` | `tests/contract/test_crm_contract.py`<br>`wecom_ability_service/domains/admin_config/service.py`<br>`wecom_ability_service/domains/admin_console/service.py` | `wecom_ability_service/customer_timeline/service.py`<br>`wecom_ability_service/customer_center/service.py`<br>`wecom_ability_service/db.py` | 是 | 冻结 | 高 |
| `wecom_ability_service/templates/admin_console/automation_conversion_agent_config_workspace.html` | 2539 | Automation Engine | 入口型 | `1 / 1*` | `wecom_ability_service/http/automation_conversion.py` | `wecom_ability_service/static/admin_console/admin_console.css`<br>内联 workspace 脚本 | 否 | 延后拆分 | 中 |
| `wecom_ability_service/templates/admin_questionnaires.html` | 2457 | Questionnaire | 入口型 | `1 / 1*` | `wecom_ability_service/http/admin_questionnaire_console.py` | `wecom_ability_service/static/admin_console/admin_console.css`<br>问卷页内联脚本 | 否 | 延后拆分 | 中 |
| `wecom_ability_service/domains/followup_orchestrator/service.py` | 2392 | AI Assist | 聚合型 | `1 / 1*` | `wecom_ability_service/http/admin_followup_orchestrator.py`<br>`tests/test_followup_orchestrator_skeleton.py` | `wecom_ability_service/domains/customer_pulse/access.py`<br>`wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py`<br>`wecom_ability_service/infra/settings.py` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/schema_postgres.sql` | 2303 | Platform Foundation | 聚合型 | `1 / 1*` | `wecom_ability_service/db.py`<br>`scripts/migrate_sqlite_to_postgres.py`<br>`tests/test_marketing_schema_init.py` | `wecom_ability_service/schema.sql`<br>共享 DDL 约束 | 否 | 包 wrapper | 高 |
| `wecom_ability_service/schema.sql` | 2300 | Platform Foundation | 聚合型 | `1 / 1*` | `wecom_ability_service/db.py` | `wecom_ability_service/schema_postgres.sql`<br>共享 DDL 约束 | 否 | 包 wrapper | 高 |
| `wecom_ability_service/domains/automation_conversion/workflow_service.py` | 2132 | Automation Engine | domain 型 | `1 / 1*` | `wecom_ability_service/domains/automation_conversion/workflow_runtime.py`<br>`tests/test_automation_conversion_v1.py` | `wecom_ability_service/db.py`<br>`wecom_ability_service/domains/tags/*`<br>`wecom_ability_service/domains/user_ops/*` | 否 | 延后拆分 | 高 |
| `wecom_ability_service/domains/customer_pulse/repo.py` | 2081 | AI Assist | domain 型 | `1 / 1*` | `wecom_ability_service/domains/customer_pulse/service.py`<br>`tests/test_customer_pulse_inbox.py` | `wecom_ability_service/db.py`<br>`wecom_ability_service/domains/customer_pulse/access.py` | 否 | 延后拆分 | 中 |

## 直接可执行的治理结论

1. Wave 1 先不要碰的重文件：
   `wecom_ability_service/domains/customer_pulse/service.py`、`wecom_ability_service/domains/user_ops/service.py`、`wecom_ability_service/domains/automation_conversion/orchestration_service.py`、`wecom_ability_service/domains/automation_conversion/service.py`、`wecom_ability_service/domains/followup_orchestrator/service.py`

2. Wave 1 必须冻结或包起来的文件：
   `wecom_ability_service/mcp_adapter.py`、`wecom_ability_service/db.py`、`wecom_ability_service/schema.sql`、`wecom_ability_service/schema_postgres.sql`

3. 当前最容易继续放大合并冲突的形态：
   超大 domain service + 共享 facade + 大而全测试文件同时改

4. 如果只做“减痛”而不做大拆，优先动作顺序：
   冻结 `mcp_adapter.py`
   给 `db.py` / `schema*.sql` 外面包一层统一操作入口
   停止给 `services.py`、`customer_center.service`、`customer_timeline.service` 增加新调用方
   把大测试文件的新增场景迁到更窄的新测试文件，而不是继续堆进旧文件

5. 当前 inventory 最值得单独看板跟踪的 6 个文件：
   `wecom_ability_service/mcp_adapter.py`
   `wecom_ability_service/db.py`
   `wecom_ability_service/domains/automation_conversion/service.py`
   `wecom_ability_service/domains/automation_conversion/orchestration_service.py`
   `wecom_ability_service/domains/customer_pulse/service.py`
   `wecom_ability_service/domains/user_ops/service.py`
