# Wave 3 Questionnaire Test Plan

日期：2026-04-20

## 1. 目标

Wave 3 questionnaire 进入 caller cutover 前，先冻结当前 contract，避免把以下行为在重构中误伤：

- admin CRUD / export / preflight
- public H5 render / OAuth / session identity
- submit duplicate check / save / mobile binding / SCRM apply
- external push / webhook / admin retry

本文只做测试冻结计划，不修改测试代码。

## 2. 已有测试覆盖

### 2.1 身份回填

现有文件：

- `tests/test_questionnaire_identity_resolution.py`

已冻结行为：

- `unionid -> openid -> external_userid` 解析优先级
- `apply_questionnaire_mobile_binding` 通过 `application/identity_contact/*` 做 bind + resolve

### 2.2 Public / Submit / External Push

现有文件：

- `tests/test_api.py`

已覆盖的关键行为：

- H5 页面渲染
- WeChat browser gate
- OAuth callback 写 session identity
- `snsapi_userinfo` 补 unionid
- public get 返回 `already_submitted`
- duplicate submit 拒绝
- mobile snapshot 落库
- required mobile question 校验
- external push enabled / disabled / global off / timeout / non-200 / retry
- questionnaire submit webhook 成功 / 失败 / retry
- mobile bind 后 identity 更新

### 2.3 Admin Console External Push

现有文件：

- `tests/test_admin_console_phase4.py`

已覆盖的关键行为：

- 问卷详情页渲染
- external push logs 页面过滤
- failed_current 过滤
- global external push logs 页面
- 单条 retry / 批量 retry UI 与结果

### 2.4 Automation Bridge Guard

现有文件：

- `tests/test_automation_facade_guards.py`

已冻结的关键行为：

- `submit_questionnaire` 里当前仍通过 lazy import 进入 `automation_conversion.sync_member_from_questionnaire_submission`

这条测试很关键，因为 Wave 3 早期 PR 如果切 submit owner，需要显式处理这条 guard，而不能无意间改变 automation bridge 入口。

### 2.5 问卷对营销自动化的读面兼容

现有文件：

- `tests/test_marketing_automation.py`

已覆盖的关键行为：

- questionnaire 作为 segmentation / questionnaire truth 的来源
- 根据 questionnaire submission 进入后续 automation path

## 3. 需要冻结的高风险行为

### 3.1 Admin 线

必须冻结：

- 问卷创建 / 更新 / 禁用 / 删除 的返回结构
- preflight payload 结构
- export columns / rows 稳定性
- latest submit debug payload 稳定性

建议测试文件：

- 现有 `tests/test_api.py` 中 `/api/admin/questionnaires` 相关用例
- 后续新增 `tests/test_questionnaire_admin_contract.py`

### 3.2 Public 线

必须冻结：

- H5 页面 hidden identity/source fields
- 非微信浏览器的 page/api gate
- OAuth callback 的 state round-trip
- session identity 覆盖 querystring 的优先级
- `openid` / `unionid` / `external_userid` / `respondent_key` 的回填结构

建议测试文件：

- 现有 `tests/test_api.py` questionnaire H5 段
- 后续新增 `tests/test_questionnaire_public_contract.py`

### 3.3 Submit 线

必须冻结：

- `unionid -> openid -> external_userid` 解析优先级
- duplicate submit 不串人
- respondent_key 稳定性
- mobile question snapshot 落库
- mobile binding 后 external_userid / mobile overwrite 行为
- 提交成功时核心返回结构 `{success, message, redirect_url}`
- SCRM apply 的 skip / apply path

建议测试文件：

- `tests/test_questionnaire_identity_resolution.py`
- `tests/test_api.py`
- 后续新增 `tests/test_questionnaire_submit_contract.py`

### 3.4 External Push 线

必须冻结：

- external push payload 关键字段
- global switch off 时 submit 仍成功
- non-200 / timeout / exception 只记录失败，不打断 submit
- retry 单条 / 批量的日志与汇总结构
- questionnaire submit webhook 不影响主提交流程

建议测试文件：

- `tests/test_api.py`
- `tests/test_admin_console_phase4.py`
- 后续新增 `tests/test_questionnaire_external_push_contract.py`

## 4. 推荐冻结矩阵

| 风险点 | 当前主要测试 | 是否已部分覆盖 | 后续建议补强 |
| --- | --- | --- | --- |
| OAuth/session/openid/unionid 回填 | `tests/test_api.py`、`tests/test_questionnaire_identity_resolution.py` | 是 | 增加 contract 文件，把 identity precedence 与 session overwrite 固化成单独测试组 |
| duplicate submit / already_submitted | `tests/test_api.py` | 是 | public get 与 submit path 各自保留一条冻结断言 |
| submission 落库字段 | `tests/test_api.py` | 是 | 增加 respondent_key / matched_by / source params 的明确断言 |
| mobile binding / rebind | `tests/test_questionnaire_identity_resolution.py`、`tests/test_api.py` | 是 | 单独冻结 bind 后 resolve 的输出字段 |
| SCRM apply | `tests/test_api.py` | 部分 | 需要一个更聚焦的 contract 文件冻结 apply success / skipped / failure log |
| external push success/fail/timeout/retry | `tests/test_api.py`、`tests/test_admin_console_phase4.py` | 是 | 把 payload 关键字段与 retry summary 冻结得更显式 |
| automation bridge lazy import | `tests/test_automation_facade_guards.py` | 是 | 在真正切换 formal contract 前保留；切换那一 PR 再同步改 guard |
| marketing automation questionnaire 读兼容 | `tests/test_marketing_automation.py` | 是 | 仅在 questionnaire read owner 切换时跑相关子集，不需要本轮全量新增 |

## 5. Wave 3 各 PR 的最小回归集

### PR 1：Questionnaire Contract Pack

目标：

- 只落 docs 与后续 contract 口径

最小回归集：

- 无需跑测试；如后续补测试文件，则先跑
  - `tests/test_http_registration_contract.py`
  - `tests/test_questionnaire_identity_resolution.py`

### PR 2：Questionnaire Application Skeleton + services shim delegation

最小回归集：

- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`
- 建议新增并跑 `tests/test_questionnaire_application_contract.py`

### PR 3：Public / Submit Cutover

最小回归集：

- `tests/test_questionnaire_identity_resolution.py`
- `tests/test_api.py -k "questionnaire and (oauth or submit or external_push or webhook)"`
- `tests/test_automation_facade_guards.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### PR 4：Admin CRUD / Export / Preflight Cutover

最小回归集：

- `tests/test_api.py -k "admin_questionnaire or questionnaire_preflight or questionnaire_export"`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### PR 5：External Push Console Cutover

最小回归集：

- `tests/test_api.py -k "questionnaire_external_push or questionnaire_submit_webhook"`
- `tests/test_admin_console_phase4.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### PR 6：Questionnaire Closeout

最小回归集：

- `tests/test_questionnaire_identity_resolution.py`
- `tests/test_api.py -k "questionnaire or admin_questionnaire"`
- `tests/test_admin_console_phase4.py`
- `tests/test_automation_facade_guards.py`
- `tests/test_marketing_automation.py -k "questionnaire"`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

## 6. 需要新增但本轮不创建的测试文件

建议后续新增：

- `tests/test_questionnaire_application_contract.py`
  - 验证 application/questionnaire skeleton 可 import、legacy delegate 不回头依赖 http/*
- `tests/test_questionnaire_admin_contract.py`
  - admin CRUD / export / preflight / latest debug
- `tests/test_questionnaire_public_contract.py`
  - public read / H5 render / OAuth/session identity
- `tests/test_questionnaire_submit_contract.py`
  - duplicate / save / mobile binding / SCRM apply
- `tests/test_questionnaire_external_push_contract.py`
  - payload / log / retry / webhook

## 7. 结论

Questionnaire 的 Wave 3 不缺“测试数量”，缺的是：

- 把现有覆盖按 admin/public/submit/external push 四条线重新归档
- 把 identity precedence、submit side effects、external push retry 明确冻成 contract
- 在切 caller 之前先把 automation bridge guard 留住

后续 PR 必须先对照本文冻结面决定增补哪条测试，再动 wiring。
