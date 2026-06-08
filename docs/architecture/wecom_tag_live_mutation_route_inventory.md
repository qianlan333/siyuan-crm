# WeCom Live Tag Mutation Route Inventory

Scope: Legacy Exit group 14 closeout locks live gate/mark/unmark and tag mutation callers to Next CommandBus plan-only handling. This group does not execute real WeCom, real token exchange, real external push, payment, storage, OpenClaw, or automation runtime. Tag catalog CRUD/sync stays deletion_locked from group 13.

Closeout status: live gate, live mark, and live unmark are `deletion_locked` / `locked` in both the route registry and production route ownership manifest. Their `legacy_fallback_allowed` flags are false, and production_compat must not register these routes.

## Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix

| Caller | Caller file | Current API | Payload | Target external_userid | tag_ids | CommandBus command | SideEffectPlan effect_type | Real WeCom | Smoke / test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Live gate smoke | curl / admin diagnostics | `GET /api/admin/wecom/tags/live/gate` | none | none | none | none | none | no; `adapter_mode=real_blocked`, `route_owner=ai_crm_next`, `fallback_used=false` | registry/manifest locked; smoke + `tests/test_wecom_tag_live_mutation_commands.py` |
| Admin live mark | API client / smoke | `POST /api/admin/wecom/tags/live/mark` | `external_userid`, `tag_ids`, `operator`, `Idempotency-Key` | `external_userid` | request `tag_ids` | `PlanWeComTagMarkCommand` | `wecom.tag.mark` | no; `real_external_call_executed=false`, `wecom_api_called=false` | registry/manifest locked; smoke + `tests/test_wecom_tag_live_mutation_commands.py` |
| Admin live unmark | API client / smoke | `POST /api/admin/wecom/tags/live/unmark` | `external_userid`, `tag_ids`, `operator`, `Idempotency-Key` | `external_userid` | request `tag_ids` | `PlanWeComTagUnmarkCommand` | `wecom.tag.unmark` | no; `real_external_call_executed=false`, `wecom_api_called=false` | registry/manifest locked; smoke + `tests/test_wecom_tag_live_mutation_commands.py` |
| Sidebar signup tag marker | `aicrm_next/sidebar_write/api.py`, `aicrm_next/sidebar_write/application.py` | `POST /api/sidebar/signup-tags/mark` | `external_userid`, `tag_id` or `tag_name`, `marked` | `external_userid` | `tag_id` when present | `MarkSignupTagCommand` | `wecom.tag.update` | no; existing plan-only sidebar CommandBus | locked sidebar route; smoke + `tests/test_wecom_tag_live_mutation_callers_contract.py` |
| Questionnaire H5 submit tag apply | `aicrm_next/questionnaire/application.py`, `aicrm_next/integration_gateway/questionnaire_adapters.py` | `POST /api/h5/questionnaires/{slug}/submit` | answers + identity; final tags derived by scoring | resolved `external_userid` | `final_tags` | `PlanQuestionnaireTagSideEffectCommand` | `questionnaire.tag.apply` | no; replaced guarded tag adapter call with Next plan-only command | locked H5 submit route; smoke + `tests/test_wecom_tag_live_mutation_callers_contract.py` |
| Questionnaire admin write tag selector | `aicrm_next/questionnaire/templates/admin_questionnaires.html` | `GET /api/admin/wecom/tags` selector only | none for mutation | none | none | none | none | no mutation route; read CRUD remains deletion_locked | `tests/test_wecom_tag_read_selectors.py` |
| Customer profile tag read/assignment boundary | `aicrm_next/customer_read_model/api.py`, `aicrm_next/customer_tags/live_mutation.py` | `GET /api/admin/customers/profile/tags`; command-only assignment boundary | `external_userid`, `tag_ids` for assignment command | `external_userid` | command `tag_ids` | `PlanCustomerTagAssignmentCommand` | `wecom.tag.assignment.apply` | no; command-only plan boundary until a write API is approved | no approved write API in this group; `tests/test_wecom_tag_live_mutation_callers_contract.py` |
| User ops tag filter | `aicrm_next/ops_enrollment/api.py` | customer/user ops reads and previews | filters only | none | none | none | none | no mutation caller found | explicitly no mutation API in this group; `tests/test_wecom_tag_live_mutation_inventory.py` |
| Automation questionnaire result | `QuestionnaireSubmitSideEffectGateway.emit_automation_questionnaire_result` | internal gateway call from submit | questionnaire/submission/final_tags | submission `external_userid` | `final_tags` as automation context | none in this group | none in this group | automation runtime remains explicitly out of scope | explicitly no automation runtime mutation in this group |

## Inventory

1. `aicrm_next/customer_tags/api.py` owns `live/gate`, `live/mark`, and `live/unmark`.
2. `aicrm_next/customer_tags/mutation_commands.py` defines `PlanWeComTagMarkCommand`, `PlanWeComTagUnmarkCommand`, `PlanCustomerTagAssignmentCommand`, and `PlanQuestionnaireTagSideEffectCommand`.
3. `aicrm_next/customer_tags/live_mutation.py` owns CommandBus dispatch, idempotency reuse, AuditLedger writes, and SideEffectPlan creation.
4. `aicrm_next/sidebar_write/application.py` already records sidebar signup tag mutation as `wecom.tag.update` SideEffectPlan only.
5. `aicrm_next/integration_gateway/questionnaire_adapters.py` now routes questionnaire tag apply through `PlanQuestionnaireTagSideEffectCommand`.
6. Customer profile tags are read-only today; `PlanCustomerTagAssignmentCommand` is the plan-only boundary for future assignment mutation.
7. No user ops tag mutation route was found; tag usage there is read/filter/preview only.

## CommandBus

| Command | Source | SideEffectPlan | Adapter | Status |
| --- | --- | --- | --- | --- |
| `PlanWeComTagMarkCommand` | `POST /api/admin/wecom/tags/live/mark` | `wecom.tag.mark` | `wecom`, `real_blocked` | locked |
| `PlanWeComTagUnmarkCommand` | `POST /api/admin/wecom/tags/live/unmark` | `wecom.tag.unmark` | `wecom`, `real_blocked` | locked |
| `PlanCustomerTagAssignmentCommand` | customer profile/tag assignment boundary | `wecom.tag.assignment.apply` | `wecom`, `real_blocked` | plan-only boundary |
| `PlanQuestionnaireTagSideEffectCommand` | questionnaire H5 submit scoring | `questionnaire.tag.apply` | `wecom`, `real_blocked` | plan-only boundary |

## SideEffectPlan Only

All mutation plans include `adapter_name=wecom`, `adapter_mode=real_blocked`, `requires_approval=true`, `real_external_call_executed=false`, `wecom_api_called=false`, `external_userid`, `tag_ids`, and a redacted `payload_summary`.

## Explicitly Unchanged

- Real WeCom execution is not enabled.
- Real WeCom token exchange is not enabled.
- Real external push is not changed by this group.
- Payment, storage, OpenClaw, and automation runtime are not changed.
- Tag catalog CRUD/sync remains group 13 `deletion_locked`.
