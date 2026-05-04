# Questionnaire Closeout

日期：2026-04-21

## 结论

`questionnaire` 这一轮独立收口已经完成主线 owner 提升：正式 owner 进入 `wecom_ability_service/application/questionnaire/*`，controller 主入口已不再把 `services.py` 或 `domains/questionnaire/service.py` 当作默认业务入口。当前仓库里仍存在少量 compatibility shim 和相邻 context 的 legacy read/bridge 依赖，但它们已不构成 Wave 3 closeout 阻塞。

## 已完成的主线

### 1. admin

- 当前 owner 文件
  - `wecom_ability_service/http/admin_questionnaires.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
- 当前已完成
  - 后台 list / detail / preflight / latest-submit-debug 已进入正式 query
  - create / update / disable / delete 已进入正式 command
  - export 已进入正式 query
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::{list_questionnaires,list_available_wecom_tags,get_latest_questionnaire_submit_debug,create_questionnaire,get_questionnaire_detail,update_questionnaire,disable_questionnaire,delete_questionnaire,export_questionnaire_submissions}`
  - `wecom_ability_service/domains/admin_console/service.py::{build_questionnaire_index_payload,build_questionnaire_detail_payload,save_questionnaire_editor,toggle_questionnaire_disabled}` 仍作为 admin console glue 复用这些 shim
- 已知技术债
  - admin console 的问卷首页、详情页、编辑台仍通过 `domains/admin_console/service.py` 走兼容 glue，不是当前 Wave 3 closeout 的阻塞项
  - `domains/questionnaire/preflight_service.py` 仍是内部 delegate target，尚未进一步内聚到更细的问卷子模块

### 2. public

- 当前 owner 文件
  - `wecom_ability_service/http/public_questionnaires.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
  - `wecom_ability_service/http/questionnaire_support.py`
- 当前已完成
  - public questionnaire read 已进入 `GetPublicQuestionnaireBySlugQuery`
  - 重复提交探测已进入 `HasQuestionnaireSubmissionQuery`
  - public submit 已进入 `SubmitQuestionnaireCommand`
  - OAuth callback 的身份回填已经通过 application bridge 完成，transport 只保留 session / redirect glue
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::QuestionnaireAlreadySubmittedError`
  - `wecom_ability_service/http/questionnaire_support.py` 中的 session / state / OAuth transport helper
- 已知技术债
  - `public_questionnaires.py` 仍需要兼容导入 `QuestionnaireAlreadySubmittedError`，这是历史提交错误语义的稳定点
  - `questionnaire_support.py` 仍保留 `_fetch_wechat_userinfo` 一类 transport helper，但它已经不再承载提交身份决策

### 3. submit

- 当前 owner 文件
  - `wecom_ability_service/application/questionnaire/commands.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/_legacy_delegate.py`
- 当前已完成
  - `SubmitQuestionnaireCommand` 已成为正式提交入口
  - `ResolveQuestionnaireRespondentIdentityQuery` / `ResolveQuestionnaireSubmitIdentityQuery` 已成为身份桥接 owner
  - controller 不再在 transport 层拼装 identity / save / SCRM apply 编排
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::{resolve_questionnaire_submit_identity,has_questionnaire_submission,save_questionnaire_submission,apply_questionnaire_mobile_binding,apply_questionnaire_result_to_scrm,submit_questionnaire}`
  - `wecom_ability_service/services.py::_bind_questionnaire_domain`
- 已知技术债
  - `application/questionnaire/*` 当前仍通过 `_legacy_delegate` 调 `domains/questionnaire/service.py`，owner 已 formalize，但内部实现还未细拆
  - 提交流程内部仍是 legacy mixed orchestration，后续若进入下一轮问卷内部治理，应以 `submit` / `identity bridge` / `external push` 为拆分边界

### 4. external push

- 当前 owner 文件
  - `wecom_ability_service/http/admin_questionnaire_console.py`
  - `wecom_ability_service/application/questionnaire/queries.py`
  - `wecom_ability_service/application/questionnaire/commands.py`
- 当前已完成
  - questionnaire-scoped / global external-push log 查询已进入正式 query
  - single / batch retry 已进入 `RetryQuestionnaireExternalPushCommand`
  - admin external-push console 不再直连 legacy questionnaire retry service
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::{retry_questionnaire_external_push_log,retry_questionnaire_external_push_logs}`
  - `wecom_ability_service/domains/admin_console/service.py::{build_questionnaire_external_push_logs_payload,build_global_questionnaire_external_push_logs_payload,retry_questionnaire_external_push_log_for_console,retry_questionnaire_external_push_logs_for_console}` 仍保留兼容 façade，但内部已转调 application owner
- 已知技术债
  - external push 的真正 delivery / retry 实现仍落在 `domains/questionnaire/service.py` 的 legacy delegate
  - admin console 其余问卷页面仍未完全改成只调 `application/questionnaire/*`

## `services.py` 当前定位

- questionnaire 相关 symbol 已退化为 compatibility wrapper
- `services.py` 不再承担 questionnaire 的主要业务入口 owner
- 仍保留的存在理由
  - 旧调用方兼容
  - monkeypatch / DI 稳定面
  - `QuestionnaireAlreadySubmittedError` 等历史异常语义兼容

## Closeout 判断

从 owner 归边、caller cutover、shim 缩面、guardrail 覆盖这 4 个维度看，questionnaire 主线已经满足本轮 closeout 条件。后续如继续演进，应进入下一轮“问卷内部实现拆分”，而不是回退到 `services.py` 或 controller 混编排。
