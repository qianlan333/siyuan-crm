# Questionnaire Primitive Boundary

日期：2026-04-21

## 目标

从本文件开始，questionnaire 相关 helper / primitive 分成 3 类：

1. formal application API
2. transport-only helper
3. internal primitive / legacy delegate

只有第 1 类可以作为新的 caller 入口。第 2、3 类都不应再被外层 caller 当作业务入口直接依赖。

## 1. Formal application API

以下入口是当前唯一正式 owner：

- `wecom_ability_service/application/questionnaire/queries.py`
  - `ListQuestionnairesQuery`
  - `ListAvailableWeComTagsQuery`
  - `BuildQuestionnairePreflightQuery`
  - `GetLatestQuestionnaireSubmitDebugQuery`
  - `GetQuestionnaireDetailQuery`
  - `ExportQuestionnaireSubmissionsQuery`
  - `GetPublicQuestionnaireBySlugQuery`
  - `ResolveQuestionnaireSubmitIdentityQuery`
  - `ResolveQuestionnaireRespondentIdentityQuery`
  - `HasQuestionnaireSubmissionQuery`
  - `GetQuestionnaireExternalPushLogsQuery`
  - `GetGlobalQuestionnaireExternalPushLogsQuery`
- `wecom_ability_service/application/questionnaire/commands.py`
  - `CreateOrUpdateQuestionnaireCommand`
  - `DisableQuestionnaireCommand`
  - `DeleteQuestionnaireCommand`
  - `SubmitQuestionnaireCommand`
  - `CompleteQuestionnaireOauthCallbackCommand`
  - `RetryQuestionnaireExternalPushCommand`
  - 以及内部仍被 formal API 组合调用的 save / apply / retry command

## 2. Transport-only helper

下列 helper 只允许在 transport glue 中使用，不得被外层业务 caller 当作 questionnaire 业务 API：

| helper | 当前文件 | 允许调用范围 | 禁止调用范围 |
| --- | --- | --- | --- |
| `_questionnaire_session_identity` | `wecom_ability_service/http/questionnaire_support.py` | `http/public_questionnaires.py`、`http/questionnaire_support.py` | `application/*`、`domains/admin_console/*`、`services.py` |
| `_questionnaire_request_identity_hints` | `wecom_ability_service/http/questionnaire_support.py` | `http/public_questionnaires.py` | `application/*`、其它 `http/*` caller |
| `_questionnaire_source_params` | `wecom_ability_service/http/questionnaire_support.py` | `http/public_questionnaires.py` | `application/*`、`domains/*` |
| `_encode_oauth_state` / `_decode_oauth_state` | `wecom_ability_service/http/questionnaire_support.py` | `http/public_questionnaires.py`、`http/questionnaire_support.py` | `application/*`、`domains/*` |
| `_wechat_oauth_*` helper | `wecom_ability_service/http/questionnaire_support.py` | questionnaire OAuth transport glue | 其它业务 caller |
| `_attach_questionnaire_links` | `wecom_ability_service/http/questionnaire_support.py` | `http/admin_questionnaires.py` 这类 response shaping | `application/*`、`domains/questionnaire/service.py` |

## 3. Internal primitive / legacy delegate

下列 symbol 当前仍存在，但从现在开始只视为 internal primitive 或 compatibility façade：

| symbol | 当前位置 | 允许调用范围 | 禁止调用范围 | 备注 |
| --- | --- | --- | --- | --- |
| `validate_questionnaire_answers` | `wecom_ability_service/domains/questionnaire/service.py` | `application/questionnaire/*`、`domains/questionnaire/*` 内部 | `http/*`、`domains/admin_console/*`、相邻 context 新 caller | 仅作为 submit orchestration 的 legacy delegate |
| `compute_questionnaire_submission_outcome` | `wecom_ability_service/domains/questionnaire/service.py` | `application/questionnaire/*`、`domains/questionnaire/*` 内部 | 同上 | 仅作为 submit/outcome 计算 primitive |
| `save_questionnaire_submission` | `wecom_ability_service/domains/questionnaire/service.py` 与 `services.py` shim | `application/questionnaire/*`、`domains/questionnaire/*` 内部 | `http/*`、admin console / support / automation caller | 不得再作为 controller 入口 |
| `apply_questionnaire_mobile_binding` | `wecom_ability_service/domains/questionnaire/service.py` 与 `services.py` shim | `application/questionnaire/*`、`domains/questionnaire/*` 内部 | `http/*`、外层 admin / public caller | 绑定副作用应由 submit command 内部触发 |
| `apply_questionnaire_submission_tags_to_scrm` / `apply_questionnaire_result_to_scrm` | `wecom_ability_service/domains/questionnaire/service.py` 与 `services.py` shim | `application/questionnaire/*`、`domains/questionnaire/*` 内部 | `http/*`、admin console / automation caller | SCRM apply 只允许通过正式 application command 编排 |
| `retry_questionnaire_external_push_log` / `retry_questionnaire_external_push_logs` | `wecom_ability_service/domains/questionnaire/service.py` 与 `services.py` shim | `application/questionnaire/*`、`domains/questionnaire/*` 内部 | `http/admin_questionnaire_console.py`、`domains/admin_console/service.py` 新 caller | 外层 retry 统一走 `RetryQuestionnaireExternalPushCommand` |
| `_bind_questionnaire_domain` | `wecom_ability_service/services.py` | `services.py` compatibility layer 内部 | 任意外层 caller | runtime 注入点，不是业务入口 |

## 4. Compatibility shim 边界

`wecom_ability_service/services.py` 中的 questionnaire symbol 从现在开始一律视为 compatibility-only：

- `list_questionnaires`
- `list_available_wecom_tags`
- `get_latest_questionnaire_submit_debug`
- `create_questionnaire`
- `get_questionnaire_detail`
- `update_questionnaire`
- `disable_questionnaire`
- `delete_questionnaire`
- `export_questionnaire_submissions`
- `get_public_questionnaire_by_slug`
- `has_questionnaire_submission`
- `resolve_questionnaire_submit_identity`
- `save_questionnaire_submission`
- `apply_questionnaire_mobile_binding`
- `apply_questionnaire_result_to_scrm`
- `submit_questionnaire`
- `retry_questionnaire_external_push_log`
- `retry_questionnaire_external_push_logs`

允许范围：

- 旧调用方兼容
- monkeypatch / DI 兼容
- 过渡期历史测试稳定面

禁止范围：

- 新增 `http/*` caller
- 新增 admin console / support / automation caller
- 新增跨 context bridge

## 5. 结论

对 questionnaire 来说，新的调用方向应当永远是：

`caller -> application/questionnaire/* -> legacy delegate（如仍需要）`

而不是：

`caller -> services.py`

或：

`caller -> domains/questionnaire/service.py`
