# Questionnaire Admin Write Route Inventory

Date: 2026-06-02

Scope: backend questionnaire admin write replacement only. Public H5 submit, OAuth/auth, real WeCom tag mutation, external push execution, payment/storage/OpenClaw/automation runtime, and any real external side effect are out of scope.

## Existing Routes Read From Code

| Route | Methods | Existing behavior before this group | Group 8 action |
| --- | --- | --- | --- |
| `/api/admin/questionnaires` | `POST` | Admin create wrote through legacy facade in production and fixture command locally. | Replaced with `questionnaire.admin.create` on Next CommandBus. |
| `/api/admin/questionnaires/{questionnaire_id}` | `PUT` | Admin update wrote through legacy facade in production and fixture command locally. | Replaced with `questionnaire.admin.update` on Next CommandBus. |
| `/api/admin/questionnaires/{questionnaire_id}` | `DELETE` | Admin delete wrote through legacy facade in production and hard-deleted fixture locally. | Replaced with `questionnaire.admin.delete` hard-delete command; API requires the questionnaire to be disabled first. |
| `/api/admin/questionnaires/{questionnaire_id}/enable` | `POST` | Admin enable wrote through legacy facade in production and fixture command locally. | Replaced with `questionnaire.admin.enable` on Next CommandBus. |
| `/api/admin/questionnaires/{questionnaire_id}/disable` | `POST` | Admin disable wrote through legacy facade in production and fixture command locally. | Replaced with `questionnaire.admin.disable` on Next CommandBus. |
| `/api/admin/questionnaires/{questionnaire_id}/export` | `GET` | Export generated/downloaded data directly, using legacy facade in production. | Replaced with `questionnaire.admin.export_download`; returns a CSV response stream without creating a server-side file or storage side effect. |

## Added Routes

| Route | Methods | Command | Notes |
| --- | --- | --- | --- |
| `/api/admin/questionnaires/{questionnaire_id}` | `PATCH` | `questionnaire.admin.update` | PATCH alias for the same admin update command. |
| `/api/admin/questionnaires/{questionnaire_id}/duplicate` | `POST` | `questionnaire.admin.duplicate` | Creates a disabled local copy in the write model. |
| `/api/admin/questionnaires/{questionnaire_id}/publish` | `POST` | `questionnaire.admin.publish` | Enables the questionnaire and creates a guarded public projection SideEffectPlan only. |
| `/api/admin/questionnaires/{questionnaire_id}/export/preview` | `POST` | `questionnaire.admin.export_preview` | Returns masked sample rows and a guarded export SideEffectPlan only. |

## Command Contract

All write commands carry:

`command_id`, `idempotency_key`, `actor_id`, `actor_type`, `questionnaire_id`, `payload`, `dry_run`, `source_route`, and `trace_id`.

Responses include:

`ok`, `command_id`, `questionnaire_id`, `source_status=next_command`, `write_model_status`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`, plus `side_effect_plan` when a guarded effect is planned.

`Idempotency-Key` is accepted from the request header and returns the cached CommandBus result for repeated requests.

## Production Boundary

When production data is ready, create/update/duplicate/publish/enable/disable/delete/export-preview execute through the Next questionnaire admin CommandBus and Postgres questionnaire repository. Delete is only accepted after the questionnaire has been disabled and then removes the questionnaire row through the repository. The legacy Flask questionnaire admin write rollback has been removed; fixture data is not used as production data.

The active Next handler owns the route surface in both production and fixture/local mode. No production fallback remains for admin persistence commands; duplicate/publish/export preview/export download remain guarded Next commands with `legacy rollback removed`.

## Deletion Closeout

Admin write routes are tracked as `runtime_owner=next_command`, `legacy_fallback_allowed=false`, `delete_status=deletion_locked`, and `replacement_status=locked`. Responses must include `source_status=next_command`, `fallback_used=false`, and no `X-AICRM-Compatibility-Facade`.

No production_compat admin write wildcard is registered; fallback stays inside the explicit integration gateway boundary. H5 submit/diagnostics and OAuth/auth remain out of scope and are not changed by this closeout.

## Out Of Scope

| Surface | Status |
| --- | --- |
| `/api/h5/questionnaires*` | Out of scope; no deletion lock added by this group. |
| `/api/h5/wechat/oauth*` | Out of scope; no deletion lock added by this group. |
| WeCom tags / external push / automation runtime / storage real execution | Blocked behind SideEffectPlan only; no real external call executes. |
