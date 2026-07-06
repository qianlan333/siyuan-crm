# Group Ops / Push Center Gray-Send Evidence - 2026-06-23

Verdict: `EVIDENCE_COLLECTED`

This report records read-only production evidence for a Group Ops / Push Center
gray-send path. It does not claim global `PASS_90_PLUS`, and it does not claim a
scenario-level `PASS_90_PLUS_CANDIDATE`, because explicit operator approval,
receiver allowlist, and gray-window approval records were not attached to this
report.

This report does not contain tokens, secrets, `Authorization` headers, raw
`external_userid`, receiver plaintext, phone numbers, customer private
request/response bodies, or raw chat/member identifiers.

## Scope

- Environment: production
- Review date: 2026-06-23
- Scenario: `group_ops_gray_send`
- Plan id: `11`
- Group Ops webhook event id: `25`
- Primary Push Center projection: `external_effect_job:97`
- External effect type: `wecom.message.group.send`
- Business type: `group_ops_plan`
- Source module: `automation_engine.group_ops.legacy_bundle`
- Source route: `/api/automation/group-ops/webhooks/{webhook_key}`
- Route owner from Push Center reconciliation: `ai_crm_next`

## Safety Attestation

| Field | Result |
| --- | --- |
| Runtime code changed | `false` |
| Route added or changed | `false` |
| Production deploy/systemd/nginx/env modified | `false` |
| Production migration executed | `false` |
| Production DB write executed by this report | `false` |
| Real external call executed by diagnostics/read path | `false` |
| Historical real external call observed in attempt evidence | `true` |
| Token or authorization header logged | `false` |
| Raw receiver / external_userid committed | `false` |

This PR only records evidence. The production send happened before this report
was written and is represented by the external effect attempt records below.

## Operator Evidence Supplied

| Required field | Evidence |
| --- | --- |
| `plan_id` | `11` |
| `effect_job_id` | `external_effect_job:97` |
| `attempt_id` | succeeded attempt `eea_***6d84`; previous failed attempt `eea_***dc91` |
| `push_center_job_id` | `external_effect_job:97` |
| `push_center_status` | `sent` |
| `retryable` | `false` |
| `operator_action_required` | `false` |
| `business_explanation` | `主发送链路已完成，当前不需要运营处理。` |
| `receiver_allowlist_readiness` | Explicit env allowlist record was not configured at read time; succeeded attempt recorded `exact_target_required=true` and `exact_target_verified=true`. |
| `operator_approval_evidence` | No separate approval record was attached; effect job `requires_approval=false`. |
| `gray_window_evidence` | Send evidence timestamp: `2026-06-23T09:02:03+08:00`; no separate approved gray-window record was attached. |
| `real_external_call_executed` | `true` in the succeeded attempt response summary. |
| `production_write_executed` | `true` for the historical production job/attempt records; `false` for this read-only evidence collection. |
| `sensitive_data_redaction_confirmed` | `true` |

## Push Center Visibility Evidence

Read-only reconciliation endpoint:

```text
GET /api/admin/push-center/jobs/external_effect_job:97/reconciliation
```

Observed response summary:

| Field | Evidence |
| --- | --- |
| HTTP status | `200` |
| `ok` | `true` |
| `projection_id` | `external_effect_job:97` |
| `display_id` | `#97` |
| `effective_status` | `sent` |
| `retryable` | `false` |
| `operator_action_required` | `false` |
| `next_action_label` | `无需操作` |
| linked `external_effect_jobs` | `1` |
| linked `external_effect_attempts` | `2` |
| linked `broadcast_jobs` | `0` |
| linked `outbound_tasks` | `0` |
| `legacy_readonly` | `false` |

Push Center can explain the business state without DB access:

```text
主发送链路已完成，当前不需要运营处理。
```

## External Effect / Attempt Evidence

External effect job:

| Field | Evidence |
| --- | --- |
| id | `97` |
| effect_type | `wecom.message.group.send` |
| adapter_name | `wecom_group_message` |
| operation | `send_group_message` |
| target_type | `group_ops_webhook_event` |
| business_type | `group_ops_plan` |
| business_id | `11` |
| source_event_id | `25` |
| execution_mode | `execute` |
| status | `succeeded` |
| attempt_count | `1` |
| max_attempts | `5` |
| last_attempt_id | `eea_***6d84` |
| created_at | `2026-06-23T08:59:49+08:00` |
| executed_at | `2026-06-23T09:02:03+08:00` |

Attempt evidence:

| Attempt | Status | Real external call | Error |
| --- | --- | --- | --- |
| `eea_***dc91` | `failed_terminal` | `false` | `group_ops_webhook_key_not_allowed` |
| `eea_***6d84` | `succeeded` | `true` | none |

Succeeded attempt response summary:

| Field | Evidence |
| --- | --- |
| adapter | `WeComGroupMessageAdapter` |
| operation | `create_group_message_task` |
| mode | `production` |
| requested_chat_count | `8` |
| exact_target_required | `true` |
| exact_target_verified | `true` |
| wecom_msgid_present | `true` |
| wecom_send_executed | `true` |
| real_external_call_executed | `true` |

The first failed attempt remains useful evidence for retry/recovery behavior:
the gate failure was observable, the later attempt succeeded, and Push Center now
shows the final effective status as `sent`.

## Related Group Ops Records

| Record | Evidence |
| --- | --- |
| Group Ops plan | `11` |
| Plan type | `webhook` |
| Plan status | `active` |
| owner_userid present | `true` |
| allow_external_recipients | `true` |
| Group Ops webhook event | `25` |
| Event created_at | `2026-06-23T08:59:49+08:00` |
| Event scheduled_at | `2026-06-23T08:59:54+08:00` |

A recent legacy `broadcast_jobs` record also exists for plan `11`:
`broadcast_job:3643`, status `sent`, `sent_count=8`, `failed_count=0`. The
primary evidence for this report is the Next Push Center projection
`external_effect_job:97`, because it contains the external effect and attempt
records required by the 90%+ closeout framework.

## Sensitive-Data Redaction Evidence

Confirmed not committed:

- token
- secret
- `Authorization` header
- raw `external_userid`
- receiver plaintext
- phone number
- raw chat/member identifier
- customer private request/response body
- WeCom message id
- full webhook key value beyond the non-secret plan label already present in
  existing summaries

The report only records internal numeric ids, redacted attempt ids, status
fields, counts, route names, and business explanations.

## Result

Result: `EVIDENCE_COLLECTED`

Reasoning:

- A real production Group Ops external effect job exists.
- A real succeeded external effect attempt exists.
- The succeeded attempt records `real_external_call_executed=true`.
- Push Center can reconcile the job and returns `effective_status=sent`.
- Push Center returns `retryable=false` and `operator_action_required=false`.

This report does not escalate to `PASS_WITH_NOTES` or
`PASS_90_PLUS_CANDIDATE`, because explicit operator approval, receiver allowlist,
and approved gray-window records were not attached as separate evidence.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` still requires the business closure closeout summary to
confirm all core scenarios:

- Group Ops / Push Center
- Ops Plan -> Broadcast E2E
- External Orders
- WeCom Auth / Callback

This report contributes Group Ops evidence only. It does not replace the final
business closure closeout.

## Risk / Rollback

This is a documentation-only evidence report. Rollback is to revert this PR.
There is no runtime rollback, no deploy rollback, and no database rollback.

## Next Action

Attach or reference the operator-owned approval, receiver allowlist, and gray
window record outside git. If those records are accepted by the operator review,
Group Ops / Push Center can be reclassified from `EVIDENCE_COLLECTED` to
`PASS_WITH_NOTES` or `PASS_90_PLUS_CANDIDATE` in the final closeout.
