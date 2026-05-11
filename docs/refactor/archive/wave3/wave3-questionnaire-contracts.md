# Wave 3 Questionnaire Contracts

日期：2026-04-20

## 1. 目标

本文只定义 questionnaire 的正式 contract 草案，不改业务代码。

正式 contract 的目标：

- 让 admin / public / submit / external push 各自有唯一 application owner
- 让 controller 不再直接依赖 `services.py` 或 `domains/questionnaire/service.py`
- 让 questionnaire 对 identity / SCRM apply / external push / automation bridge 的跨 context 副作用变成显式 command

建议命名空间：

- `wecom_ability_service/application/questionnaire/queries.py`
- `wecom_ability_service/application/questionnaire/commands.py`
- `wecom_ability_service/application/questionnaire/dto.py`
- `wecom_ability_service/application/questionnaire/_legacy_delegate.py`

## 2. 合同总览

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ListQuestionnairesQuery` | `ListQuestionnairesQueryDTO { include_disabled, include_stats }` | `ListQuestionnairesResultDTO { items[] }` | `services.list_questionnaires` -> `domains.questionnaire.service.list_questionnaires` | `http/admin_questionnaires.py`、`domains/admin_console/service.py`、`domains/admin_dashboard/repo.py`、`domains/automation_conversion/service.py` | 无写副作用；读面附带提交统计 | `services.list_questionnaires`、`domains.questionnaire.service.list_questionnaires` | 先保留 shim，再切 admin 与相邻 reader | 1 |
| `GetQuestionnaireDetailQuery` | `GetQuestionnaireDetailQueryDTO { questionnaire_id }` | `GetQuestionnaireDetailResultDTO { questionnaire }` | `services.get_questionnaire_detail` -> `domains.questionnaire.service.get_questionnaire_detail` | `http/admin_questionnaires.py`、`domains/admin_console/service.py`、`domains/marketing_automation/service.py`、`domains/automation_conversion/service.py` | 无直接写副作用 | `services.get_questionnaire_detail`、`domains.questionnaire.service.get_questionnaire_detail` | 先保留 shim，再切 admin/automation reader | 1 |
| `BuildQuestionnairePreflightQuery` | `BuildQuestionnairePreflightQueryDTO { config_snapshot }` | `BuildQuestionnairePreflightResultDTO { checks[], summary }` | `domains.questionnaire.preflight_service.build_questionnaire_preflight_payload` | `http/admin_questionnaires.py`、`domains/admin_dashboard/repo.py` | 读 `Integration Gateway` / `Identity` 可用性；无写副作用 | `domains.questionnaire.build_questionnaire_preflight_payload` | 新建 query 后，把 admin/preflight 只走 application | 2 |
| `GetLatestQuestionnaireSubmitDebugQuery` | `GetLatestQuestionnaireSubmitDebugQueryDTO { questionnaire_id }` | `GetLatestQuestionnaireSubmitDebugResultDTO { debug_log? }` | `services.get_latest_questionnaire_submit_debug` -> `domains.questionnaire.service.get_latest_questionnaire_submit_debug` | `http/admin_questionnaires.py` | 无写副作用 | `services.get_latest_questionnaire_submit_debug` | 保留 legacy 返回结构不变 | 2 |
| `ExportQuestionnaireSubmissionsQuery` | `ExportQuestionnaireSubmissionsQueryDTO { questionnaire_id }` | `ExportQuestionnaireSubmissionsResultDTO { rows[], columns[] }` | `services.export_questionnaire_submissions` -> `domains.questionnaire.service.export_questionnaire_submissions` | `http/admin_questionnaires.py` | 无写副作用；读取 submission / answers 快照 | `services.export_questionnaire_submissions` | 先切 admin export，再清理 service shim | 3 |
| `CreateQuestionnaireCommand` | `CreateQuestionnaireCommandDTO { payload, operator }` | `CreateQuestionnaireCommandResultDTO { questionnaire }` | `services.create_questionnaire` -> `domains.questionnaire.service.create_questionnaire` | `http/admin_questionnaires.py`、`domains/admin_console/service.py` | 无跨 context 写；只写 questionnaire 自身表 | `services.create_questionnaire`、`domains.questionnaire.service.create_questionnaire` | 保持现有 JSON key 与错误路径 | 3 |
| `UpdateQuestionnaireCommand` | `UpdateQuestionnaireCommandDTO { questionnaire_id, payload, operator }` | `UpdateQuestionnaireCommandResultDTO { questionnaire }` | `services.update_questionnaire` -> `domains.questionnaire.service.update_questionnaire` | `http/admin_questionnaires.py`、`domains/admin_console/service.py` | 无跨 context 写；只写 questionnaire 自身表 | `services.update_questionnaire`、`domains.questionnaire.service.update_questionnaire` | 保留 editor payload 与返回结构 | 3 |
| `DisableQuestionnaireCommand` | `DisableQuestionnaireCommandDTO { questionnaire_id, is_disabled, operator }` | `DisableQuestionnaireCommandResultDTO { questionnaire }` | `services.disable_questionnaire` -> `domains.questionnaire.service.disable_questionnaire` | `http/admin_questionnaires.py`、`domains/admin_console/service.py` | 无跨 context 写 | `services.disable_questionnaire` | 保持启停语义与状态字段不变 | 3 |
| `DeleteQuestionnaireCommand` | `DeleteQuestionnaireCommandDTO { questionnaire_id, operator }` | `DeleteQuestionnaireCommandResultDTO { deleted }` | `services.delete_questionnaire` -> `domains.questionnaire.service.delete_questionnaire` | `http/admin_questionnaires.py` | 只删除 questionnaire 自身主记录 | `services.delete_questionnaire` | 保留布尔返回与 404/False 语义 | 3 |
| `GetPublicQuestionnaireBySlugQuery` | `GetPublicQuestionnaireBySlugQueryDTO { slug }` | `GetPublicQuestionnaireBySlugResultDTO { questionnaire }` | `services.get_public_questionnaire_by_slug` -> `domains.questionnaire.service.get_public_questionnaire_by_slug` | `http/public_questionnaires.py` | 无写副作用 | `services.get_public_questionnaire_by_slug` | 先切 public read，再处理 submit | 4 |
| `ResolveQuestionnaireSubmitIdentityQuery` | `ResolveQuestionnaireSubmitIdentityQueryDTO { corp_id?, openid, unionid, external_userid, respondent_key, session_identity, request_meta }` | `ResolveQuestionnaireSubmitIdentityResultDTO { identity, matched_by, normalized_identity }` | `services.resolve_questionnaire_submit_identity` -> `domains.questionnaire.service.resolve_questionnaire_submit_identity` | `http/public_questionnaires.py` submit transport、未来 questionnaire submit service 内部 | 调 `application/identity_contact/*` 读 identity；不直接写 | `services.resolve_questionnaire_submit_identity`、`domains.questionnaire.service.resolve_questionnaire_submit_identity` | 先建 query，再把 submit orchestration 改成显式依赖 | 4 |
| `CheckQuestionnaireSubmissionStatusQuery` | `CheckQuestionnaireSubmissionStatusQueryDTO { questionnaire_id, identity }` | `CheckQuestionnaireSubmissionStatusResultDTO { already_submitted, redirect_url? }` | `services.has_questionnaire_submission` -> `domains.questionnaire.service.has_questionnaire_submission` | `http/public_questionnaires.py` | 无写副作用 | `services.has_questionnaire_submission` | public 页面和 submit API 都复用同一 query | 4 |
| `SubmitQuestionnaireCommand` | `SubmitQuestionnaireCommandDTO { slug, answers, hidden_identity, source_params, request_meta }` | `SubmitQuestionnaireCommandResultDTO { success, message, redirect_url, submission_id? }` | `services.submit_questionnaire` -> `domains.questionnaire.service.submit_questionnaire` | `http/public_questionnaires.py` | identity 绑定、SCRM apply、automation bridge、webhook、external push | `services.submit_questionnaire`、`domains.questionnaire.service.submit_questionnaire` | 对外先保持现有 `{success,message,redirect_url}` 结构 | 5 |
| `ApplyQuestionnaireMobileBindingCommand` | `ApplyQuestionnaireMobileBindingCommandDTO { submission_id, submission_snapshot }` | `ApplyQuestionnaireMobileBindingCommandResultDTO { success, skipped, person_id?, external_userid? }` | `services.apply_questionnaire_mobile_binding` -> `domains.questionnaire.service.apply_questionnaire_mobile_binding` | `SubmitQuestionnaireCommand` 内部、历史兼容测试 | 通过 `application/identity_contact/*` 写 identity map / binding | `services.apply_questionnaire_mobile_binding` | 初期只作为 submit 内部 hook，不给 controller 直用 | 5 |
| `ApplyQuestionnaireSubmissionTagsCommand` | `ApplyQuestionnaireSubmissionTagsCommandDTO { submission_id, operator }` | `ApplyQuestionnaireSubmissionTagsCommandResultDTO { ok, applied_tag_codes[], skipped_reason? }` | `services.apply_questionnaire_submission_tags_to_scrm` -> `domains.questionnaire.service.apply_questionnaire_submission_tags_to_scrm` | `SubmitQuestionnaireCommand` 内部、admin debug 兼容链 | 调 WeCom tag apply 与 tag snapshot 持久化 | `services.apply_questionnaire_submission_tags_to_scrm` | 初期仍保持 legacy 行为，但通过正式 command 进入 | 5 |
| `DeliverQuestionnaireExternalPushCommand` | `DeliverQuestionnaireExternalPushCommandDTO { submission_id, submission_snapshot, trigger_source }` | `DeliverQuestionnaireExternalPushCommandResultDTO { ok, status, push_log_id?, failure_reason? }` | `domains.questionnaire.service._deliver_questionnaire_external_push` | `SubmitQuestionnaireCommand` 内部 | 直接对外 HTTP；写 external push logs | `domains.questionnaire.service._deliver_questionnaire_external_push`、`requests.post` 旁路 | transport 与日志都由 command owner 管 | 6 |
| `RetryQuestionnaireExternalPushLogCommand` | `RetryQuestionnaireExternalPushLogCommandDTO { push_log_id, operator }` | `RetryQuestionnaireExternalPushLogCommandResultDTO { ok, retried, latest_log }` | `domains.questionnaire.service.retry_questionnaire_external_push_log` | `domains/admin_console/service.py`、`http/admin_questionnaire_console.py` | 对外 HTTP；写 retry log | `domains.questionnaire.service.retry_questionnaire_external_push_log` | admin console 一律改走 command | 6 |
| `RetryQuestionnaireExternalPushLogsCommand` | `RetryQuestionnaireExternalPushLogsCommandDTO { push_log_ids[], operator }` | `RetryQuestionnaireExternalPushLogsCommandResultDTO { selected_count, retried_count, success_count, failed_count, skipped_count }` | `domains.questionnaire.service.retry_questionnaire_external_push_logs` | `domains/admin_console/service.py`、`http/admin_questionnaire_console.py` | 对外 HTTP；写 retry logs | `domains.questionnaire.service.retry_questionnaire_external_push_logs` | 保持批量 retry 汇总格式 | 6 |
| `ListQuestionnaireExternalPushLogsQuery` | `ListQuestionnaireExternalPushLogsQueryDTO { questionnaire_id?, questionnaire_title?, status?, user_id?, target_url?, limit }` | `ListQuestionnaireExternalPushLogsResultDTO { items[], summary, filters }` | `domains/admin_console.service.build_questionnaire_external_push_logs_payload` / `build_global_questionnaire_external_push_logs_payload` | `http/admin_questionnaire_console.py` | 无直接写副作用；读 external push logs/read model | `domains.admin_console.service.build_questionnaire_external_push_logs_payload` | 先 formalize query，再切 admin console 页面 | 6 |

## 3. 提交与对外副作用的合同口径

### 3.1 Questionnaire 自身 owner

由 questionnaire 自己拥有：

- 问卷配置
- 题目/选项/分数规则
- 答案校验
- outcome 计算
- submission 持久化
- respondent_key 与 source snapshot
- external push payload 的问卷快照部分

### 3.2 Identity 副作用

提交时的身份回填和 mobile 绑定不再由 questionnaire 直接写 identity domain，而是：

- questionnaire 只调用 `application/identity_contact/*`
- `ResolveQuestionnaireSubmitIdentityQuery`
- `ApplyQuestionnaireMobileBindingCommand`

### 3.3 SCRM apply 副作用

问卷决定“这次提交是否应该触发 SCRM apply”，但：

- 不再允许 controller 或 submit orchestration 直接 new `WeComClient`
- 先通过 `ApplyQuestionnaireSubmissionTagsCommand` 收口
- 若后续继续膨胀，再考虑单独拆 `questionnaire_scrm_apply_service`

### 3.4 External push / webhook 副作用

问卷提交后的外部投递统一收口到：

- `DeliverQuestionnaireExternalPushCommand`
- `RetryQuestionnaireExternalPushLogCommand`
- `RetryQuestionnaireExternalPushLogsCommand`

当前 webhook 仍和 external push 同属“submit 后对外投递”范畴，建议由同一外推 owner 承接，不再散在 submit orchestration 中。

## 4. 禁止绕过的旧入口

从 Wave 3 开始，以下入口应视为 legacy bypass：

- `services.create_questionnaire`
- `services.update_questionnaire`
- `services.disable_questionnaire`
- `services.delete_questionnaire`
- `services.export_questionnaire_submissions`
- `services.get_public_questionnaire_by_slug`
- `services.resolve_questionnaire_submit_identity`
- `services.has_questionnaire_submission`
- `services.submit_questionnaire`
- `services.apply_questionnaire_mobile_binding`
- `services.apply_questionnaire_submission_tags_to_scrm`
- `domains.questionnaire.service.retry_questionnaire_external_push_log`
- `domains.questionnaire.service.retry_questionnaire_external_push_logs`
- `domains.questionnaire.preflight_service.build_questionnaire_preflight_payload`

其中：

- 历史兼容 wrapper 可以暂时保留
- 但新的 controller / admin caller / submit bridge 不应继续直接依赖这些旧入口

## 5. 推荐切换顺序

1. `ListQuestionnairesQuery`
2. `GetQuestionnaireDetailQuery`
3. `BuildQuestionnairePreflightQuery`
4. `GetPublicQuestionnaireBySlugQuery`
5. `ResolveQuestionnaireSubmitIdentityQuery`
6. `CheckQuestionnaireSubmissionStatusQuery`
7. `SubmitQuestionnaireCommand`
8. `ApplyQuestionnaireMobileBindingCommand`
9. `ApplyQuestionnaireSubmissionTagsCommand`
10. `ListQuestionnaireExternalPushLogsQuery`
11. `RetryQuestionnaireExternalPushLogCommand`
12. `RetryQuestionnaireExternalPushLogsCommand`
13. `CreateQuestionnaireCommand`
14. `UpdateQuestionnaireCommand`
15. `DisableQuestionnaireCommand`
16. `DeleteQuestionnaireCommand`
17. `ExportQuestionnaireSubmissionsQuery`
18. `GetLatestQuestionnaireSubmitDebugQuery`
19. `DeliverQuestionnaireExternalPushCommand`

这个顺序的含义：

- 先把读入口和 public submit 前置 query 固化
- 再切 submit owner
- 再切 admin CRUD / export
- 最后切 external push admin console 线

## 6. 结论

Wave 3 questionnaire 不应再新增“controller -> services.py -> domains.questionnaire.service”这种链路。

后续所有小 PR 都应该围绕本文定义的 contract 切换 caller，而不是在 legacy service 中继续扩展新逻辑。
