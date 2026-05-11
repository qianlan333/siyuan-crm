# Wave 3 Questionnaire Callers Map

日期：2026-04-20

## 1. 目标

本文只盘点 questionnaire 当前的 caller、旁路和跨 context 写桥接，不改业务代码。

重点回答三个问题：

1. 现在谁在调 questionnaire
2. 这些 caller 目前走的是哪条 legacy 入口
3. 未来应切到哪个 formal application contract

## 2. 主调用方地图

| 线别 | 当前 caller 文件 | 当前直接调用 | 当前 owner 形态 | 未来正式入口 | 备注 |
| --- | --- | --- | --- | --- | --- |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.list_questionnaires` | `services.py` shim -> `domains.questionnaire.service` | `ListQuestionnairesQuery` | 问卷列表 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.get_questionnaire_detail` | 同上 | `GetQuestionnaireDetailQuery` | 问卷详情 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.create_questionnaire` | 同上 | `CreateQuestionnaireCommand` | 新建 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.update_questionnaire` | 同上 | `UpdateQuestionnaireCommand` | 编辑 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.disable_questionnaire` | 同上 | `DisableQuestionnaireCommand` | 启停 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.delete_questionnaire` | 同上 | `DeleteQuestionnaireCommand` | 删除 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.export_questionnaire_submissions` | 同上 | `ExportQuestionnaireSubmissionsQuery` | 导出 |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `services.get_latest_questionnaire_submit_debug` | 同上 | `GetLatestQuestionnaireSubmitDebugQuery` | latest debug |
| admin | `wecom_ability_service/http/admin_questionnaires.py` | `domains.questionnaire.build_questionnaire_preflight_payload` | domain helper 直连 | `BuildQuestionnairePreflightQuery` | 当前唯一明显 domain 直连 |
| public | `wecom_ability_service/http/public_questionnaires.py` | `services.get_public_questionnaire_by_slug` | `services.py` shim -> `domains.questionnaire.service` | `GetPublicQuestionnaireBySlugQuery` | H5 页面/API 共用 |
| public | `wecom_ability_service/http/public_questionnaires.py` | `services.has_questionnaire_submission` | 同上 | `CheckQuestionnaireSubmissionStatusQuery` | public page already-submitted 判断 |
| public | `wecom_ability_service/http/public_questionnaires.py` | `services.submit_questionnaire` | 同上 | `SubmitQuestionnaireCommand` | H5 submit 主入口 |
| public transport | `wecom_ability_service/http/questionnaire_support.py` | Flask session / OAuth helper | transport helper | 保持 transport-only | 这里不应成为 questionnaire domain owner |
| external push admin | `wecom_ability_service/http/admin_questionnaire_console.py` | `domains.admin_console.service.build_questionnaire_*_payload` | admin console glue | `ListQuestionnaireExternalPushLogsQuery` | 外推日志查看 |
| external push admin | `wecom_ability_service/http/admin_questionnaire_console.py` | `domains.admin_console.service.retry_questionnaire_external_push_*` | admin console glue -> questionnaire legacy retry | `RetryQuestionnaireExternalPushLogCommand` / `RetryQuestionnaireExternalPushLogsCommand` | 单条/批量补发 |
| admin glue | `wecom_ability_service/domains/admin_console/service.py` | `list_questionnaires` / `get_questionnaire_detail` / retry helpers | legacy read + action glue | 对应 query/command | questionnaire console payload 仍散在 admin console |
| dashboard read | `wecom_ability_service/domains/admin_dashboard/repo.py` | `list_questionnaires` / `build_questionnaire_preflight_payload` | legacy read | `ListQuestionnairesQuery` / `BuildQuestionnairePreflightQuery` | 相邻读 caller |

## 3. Submit 链路中的内部写桥接

当前 `domains/questionnaire/service.py::submit_questionnaire` 内部，实际串了如下桥接：

| 提交阶段 | 当前实现 | 当前层级 | 建议 formal owner |
| --- | --- | --- | --- |
| identity resolve | `resolve_questionnaire_submit_identity` | questionnaire domain service | `ResolveQuestionnaireSubmitIdentityQuery` |
| mobile rebind | `apply_questionnaire_mobile_binding` -> `application/identity_contact/*` | questionnaire domain service | `ApplyQuestionnaireMobileBindingCommand` |
| SCRM apply | `apply_questionnaire_submission_tags_to_scrm` -> `WeComClient.from_app` / `tags_repo.save_tag_snapshot` | questionnaire domain service | `ApplyQuestionnaireSubmissionTagsCommand` |
| automation bridge | `from ..automation_conversion.service import sync_member_from_questionnaire_submission` | lazy import in questionnaire domain service | future `QuestionnaireAutomationSyncCommand` or keep inside `SubmitQuestionnaireCommand` delegate，先不拆 automation internals |
| webhook | `_fire_questionnaire_submit_webhook` -> `send_outbound_webhook` | questionnaire domain service | 先归入 `DeliverQuestionnaireExternalPushCommand` 的外推 owner，后续可再单列 webhook command |
| external push | `_deliver_questionnaire_external_push` -> `requests.post` + push log | questionnaire domain service | `DeliverQuestionnaireExternalPushCommand` |

## 4. 身份回填调用链地图

### 4.1 当前链路

1. `http/public_questionnaires.py`
   - 组装 payload、source params、request_meta
2. `http/questionnaire_support.py`
   - 处理 session identity、OAuth callback、querystring identity
3. `domains/questionnaire/service.py::submit_questionnaire`
   - `resolve_questionnaire_submit_identity(openid, unionid, external_userid)`
4. `domains/questionnaire/service.py::apply_questionnaire_mobile_binding`
   - 调 `BindExternalContactIdentityCommand`
   - 再调 `ResolvePersonIdentityQuery`

### 4.2 Wave 3 目标链路

1. `http/public_questionnaires.py`
   - parse request
   - 读取 transport identity
   - 调 `SubmitQuestionnaireCommand`
2. `application/questionnaire/*`
   - 调 `ResolveQuestionnaireSubmitIdentityQuery`
   - 内部调用 `application/identity_contact/*`
   - 内部触发 mobile binding / SCRM apply / external push
3. `http/questionnaire_support.py`
   - 只保留 OAuth / session / URL helper

## 5. 当前 legacy 直连点

### 5.1 `services.py` 旁路

当前 questionnaire 相关 legacy symbol：

- `list_questionnaires`
- `list_available_wecom_tags`
- `get_latest_questionnaire_submit_debug`
- `create_questionnaire`
- `get_questionnaire_detail`
- `update_questionnaire`
- `disable_questionnaire`
- `delete_questionnaire_submissions_by_slug`
- `delete_questionnaire`
- `export_questionnaire_submissions`
- `get_public_questionnaire_by_slug`
- `resolve_questionnaire_submit_identity`
- `has_questionnaire_submission`
- `save_questionnaire_submission`
- `apply_questionnaire_mobile_binding`
- `apply_questionnaire_submission_tags_to_scrm`
- `submit_questionnaire`

结论：

- Wave 3 切 caller 时，不能再给这些 symbol 新增依赖
- 它们只允许作为 compatibility shim 存在

### 5.2 Domain/service 直连

当前仍有这些 direct domain import/use：

- `http/admin_questionnaires.py -> domains.questionnaire.build_questionnaire_preflight_payload`
- `http/admin_questionnaire_console.py -> domains.admin_console.service.*`
- `domains/admin_console/service.py -> questionnaire legacy functions`
- `domains/admin_dashboard/repo.py -> questionnaire legacy functions`
- `domains/marketing_automation/service.py -> get_questionnaire_detail`
- `domains/automation_conversion/service.py -> get_questionnaire_detail` / `list_questionnaires`

## 6. Helper 归位地图

| Helper / 函数 | 当前文件 | 未来归位 | 说明 |
| --- | --- | --- | --- |
| `_questionnaire_session_identity` | `http/questionnaire_support.py` | 保留 transport | 读 Flask session，不应进 domain |
| `_questionnaire_request_identity` | `http/questionnaire_support.py` | 保留 transport | querystring/session 拼装 |
| `resolve_questionnaire_submit_identity` | `domains/questionnaire/service.py` | questionnaire identity service | 提交期 identity resolve |
| `_bind_questionnaire_identity` | `domains/questionnaire/service.py` | questionnaire identity service | 对 identity_contact 的 delegate |
| `validate_questionnaire_answers` | `domains/questionnaire/service.py` | questionnaire submit service | 纯问卷校验 |
| `compute_questionnaire_submission_outcome` | `domains/questionnaire/service.py` | questionnaire submit service | 纯问卷 scoring/outcome |
| `has_questionnaire_submission` | `domains/questionnaire/service.py` | questionnaire submit service | duplicate check |
| `save_questionnaire_submission` | `domains/questionnaire/service.py` | questionnaire submit service | submission persistence |
| `apply_questionnaire_mobile_binding` | `domains/questionnaire/service.py` | questionnaire submit service | submit 后 identity side effect |
| `apply_questionnaire_submission_tags_to_scrm` | `domains/questionnaire/service.py` | questionnaire submit service | 先挂 submit owner，后续视规模再细拆 |
| `_build_questionnaire_external_push_payload` | `domains/questionnaire/service.py` | questionnaire external push service | 外推 payload |
| `retry_questionnaire_external_push_log(s)` | `domains/questionnaire/service.py` | questionnaire external push service | retry owner |

## 7. 推荐切换顺序

1. `http/public_questionnaires.py`
   - 先切 `GetPublicQuestionnaireBySlugQuery`
   - 再切 `CheckQuestionnaireSubmissionStatusQuery`
   - 最后切 `SubmitQuestionnaireCommand`
2. `http/admin_questionnaires.py`
   - 切 CRUD / export / debug / preflight
3. `http/admin_questionnaire_console.py`
   - 切 external push logs / retry
4. `domains/admin_console/service.py`
   - 从 payload builder 里去掉 questionnaire legacy action 调用
5. `domains/admin_dashboard/repo.py`
   - 切 questionnaire read/preflight query
6. `domains/marketing_automation/service.py` / `domains/automation_conversion/service.py`
   - 这两者只做 questionnaire read consumer 对齐，不在 Wave 3 第一批里重构内部实现

## 8. 结论

当前 questionnaire 的主要问题不是 caller 太少，而是 caller 被分散在：

- `http/admin_questionnaires.py`
- `http/public_questionnaires.py`
- `http/admin_questionnaire_console.py`
- `domains/admin_console/service.py`
- `domains/admin_dashboard/repo.py`
- `services.py`

Wave 3 应先把这些 caller 逐一对齐到 formal application contract，再做 `domains/questionnaire/service.py` 的真正瘦身。
