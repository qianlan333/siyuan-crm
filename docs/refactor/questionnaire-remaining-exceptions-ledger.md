# Questionnaire Remaining Exceptions Ledger

日期：2026-04-21

## 说明

下表只记录当前仍保留、但本轮不继续处理的 questionnaire 例外。判断标准不是“是否还存在 legacy 痕迹”，而是“是否阻塞 Wave 3 closeout”。

| 例外 | 当前形态 | 为什么这次不拆 | 类别 | 是否阻塞 Wave 3 closeout | 后续归位建议 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/services.py` 的 questionnaire wrappers 与 `_bind_questionnaire_domain` | 历史 shim / runtime bridge | 需要保留旧 import、异常语义和 runtime 注入稳定面；本轮优先先把 caller owner 收口，而不是直接删兼容层 | `shim` / `bridge` | 否 | 后续如进入 questionnaire 内部模块化，可先收缩 `services.py` 到 exception export + compatibility façade |
| `wecom_ability_service/http/public_questionnaires.py -> services.QuestionnaireAlreadySubmittedError` | public controller 的单一兼容异常导入 | 当前 public submit 错误语义依赖这条历史异常类型，贸然移动会扩大兼容面 | `shim` | 否 | 后续可在 `application/questionnaire/*` 暴露稳定异常出口，再把 controller 改到 application exception |
| `wecom_ability_service/domains/admin_console/service.py::{build_questionnaire_index_payload,build_questionnaire_detail_payload,save_questionnaire_editor,toggle_questionnaire_disabled}` | admin console glue 仍复用 questionnaire shim 与 repo | 这些函数属于 admin console 页面 glue，不是本轮 Wave 3 的主要 controller cutover 目标 | `read` / `maintenance` / `bridge` | 否 | 后续可把问卷 console 首页、详情、编辑态分别改成直接调用 `application/questionnaire/*` |
| `wecom_ability_service/http/admin_support.py::list_available_wecom_tags` 直连 `domains/questionnaire/service.py` | support 页面读面直连 | 属于相邻 context 的只读依赖，本轮不进入 admin support 改造 | `read` | 否 | 后续切到 `ListAvailableWeComTagsQuery` |
| `wecom_ability_service/domains/automation_conversion/service.py::{get_questionnaire_detail,list_available_wecom_tags,list_questionnaires}` | automation_conversion 的问卷读依赖 | 用户已明确本轮不进入 `automation_conversion` 内部拆分 | `read` / `bridge` | 否 | 后续该 context 收口时，统一改成 `application/questionnaire/queries.py` |
| `wecom_ability_service/domains/admin_dashboard/repo.py::{list_questionnaires,build_questionnaire_preflight_payload}` | dashboard 的轻量问卷读依赖 | 不属于问卷主线 caller；本轮只保证 questionnaire owner 成立 | `read` / `maintenance` | 否 | 后续改成 `ListQuestionnairesQuery` + `BuildQuestionnairePreflightQuery` |
| `wecom_ability_service/domains/marketing_automation/service.py::get_questionnaire_detail` | marketing_automation 的问卷详情读取 | 这是相邻 context 的读侧桥接，本轮不触碰 marketing automation | `read` / `bridge` | 否 | 后续改成 `GetQuestionnaireDetailQuery` |
| `wecom_ability_service/domains/questionnaire/service.py` 仍是 mixed legacy delegate target | application owner 已建立，但内部实现尚未细拆 | 本轮目标是 formal owner + caller cutover，不是立即做问卷内部子模块拆分 | `maintenance` / `bridge` | 否 | 如继续演进，优先拆 `submit`、`identity bridge`、`external push` 三块内部 owner |
| `wecom_ability_service/domains/questionnaire/preflight_service.py` 仍为独立 helper | preflight 内部实现尚未合并 | 目前已有 `BuildQuestionnairePreflightQuery` 封装，直接行为风险低 | `maintenance` | 否 | 后续保留为内部 helper，或并入更细的 admin/preflight owner |

## 结论

当前 remaining exceptions 仍然存在，但都已被限制在：

- compatibility shim
- 相邻 context 的 legacy read
- admin console glue
- application 的 legacy delegate target

它们不再构成 questionnaire 主线的 owner 漂移，因此不阻塞 Wave 3 closeout。
