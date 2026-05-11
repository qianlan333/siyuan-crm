# Wave 2 User Ops Contracts

日期：2026-04-20

目标：

- 只为 `user_ops` 建 formal contract 草案和 skeleton owner。
- 本文档不启动 caller cutover，不改变现有 HTTP path，也不改 `domains/user_ops/service.py` 主逻辑。
- 当前 application skeleton 仅做 contract 占位和 legacy delegate，对外宣告后续唯一正式入口。

## 合同总览

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GetUserOpsOverviewQuery` | `GetUserOpsOverviewQueryDTO { filters: LeadPoolFiltersDTO }` | `GetUserOpsOverviewResultDTO { lead_pool_total_count, cards[], generated_at }` | `services.get_user_ops_overview` -> `domains.user_ops.page_service.get_user_ops_overview` | `http/admin_user_ops.py`、`domains/admin_console/service.py`、`domains/admin_dashboard/repo.py` | 读面会消费 `routing_config` / `class_user` 的既有投影结果，但不直接写 | `services.get_user_ops_overview` | 先保留 shim，后续 caller 改直连 query | 1 |
| `ListLeadPoolQuery` | `ListLeadPoolQueryDTO { filters: LeadPoolFiltersDTO }` | `ListLeadPoolResultDTO { items[], total, filters, filter_options, meta }` | `services.list_user_ops_pool` -> `domains.user_ops.page_service.list_user_ops_pool` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 读面依赖 lead pool current + owner role map，不直接写 | `services.list_user_ops_pool` | 先保留 shim，后续 admin list/export 直连 query | 2 |
| `UpsertLeadPoolMemberCommand` | `UpsertLeadPoolMemberCommandDTO { mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound, huangxiaocan_activation_state, class_term_no, class_term_label, entry_source, operator, remark }` | `UpsertLeadPoolMemberResultDTO { member, action_type, before_payload, after_payload }` | `services.upsert_user_ops_lead_pool_member` -> `domains.user_ops.service.upsert_user_ops_lead_pool_member` | `domains/user_ops/service.py` 内部导入流程、owner backfill、deferred jobs | 会写 `user_ops_lead_pool_current` + history，并消费 identity / class_user / routing 结果 | `services.upsert_user_ops_lead_pool_member`、`domains.user_ops.service.upsert_user_ops_lead_pool_member` | 本轮只建 owner，不切 caller | 6 |
| `WriteLeadPoolHistoryCommand` | `WriteLeadPoolHistoryCommandDTO { mobile, external_userid, action_type, source_type, operator, before_payload, after_payload, remark }` | `WriteLeadPoolHistoryResultDTO = None` | `services.write_user_ops_lead_pool_history` -> `domains.user_ops.service.write_user_ops_lead_pool_history` | 当前主要由 `domains/user_ops/service.py` 内部使用 | 仅写 history，属于内部 primitive | 任何新 caller 直接写 `write_user_ops_lead_pool_history` | 不对外公开；后续只允许 application command 内部调用 | 内部 primitive |
| `ScheduleUserOpsAutoAssignClassTermJobCommand` | `ScheduleUserOpsAutoAssignClassTermJobCommandDTO { external_userid, owner_userid, delay_seconds, run_after_seconds, operator }` | `ScheduleUserOpsAutoAssignClassTermJobResultDTO { ok, job_id?, scheduled_for? }` | `services.schedule_user_ops_auto_assign_class_term_job` -> `domains.user_ops.service.schedule_user_ops_auto_assign_class_term_job` | `http/background_jobs.py`、callback/sync 后续补口 | 会写 deferred jobs，并依赖 identity / class_user 结果 | `services.schedule_user_ops_auto_assign_class_term_job` | 先保留 shim，后续 background_jobs 切 command | 7 |
| `RunDueUserOpsDeferredJobsCommand` | `RunDueUserOpsDeferredJobsCommandDTO { limit }` | `RunDueUserOpsDeferredJobsResultDTO { ok, processed_count, items[] }` | `services.run_due_user_ops_deferred_jobs` -> `domains.user_ops.service.run_due_user_ops_deferred_jobs` | `http/admin_user_ops.py`、`http/background_jobs.py`、`domains/admin_jobs/service.py`、`domains/admin_console/service.py` | 会刷新 contact tags、回写 lead pool current/history | `services.run_due_user_ops_deferred_jobs` | 先保留 shim，后续 jobs/admin 分别切 command | 8 |
| `ImportExperienceLeadsCommand` | `ImportExperienceLeadsCommandDTO { pasted_text, file_name, file_bytes, created_by }` | `ImportExperienceLeadsResultDTO { ok, batch_id, total_rows, success_rows, failed_rows, duplicate_count }` | `services.import_experience_leads` -> `domains.user_ops.service.import_experience_leads` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 写 import batch + experience source + history | `services.import_experience_leads` | 先保留 shim，后续 admin import 切 command | 4 |
| `ImportMobileClassTermCommand` | `ImportMobileClassTermCommandDTO { pasted_text, file_name, file_bytes, created_by }` | `ImportMobileClassTermResultDTO { ok, batch_id, applied_count, members[] }` | `services.import_mobile_class_term_source` -> `domains.user_ops.service.import_mobile_class_term_source` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 写 import batch、lead pool current/history，并触发 identity 绑定后续兼容逻辑 | `services.import_mobile_class_term_source` | 先保留 shim，后续 admin import 切 command | 5 |
| `ImportActivationStatusCommand` | `ImportActivationStatusCommandDTO { pasted_text, file_name, file_bytes, created_by }` | `ImportActivationStatusResultDTO { ok, batch_id, applied_count, members[] }` | `services.import_activation_status_source` -> `domains.user_ops.service.import_activation_status_source` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 写 activation source，并补丁更新 lead pool current/history | `services.import_activation_status_source` | 先保留 shim，后续 admin import 切 command | 5 |
| `BackfillOwnerClassTermsCommand` | `BackfillOwnerClassTermsCommandDTO { owner_userid, class_term_min, class_term_max, dry_run, operator, entry_source }` | `BackfillOwnerClassTermsResultDTO { ok, candidate_total, samples[], owner_mismatch_samples[] }` | `services.backfill_owner_class_terms_into_lead_pool` -> `domains.user_ops.service.backfill_owner_class_terms_into_lead_pool` | `http/admin_user_ops.py`、`domains/admin_console/service.py` | 强依赖 identity / class_user / routing / tags，多副作用写 lead pool | `services.backfill_owner_class_terms_into_lead_pool` | 暂不切；放在 import / list 之后单独处理 | 9 |
| `RefreshUserOpsContactTagsCommand` | `RefreshUserOpsContactTagsCommandDTO { external_userid, owner_userid, refresh_scope, scoped_tag_ids[] }` | `RefreshUserOpsContactTagsResultDTO { ok, refreshed, refreshed_userids[], snapshot_count }` | `services.refresh_user_ops_contact_tags_for_external_userid` / `services.refresh_user_ops_contact_tags_for_owner` -> `domains.user_ops.service.*` | `domains/user_ops/service.py` deferred jobs、customer context refresh 兼容链 | 读 WeCom 联系人实时 tags，并写 tag snapshot | `services.refresh_contact_tags_for_external_userid`、`services.refresh_user_ops_contact_tags_for_external_userid`、`services.refresh_user_ops_contact_tags_for_owner` | 保留 shim，后续按 external_userid / owner 两种入口拆命令 | 3 |

## 读写分层口径

- 读面：
  - `GetUserOpsOverviewQuery`
  - `ListLeadPoolQuery`
- 正式写面：
  - `UpsertLeadPoolMemberCommand`
  - `ScheduleUserOpsAutoAssignClassTermJobCommand`
  - `RunDueUserOpsDeferredJobsCommand`
  - `ImportExperienceLeadsCommand`
  - `ImportMobileClassTermCommand`
  - `ImportActivationStatusCommand`
  - `BackfillOwnerClassTermsCommand`
  - `RefreshUserOpsContactTagsCommand`
- 内部 primitive：
  - `WriteLeadPoolHistoryCommand`

## 现阶段明确不做的事

- 不改 `http/admin_user_ops.py` / `domains/admin_console/service.py` 的 caller wiring。
- 不拆 `domains/user_ops/service.py` 内部模块。
- 不处理 `background_jobs / sidebar class-term patch` 的真正 cutover。
- 不做 schema / SQL migration。

## 结论

本轮完成后，`user_ops` 会具备：

- formal application namespace
- 统一 DTO 命名
- 可导入的 query / command skeleton
- 后续 caller cutover 的单一 owner

但真正的 caller cutover 仍留到后续独立 PR。
