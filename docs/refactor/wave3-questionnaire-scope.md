# Wave 3 Questionnaire Scope

日期：2026-04-20

## 1. 目标

Wave 3 的第一条主线只处理 `questionnaire` 这个 context 的范围盘点和合同化设计，不改业务代码，不进入 `automation_conversion` / `customer_pulse` / `followup_orchestrator` 内部拆分。

本轮要解决的不是“继续扩一份宏观蓝图”，而是把当前问卷链路里已经混在一起的 4 条线先拆清：

1. admin 线
2. public 线
3. submit 线
4. external push 线

## 2. 当前现状

当前问卷逻辑的主要问题不是单个函数太复杂，而是 owner 混乱：

- `wecom_ability_service/domains/questionnaire/service.py`
  - 同时承载 admin CRUD、public read、问题校验/评分、身份解析、提交流程、SCRM 打标、external push、webhook。
- `wecom_ability_service/http/public_questionnaires.py`
  - 同时承载 H5 页面渲染、OAuth/session 身份接力、提交入口。
- `wecom_ability_service/http/admin_questionnaires.py`
  - 仍通过 `services.py` 走问卷 CRUD / export / debug。
- `wecom_ability_service/http/admin_questionnaire_console.py`
  - 承接 external push log 查看与 retry，但真正 payload 组装又落在 `domains/admin_console/service.py`。
- `wecom_ability_service/http/questionnaire_support.py`
  - 现状是 transport helper，不是 domain service；用户口径里提到的 `wecom_ability_service/questionnaire_support.py`，仓库实际文件路径是 `wecom_ability_service/http/questionnaire_support.py`。
- `wecom_ability_service/services.py`
  - 仍保留 `submit_questionnaire`、`apply_questionnaire_mobile_binding`、`apply_questionnaire_submission_tags_to_scrm` 等 legacy wrapper，是当前最明显的旁路面。

## 3. 四条线的现状边界

### 3.1 Admin 线

当前文件：

- `wecom_ability_service/http/admin_questionnaires.py`
- `wecom_ability_service/domains/questionnaire/service.py`
- `wecom_ability_service/domains/questionnaire/preflight_service.py`

当前职责：

- 问卷列表
- 问卷详情
- 创建 / 更新 / 禁用 / 删除
- 导出提交记录
- latest submit debug
- admin preflight

当前问题：

- controller 仍主要经 `services.py` 进入 domain
- preflight helper 直接从 domain 暴露，没有 formal application query
- `list_available_wecom_tags` 和 identity map availability 其实已经跨到其他 context / integration 读面

### 3.2 Public 线

当前文件：

- `wecom_ability_service/http/public_questionnaires.py`
- `wecom_ability_service/http/questionnaire_support.py`

当前职责：

- H5 页面渲染
- WeChat OAuth start/callback
- session identity 写入与读取
- request/querystring 身份拼装
- public questionnaire detail API
- submit API transport glue

当前问题：

- transport helper 和 submit/use-case 仍未切开
- `public_questionnaires.py` 通过 `services.py` 直接进问卷提交流程
- session/openid/unionid/respondent_key 的链路没有 formal application contract，只是被 controller 直接拼装后传入 legacy service

### 3.3 Submit 线

当前文件：

- `wecom_ability_service/domains/questionnaire/service.py`
- `wecom_ability_service/services.py`

当前职责：

- identity resolve
- duplicate check
- answer validate
- outcome compute
- submission save
- mobile binding
- SCRM 打标
- automation sync bridge
- webhook
- external push

当前问题：

- `submit_questionnaire` 是当前最重的混合入口
- 一次提交内同时触发 identity / SCRM / automation / external HTTP
- domain service 仍直接 import `Flask current_app` / `session` / `requests`
- 现有提交链路已经不是纯 questionnaire domain，而是 questionnaire orchestration

### 3.4 External Push 线

当前文件：

- `wecom_ability_service/domains/questionnaire/service.py`
- `wecom_ability_service/http/admin_questionnaire_console.py`
- `wecom_ability_service/domains/admin_console/service.py`
- `wecom_ability_service/domains/admin_console/repo.py`

当前职责：

- build external push payload
- 写 external push logs
- 发 HTTP 请求
- retry 单条 / 批量
- admin 控制台查看日志与补发

当前问题：

- transport、日志模型、admin 展示、retry policy 仍混在 legacy domain + admin console service
- admin 线通过 `domains/admin_console/service.py` 直接消费 questionnaire 的 retry 实现，没有 formal application API

## 4. 身份回填链路

当前 public submit 的身份链路如下：

1. `http/public_questionnaires.py::h5_wechat_oauth_callback`
   - 通过 `http/questionnaire_support.py::_fetch_wechat_userinfo` 获取 openid / unionid
   - 写 session `questionnaire_h5_identity`
2. `http/questionnaire_support.py`
   - `_questionnaire_session_identity`
   - `_questionnaire_request_identity`
   - `_questionnaire_source_params`
   - 负责把 session/querystring/source params 暂时拼成 transport payload
3. `domains/questionnaire/service.py::submit_questionnaire`
   - 调 `resolve_questionnaire_submit_identity`
   - 当前优先级是 `unionid -> openid -> external_userid`
   - 根据 request identity + session identity 生成 `respondent_key`
4. `apply_questionnaire_mobile_binding`
   - 若问卷答案里有 mobile 且 submission 已拿到 `external_userid`
   - 则调用 `application/identity_contact/*` 做 bind + re-resolve

Wave 3 的结论：

- OAuth / session / request param 处理仍属于 transport 层，应继续留在 `http/questionnaire_support.py`
- 真正的 identity resolve / rebind / submit-time identity normalization 应收口到 questionnaire 的正式 application contract
- `questionnaire` 只能通过 `application/identity_contact/*` 调 identity，不能再回头 import identity domain/service

## 5. `questionnaire -> SCRM apply / external push` 边界

### 5.1 Questionnaire 自己应该拥有的部分

- 问卷定义与问题/分数规则
- 提交时的答案验证与结果计算
- submission record / answer snapshots / respondent_key
- external push payload 中与问卷自身有关的快照字段
- retry eligibility、retry attempt、push log 业务状态

### 5.2 不应继续内联在 submit orchestration 里的部分

- `WeComClient.from_app().mark_external_contact_tags(...)`
- `tags_repo.save_tag_snapshot(...)`
- `requests.post(...)`
- `send_outbound_webhook(...)`
- `from ..automation_conversion.service import sync_member_from_questionnaire_submission`

Wave 3 的边界口径：

- 问卷提交是否触发 SCRM apply，由 questionnaire submit owner 决定
- 但真正的 SCRM integration 发送，不应再直接写在 submit orchestration 里
- 问卷提交是否触发 external push / webhook，也由 questionnaire submit owner 决定
- 但 transport 和 delivery 应迁入专门的 external push service / adapter
- automation bridge 这轮只盘点，不进入 `automation_conversion` 内部拆分；先把 bridge owner 从 legacy submit service 提升成显式 contract

## 6. 建议的内部服务拆分

### 6.1 Questionnaire Identity Service

应吸收的 helper / use-case：

- `resolve_questionnaire_submit_identity`
- `_resolve_external_contact_identity_payload`
- `_resolve_questionnaire_person_identity`
- `_bind_questionnaire_identity`

边界说明：

- 只负责“提交时应该把谁认作当前 respondent”
- 只允许通过 `application/identity_contact/*` 读写 identity
- 不承接 OAuth / session / request parsing

不应放进去的 helper：

- `_questionnaire_session_identity`
- `_questionnaire_request_identity`
- `_wechat_oauth_*`
- `_fetch_wechat_userinfo`

这些仍属于 transport 层的 `http/questionnaire_support.py`

### 6.2 Questionnaire Submit Service

应吸收的 helper / use-case：

- `validate_questionnaire_answers`
- `compute_questionnaire_submission_outcome`
- `has_questionnaire_submission`
- `save_questionnaire_submission`
- `_extract_mobile_snapshot_from_validated_answers`
- `_build_respondent_key`
- `submit_questionnaire`
- `apply_questionnaire_mobile_binding`
- `apply_questionnaire_submission_tags_to_scrm`

边界说明：

- 这是 Wave 3 的主 owner
- 负责一次提交内的 orchestration
- 允许调用 questionnaire identity service 和 questionnaire external push service
- 不应直接承接 HTTP/session 细节

### 6.3 Questionnaire External Push Service

应吸收的 helper / use-case：

- `_questionnaire_submit_webhook_payload`
- `is_questionnaire_external_push_global_enabled`
- `_build_questionnaire_external_push_payload`
- `_create_questionnaire_external_push_log`
- `_safe_create_questionnaire_external_push_log`
- `_get_questionnaire_external_push_log`
- `_count_questionnaire_external_push_retry_logs`
- `_execute_questionnaire_external_push_request`
- `_deliver_questionnaire_external_push`
- `retry_questionnaire_external_push_log`
- `retry_questionnaire_external_push_logs`
- `_fire_questionnaire_submit_webhook`

边界说明：

- 负责 submit 之后的对外投递
- 负责 payload、日志、retry policy
- admin console 侧查看与 retry 也应只通过它的正式 query/command

## 7. 当前 legacy 直连点

### 7.1 HTTP / admin caller 侧

- `http/admin_questionnaires.py -> services.py::{list_questionnaires,get_questionnaire_detail,create_questionnaire,update_questionnaire,disable_questionnaire,delete_questionnaire,export_questionnaire_submissions,get_latest_questionnaire_submit_debug}`
- `http/admin_questionnaires.py -> domains.questionnaire.build_questionnaire_preflight_payload`
- `http/public_questionnaires.py -> services.py::{get_public_questionnaire_by_slug,has_questionnaire_submission,submit_questionnaire}`
- `http/admin_questionnaire_console.py -> domains.admin_console.service::{build_questionnaire_*_payload,retry_questionnaire_external_push_*}`

### 7.2 Submit orchestration 内部

- `domains/questionnaire/service.py -> application/identity_contact/*`
- `domains/questionnaire/service.py -> WeComClient.from_app()`
- `domains/questionnaire/service.py -> tags_repo.save_tag_snapshot`
- `domains/questionnaire/service.py -> send_outbound_webhook`
- `domains/questionnaire/service.py -> requests.post`
- `domains/questionnaire/service.py -> lazy import automation_conversion.sync_member_from_questionnaire_submission`

### 7.3 相邻 consumer

- `domains/admin_console/service.py`
- `domains/admin_dashboard/repo.py`
- `domains/marketing_automation/service.py`
- `domains/automation_conversion/service.py`

其中：

- `admin_console` 与 `admin_dashboard` 以 read/admin console 方式消费 questionnaire
- `marketing_automation` 与 `automation_conversion` 是相邻业务 context，对 questionnaire 有明显读依赖
- `automation_conversion.sync_member_from_questionnaire_submission` 是 submit 线当前唯一明确的跨 context 写桥接

## 8. Wave 3 Questionnaire 的正式边界结论

Wave 3 不做 questionnaire 的“内部一次性大拆”，只先建立如下正式 owner：

1. admin owner
   - 问卷 CRUD / preflight / export / latest-submit-debug
2. public owner
   - public questionnaire read + submit transport glue
3. submit owner
   - identity normalization + duplicate check + save + post-submit side effects 编排
4. external push owner
   - payload / log / retry / admin external push console

Wave 3 的 application contract 要先把 caller 收到正式 API，再决定 `domains/questionnaire/service.py` 内部进一步拆成几个文件。

## 9. 本轮明确不进入的范围

- `automation_conversion` 内部拆分
- `customer_pulse` 内部拆分
- `followup_orchestrator` 内部拆分
- schema / SQL migration
- admin_console 整体重构
- marketing_automation 对 questionnaire 读面的彻底改造

## 10. 结论

Questionnaire 在 Wave 3 的第一阶段不是“继续扩一个大 service”，而是：

- 先把 admin / public / submit / external push 四条线单独命名
- 先把 identity、SCRM apply、automation bridge、external push 都从“隐式 side effect”变成“显式 contract”
- 先让 `http/*` 和 `services.py` 不再作为默认 owner

这为后续 PR 小步切换提供了稳定边界，同时不破坏 Wave 2 已完成的 identity / user_ops 主线成果。
