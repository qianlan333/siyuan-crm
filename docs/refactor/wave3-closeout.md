# Wave 3 Closeout

日期：2026-04-21

## 总结

Wave 3 的目标是让 `questionnaire` 从 legacy `services.py` + `domains/questionnaire/service.py` 的混合入口，回到正式 `application/questionnaire/*` owner。按当前仓库状态，这一目标已经完成：formal application API 已建立，主 caller 已完成 cutover，`services.py` 已退为 compatibility shim，问卷相关 guardrail 和冻结回归已覆盖主线。

## 主线验收

| 主线 | formal application API 是否已建立 | caller 是否已切走 legacy questionnaire 主入口 | `services.py` 是否已不再承担主要入口 | guardrail / contract 是否已覆盖 | 备注 |
| --- | --- | --- | --- | --- | --- |
| admin | 是，`wecom_ability_service/application/questionnaire/queries.py` 与 `commands.py` 已建立 CRUD / export / preflight 正式入口 | 是，`wecom_ability_service/http/admin_questionnaires.py` 已切到 application owner | 是，只保留 compatibility wrapper | 是，HTTP 注册契约、API 冻结与本次 questionnaire caller guardrail 已覆盖 | admin console 问卷壳层仍有 compatibility glue，但不再是主 controller owner |
| public | 是，public read / submit / OAuth bridge 已有正式 query / command | 是，`wecom_ability_service/http/public_questionnaires.py` 已切到 application owner | 是，只保留 `QuestionnaireAlreadySubmittedError` 等兼容点 | 是，identity resolution / API 回归已冻结 | `http/questionnaire_support.py` 仍保留 transport helper，这是设计内边界 |
| submit | 是，`SubmitQuestionnaireCommand` / `ResolveQuestionnaireRespondentIdentityQuery` 已建立 | 是，controller 不再直连 `services.submit_questionnaire` | 是，shim 只做兼容委托 | 是，questionnaire identity 与 public submit 回归已覆盖 | 内部实现仍通过 legacy delegate 调 `domains/questionnaire/service.py` |
| external push | 是，`RetryQuestionnaireExternalPushCommand`、`GetQuestionnaireExternalPushLogsQuery`、`GetGlobalQuestionnaireExternalPushLogsQuery` 已建立 | 是，`http/admin_questionnaire_console.py` 不再直连 legacy retry/helper | 是，只保留 retry compatibility shim | 是，external push contract 与 console API 回归已覆盖 | delivery / retry 内部 executor 仍在 legacy delegate，不阻塞 closeout |

## 已完成项

- `application/questionnaire/*` 已建立 formal API、DTO 和 legacy delegate 边界
- `services.py` 的 questionnaire symbols 已全部退成 wrapper / shim
- `http/public_questionnaires.py` 已收口到 application owner
- `http/questionnaire_support.py` 已收口成 transport/session/OAuth helper
- `http/admin_questionnaires.py` 已收口到 application owner
- `http/admin_questionnaire_console.py` 的 questionnaire external push / retry 已收口到 application owner
- 已有冻结测试覆盖 public submit、questionnaire identity、admin questionnaire、external push console 的主线行为

## 非阻塞剩余项

- `domains/admin_console/service.py` 仍保留问卷 console 首页、详情和编辑态 glue
- `services.py` 仍保留 compatibility shim 与 runtime bridge
- 相邻 context 仍有少量 questionnaire read-side legacy imports
- `domains/questionnaire/service.py` 仍是 application legacy delegate 的内部实现 target

以上剩余项已经记录在：

- `docs/refactor/questionnaire-remaining-exceptions-ledger.md`
- `docs/refactor/questionnaire-primitive-boundary.md`

## 结论

Wave 3 已完成。

当前没有阻塞 Wave 3 正式关单的主线缺口；剩余问题均属于非阻塞 compatibility / read-side / internal-delegate 技术债。
