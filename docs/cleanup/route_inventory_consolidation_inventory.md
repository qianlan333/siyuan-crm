# Route Inventory Consolidation Inventory

Generated: 2026-06-29T10:15:00Z

This report is generated from `docs/architecture/route_ownership_manifest.yml`,
`docs/architecture/*route_inventory.md`, and
`docs/archive/route_inventory/*route_inventory.md` by
`tools/report_route_inventory_consolidation.py`. It does not delete, move,
or deprecate any route inventory file by itself.

## Current Sources

- Canonical manifest: `docs/architecture/route_ownership_manifest.yml`
- Manifest contract: `docs/architecture/route_ownership_manifest.md`
- Manifest checker: `tools/check_route_ownership_manifest.py`
- Manifest regression test: `tests/test_route_ownership_manifest.py`

The manifest currently covers 550 FastAPI routes.
The active hand-written inventory set currently contains 17 `*_route_inventory.md` files.
The archived manifest-derivable inventory set currently contains 7 `*_route_inventory.md` files.
The total inventory evidence set currently contains 24 `*_route_inventory.md` files.
44 exact route rows can currently be regenerated from the manifest for `mostly_manifest_derivable` inventories.

## Classification Summary

- `mostly_manifest_derivable`: 7
- `retain_closeout_evidence`: 17

## Inventory Details

### mostly_manifest_derivable

| Inventory | Location | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `docs/archive/route_inventory/cloud_orchestrator_media_upload_route_inventory.md` | `archived` | 4 | 4 | 0 | 3 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/archive/route_inventory/cloud_orchestrator_run_due_route_inventory.md` | `archived` | 2 | 2 | 0 | 1 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `archived` | 7 | 7 | 0 | 0 | Exact routes match manifest and can be compared with generated route rows. |
| `docs/archive/route_inventory/sidebar_jssdk_route_inventory.md` | `archived` | 2 | 2 | 0 | 0 | Exact routes match manifest and can be compared with generated route rows. |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `archived` | 9 | 9 | 0 | 2 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `archived` | 13 | 13 | 0 | 6 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `archived` | 7 | 7 | 0 | 4 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |

### retain_closeout_evidence

| Inventory | Location | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `docs/architecture/admin_auth_login_route_inventory.md` | `active` | 8 | 5 | 3 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/auth_wecom_route_inventory.md` | `active` | 9 | 7 | 2 | 7 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/checkout_orders_route_inventory.md` | `active` | 21 | 8 | 8 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/cloud_orchestrator_campaign_write_route_inventory.md` | `active` | 18 | 11 | 1 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/cloud_orchestrator_campaigns_route_inventory.md` | `active` | 15 | 12 | 3 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/hxc_dashboard_route_inventory.md` | `active` | 13 | 11 | 1 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/media_library_route_inventory.md` | `active` | 25 | 21 | 4 | 12 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/messages_route_inventory.md` | `active` | 12 | 10 | 1 | 4 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/provider_payment_notify_route_inventory.md` | `active` | 15 | 5 | 6 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/public_product_pay_route_inventory.md` | `active` | 19 | 3 | 11 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_admin_read_route_inventory.md` | `active` | 17 | 15 | 2 | 3 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_admin_write_route_inventory.md` | `active` | 10 | 8 | 2 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_h5_submit_route_inventory.md` | `active` | 5 | 4 | 1 | 5 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_oauth_route_inventory.md` | `active` | 7 | 3 | 3 | 6 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/sidebar_readonly_route_inventory.md` | `active` | 16 | 14 | 2 | 1 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/wecom_tag_read_route_inventory.md` | `active` | 18 | 12 | 2 | 6 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/wecom_tag_write_route_inventory.md` | `active` | 12 | 7 | 4 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |

## Manifest-Generated Rows

These rows are derived from `route_ownership_manifest.yml` for inventories
classified as `mostly_manifest_derivable`. They are intended as parity
evidence before any hand-written route table is archived.

| Inventory | Route | Methods | Route name | Capability owner | External effects | Data source | Auth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `docs/archive/route_inventory/cloud_orchestrator_media_upload_route_inventory.md` | `/admin/cloud-orchestrator/campaigns` | `GET` | `api.admin_cloud_orchestrator_campaigns_workspace` | `cloud_orchestrator` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/cloud_orchestrator_media_upload_route_inventory.md` | `/admin/cloud-orchestrator/plans` | `GET` | `api.admin_cloud_orchestrator_plans_workspace` | `cloud_orchestrator` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/cloud_orchestrator_media_upload_route_inventory.md` | `/admin/cloud-orchestrator/plans/{plan_id}` | `GET` | `api.admin_cloud_orchestrator_plan_detail` | `cloud_orchestrator` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/cloud_orchestrator_media_upload_route_inventory.md` | `/api/admin/cloud-orchestrator/media/upload` | `POST` | `api_cloud_orchestrator_media_upload` | `cloud_orchestrator` | `none` | `command` | `true` |
| `docs/archive/route_inventory/cloud_orchestrator_run_due_route_inventory.md` | `/api/admin/cloud-orchestrator/campaigns/run-due` | `POST` | `api_plan_cloud_campaign_run_due` | `cloud_orchestrator` | `none` | `command` | `true` |
| `docs/archive/route_inventory/cloud_orchestrator_run_due_route_inventory.md` | `/api/admin/cloud-orchestrator/campaigns/run-due/preview` | `POST` | `api_preview_cloud_campaign_run_due` | `cloud_orchestrator` | `none` | `command` | `true` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customer-automation/activation-webhook` | `POST` | `activation_webhook` | `automation_engine` | `none` | `command` | `false` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customers/automation/activation-webhook` | `POST` | `api_customer_automation_activation_webhook` | `automation_engine` | `none` | `command` | `false` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customers/automation/signup-conversion/batches` | `GET` | `signup_conversion_batches` | `automation_engine` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customers/automation/signup-conversion/batches/{batch_id}` | `GET` | `signup_conversion_batch` | `automation_engine` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customers/automation/webhook-deliveries` | `GET` | `customer_automation_webhook_deliveries` | `automation_engine` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customers/automation/webhook-deliveries/retry-due` | `POST` | `api_plan_customer_automation_webhook_delivery_retry_due` | `automation_engine` | `none` | `command` | `false` |
| `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md` | `/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry` | `POST` | `api_plan_customer_automation_webhook_delivery_retry` | `automation_engine` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_jssdk_route_inventory.md` | `/api/sidebar/jssdk-config` | `GET` | `sidebar_jssdk_config` | `identity_contact` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/sidebar_jssdk_route_inventory.md` | `/sidebar/bind-mobile` | `GET` | `api.sidebar_bind_mobile_page` | `identity_contact` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/bind-mobile` | `POST` | `bind_mobile` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/jssdk-config` | `GET` | `sidebar_jssdk_config` | `identity_contact` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/lead-pool/upsert-class-term` | `POST` | `upsert_lead_pool_class_term` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/marketing-status/mark-enrolled` | `POST` | `mark_enrolled` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/marketing-status/set-followup-segment` | `POST` | `set_followup_segment` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/marketing-status/unmark-enrolled` | `POST` | `unmark_enrolled` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/signup-tags/mark` | `POST` | `mark_signup_tag` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/v2/materials/send` | `POST` | `plan_material_send` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/sidebar_write_route_inventory.md` | `/api/sidebar/v2/profile` | `PUT` | `update_sidebar_v2_profile` | `sidebar_write` | `none` | `command` | `false` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/admin/user-ops` | `GET` | `api.admin_user_ops` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/admin/user-ops/ui` | `GET` | `api.admin_user_ops_ui` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/batch-send/execute` | `POST` | `user_ops_batch_send_execute` | `ops_enrollment` | `none` | `command` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/broadcast/preview` | `POST` | `user_ops_broadcast_preview` | `ops_enrollment` | `none` | `command` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/cards` | `GET` | `user_ops_cards` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/customers` | `GET` | `user_ops_customers` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/customers/{external_userid}` | `GET` | `user_ops_customer_detail` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/customers/{external_userid}/timeline` | `GET` | `user_ops_customer_timeline` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/export` | `GET` | `user_ops_export_stub` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/export/preview` | `POST` | `user_ops_export_preview` | `ops_enrollment` | `none` | `command` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/filters` | `GET` | `user_ops_filters` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/overview` | `GET` | `user_ops_overview` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/user_ops_route_inventory.md` | `/api/admin/user-ops/send-records` | `GET` | `user_ops_send_records` | `ops_enrollment` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/admin/customers/profile/tags` | `GET` | `get_admin_customer_profile_tags` | `customer_read_model` | `none` | `read_model` | `true` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/admin/wecom/tags` | `POST` | `create_admin_wecom_tag_command` | `customer_tags` | `staging_disabled` | `external_adapter` | `true` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/admin/wecom/tags/live/gate` | `GET` | `list_wecom_tags_live_gate` | `customer_tags` | `staging_disabled` | `read_model` | `true` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/admin/wecom/tags/live/mark` | `POST` | `mark_tags_live` | `customer_tags` | `staging_disabled` | `external_adapter` | `true` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/admin/wecom/tags/live/unmark` | `POST` | `unmark_tags_live` | `customer_tags` | `staging_disabled` | `external_adapter` | `true` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/h5/questionnaires/{slug}/submit` | `OPTIONS` | `public_submit_questionnaire_options` | `questionnaire` | `none` | `read_model` | `false` |
| `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | `/api/sidebar/signup-tags/mark` | `POST` | `mark_signup_tag` | `sidebar_write` | `none` | `command` | `false` |

## Recommended Order

1. Keep all existing route inventory tests in place.
2. Use this report to compare generated route/method/owner rows against the
   active and archived hand-written route inventory files.
3. Keep closeout evidence sections archived under `docs/archive/route_inventory/`
   once exact route rows are proven redundant with manifest-generated rows.
4. Do not remove route inventory tests until their assertions are either
   generated from the manifest or intentionally retained as archive evidence.

## Non-Goals

- Do not delete route inventory evidence in this batch.
- Do not delete `tests/test_*_route_inventory.py`.
- Do not change route ownership manifest semantics.
- Do not change FastAPI router registration or route behavior.
