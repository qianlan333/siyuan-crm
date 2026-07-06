# Sidebar Write Route Inventory

Status: Legacy Exit group 5 deletion closeout locked.

Scope: Sidebar write paths only. This group moves internal mutations to the Next CommandBus, records AuditLedger events, creates SideEffectPlan records for external side effects, and removes the legacy production_compat rollback for the exact write routes.

Non-goals: no real WeCom sends, no real JSSDK signing, no real material send, no automation runtime execution, no payment/OpenClaw/storage calls.

| Path | Method | Current owner | Expected owner | Write type | Target aggregate | External side effect risk | Command name | Side effect plan | Replacement decision | Delete decision | Test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/sidebar/bind-mobile` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | binding update | customer identity/sidebar projection | medium | `BindMobileCommand` | none | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_commands.py` |
| `/api/sidebar/lead-pool/upsert-class-term` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | lead-pool local status | customer class/user status projection | medium | `UpsertLeadPoolClassTermCommand` | none | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_commands.py` |
| `/api/sidebar/signup-tags/mark` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | signup tag local marker | customer tag/status projection | high | `MarkSignupTagCommand` | `wecom.tag.update` real_blocked | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_no_real_side_effects.py` |
| `/api/sidebar/marketing-status/set-followup-segment` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | marketing status local marker | marketing status projection | medium | `SetFollowupSegmentCommand` | `automation.followup_segment_changed` real_blocked | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_commands.py` |
| `/api/sidebar/marketing-status/mark-enrolled` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | marketing enrollment marker | marketing status projection | medium | `MarkEnrolledCommand` | none | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_commands.py` |
| `/api/sidebar/marketing-status/unmark-enrolled` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | marketing enrollment marker | marketing status projection | medium | `UnmarkEnrolledCommand` | none | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_commands.py` |
| `/api/sidebar/v2/profile` | PUT | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | profile update | customer profile projection | high | `UpdateSidebarProfileCommand` | `wecom.profile.update` real_blocked | Next CommandBus locked; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_no_real_side_effects.py` |
| `/api/sidebar/v2/materials/send` | POST | `aicrm_next.sidebar_write` | `aicrm_next.sidebar_write` | external side effect plan | material send request | high | `PlanMaterialSendCommand` | `wecom.material.send` real_blocked | blocked/plan only; no real send; legacy production_compat rollback removed | deletion_locked | `tests/test_sidebar_write_no_real_side_effects.py` |
| `/api/sidebar/jssdk-config` | GET | production_compat / blocked readonly route | later adapter group | JSSDK real signature | WeCom JSSDK signature | high | none | none in this group | out of scope | not deleted in this group | `historical removed reference (test_sidebar_write_registry_lifecycle.py)` |

CommandBus contract:

- Every write request creates a command with `command_id`, `idempotency_key`, `actor_id`, `actor_type`, `external_userid`, `payload`, `dry_run`, `source_route`, and `trace_id`.
- Every command writes an AuditLedger event.
- External side effects produce SideEffectPlan records only, with `adapter_mode: real_blocked`, `requires_approval: true`, and `real_external_call_executed: false`.
- Errors are controlled: 400 `input_error`, 404 `not_found`, or 503 `production_unavailable`.
- Responses must include `route_owner: ai_crm_next`, `fallback_used: false`, and no `X-AICRM-Compatibility-Facade`.
- Legacy production_compat rollback is removed for the exact write routes; JSSDK remains a separate out-of-scope group.
