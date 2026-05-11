# Wave 2 User Ops Callers Map

日期：2026-04-20

目标：

- 只盘点 `user_ops` 当前调用方，不做 caller cutover。
- 明确哪些入口在后续 PR 要切到 `application/user_ops/*`。

## 1. 主调用方地图

| 调用方 | 当前调用入口 | 责任类型 | 后续正式入口 | 备注 |
| --- | --- | --- | --- | --- |
| `wecom_ability_service/http/admin_user_ops.py` | `services.get_user_ops_overview`、`list_user_ops_pool`、`import_mobile_class_term_source`、`import_activation_status_source`、`backfill_owner_class_terms_into_lead_pool`、`run_due_user_ops_deferred_jobs` | admin HTTP read/write 入口 | `GetUserOpsOverviewQuery`、`ListLeadPoolQuery`、`ImportMobileClassTermCommand`、`ImportActivationStatusCommand`、`BackfillOwnerClassTermsCommand`、`RunDueUserOpsDeferredJobsCommand` | 后续第一批 caller cutover 的主入口 |
| `wecom_ability_service/domains/admin_console/service.py` | 同上，并透传 operations shell 行为 | admin shell glue | 同 `http/admin_user_ops.py` | 需与 admin shell / operations shell 一起切 |
| `wecom_ability_service/domains/admin_dashboard/repo.py` | `get_user_ops_overview` | dashboard 聚合读 | `GetUserOpsOverviewQuery` | 只读、风险低，可较早切 |
| `wecom_ability_service/domains/admin_jobs/service.py` | `run_due_user_ops_deferred_jobs`、`get_user_ops_deferred_job_counts` | job orchestration | `RunDueUserOpsDeferredJobsCommand` | counts 读口后续另补 query；本轮先不动 |
| `wecom_ability_service/http/background_jobs.py` | `domains.user_ops.service.run_due_user_ops_deferred_jobs`、`schedule_user_ops_auto_assign_class_term_job` | 内部 job HTTP 入口 | `RunDueUserOpsDeferredJobsCommand`、`ScheduleUserOpsAutoAssignClassTermJobCommand` | 仍属于后续 caller cutover，不在本轮 |
| `wecom_ability_service/domains/contacts/service.py` | 通过依赖注入调用 `refresh_contact_tags_for_external_userid` | customer/contact 刷 tag 协调 | `RefreshUserOpsContactTagsCommand` | 与 customer context 刷新耦合，后续单独处理 |
| `wecom_ability_service/domains/user_ops/service.py` | 内部互调 `upsert_user_ops_lead_pool_member`、`write_user_ops_lead_pool_history`、`refresh_user_ops_contact_tags_for_external_userid` | legacy write owner | `UpsertLeadPoolMemberCommand`、`WriteLeadPoolHistoryCommand`、`RefreshUserOpsContactTagsCommand` | 这是未来内部拆分目标，不在本轮 |

## 2. 高副作用写链路

| 入口 | 当前副作用 | 依赖 context |
| --- | --- | --- |
| `backfill_owner_class_terms_into_lead_pool` | 读 live tags、读 identity、判 class term、写 lead pool current/history | Identity / Class User / Routing / Tags |
| `run_due_user_ops_deferred_jobs` | 跑 deferred job、刷 tags、写 lead pool | Identity / Tags / WeCom Runtime |
| `import_mobile_class_term_source` | 写 import batch、写 current/history、合并绑定结果 | Identity / Class User |
| `import_activation_status_source` | 写 activation source、补丁 current/history | Identity / Lead Pool |
| `schedule_user_ops_auto_assign_class_term_job` | 写 deferred jobs | Background Jobs / Identity |

## 3. 推荐 caller cutover 分批

1. Admin read first
   - `http/admin_user_ops.py`
   - `domains/admin_dashboard/repo.py`
   - `domains/admin_console/service.py` 中 overview/list 读面

2. Admin import / maintenance write second
   - `ImportExperienceLeadsCommand`
   - `ImportMobileClassTermCommand`
   - `ImportActivationStatusCommand`
   - `BackfillOwnerClassTermsCommand`

3. Background / deferred third
   - `http/background_jobs.py`
   - `domains/admin_jobs/service.py`
   - `ScheduleUserOpsAutoAssignClassTermJobCommand`
   - `RunDueUserOpsDeferredJobsCommand`

4. Internal primitive last
   - `UpsertLeadPoolMemberCommand`
   - `WriteLeadPoolHistoryCommand`
   - `RefreshUserOpsContactTagsCommand`

## 4. 本轮保留不动的入口

- `http/admin_user_ops.py`
- `domains/user_ops/service.py` 主逻辑
- `background_jobs / sidebar class-term patch`
- 任何 user_ops schema / SQL

## 结论

`user_ops` 的调用方已经足够清晰，可以在后续 PR 按“先读后写、先低副作用后高副作用”的顺序切换，而不需要一次性大改。
