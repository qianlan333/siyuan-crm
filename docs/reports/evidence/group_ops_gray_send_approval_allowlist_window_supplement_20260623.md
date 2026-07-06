# Group Ops Gray-Send Approval / Allowlist / Window Supplement - 2026-06-23

Result: `EVIDENCE_COLLECTED`

This supplement follows
`docs/reports/evidence/group_ops_gray_send_evidence_20260623.md`, which already
proved the production send path for `external_effect_job:97` reached Push Center
`sent` with a succeeded real external-effect attempt.

This report checks whether the missing independent operator approval, receiver
allowlist, and gray-window approval evidence can be attached. It cannot upgrade
the Group Ops chain to `PASS_WITH_NOTES` or `PASS_90_PLUS_CANDIDATE`, because
those three independent records were still not available in the approved
evidence window.

This PR does not add runtime logic, routes, deploy changes, migrations,
production writes, or new external calls.

## Existing Group Ops Send Evidence Reference

| Field | Evidence |
| --- | --- |
| Source report | `docs/reports/evidence/group_ops_gray_send_evidence_20260623.md` |
| Environment | production |
| Scenario | `group_ops_gray_send` |
| Plan id | `11` |
| Group Ops webhook event id | `25` |
| Push Center projection | `external_effect_job:97` |
| Effect type | `wecom.message.group.send` |
| Push Center status | `sent` |
| Succeeded attempt | `eea_***6d84` |
| Previous failed attempt | `eea_***dc91` |
| Succeeded attempt real external call | `true` |
| Retryable | `false` |
| Operator action required | `false` |

## Operator Approval Evidence

| Required evidence | Observed |
| --- | --- |
| Approval record reference redacted | `not_attached` |
| Approval actor / role redacted | `not_attached` |
| Approval timestamp / window redacted | `not_attached` |
| `AICRM_GROUP_OPS_GRAY_SEND_APPROVED` configured in production evidence shell | `false` |

Judgment: independent operator approval evidence is still missing. The original
send succeeded, but this supplement cannot prove that a separate approval record
existed before the send.

## Receiver Allowlist Evidence

| Required evidence | Observed |
| --- | --- |
| Receiver allowlist source reference redacted | `not_attached` |
| Receiver allowlist membership confirmed | `not_attached` |
| `AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST` configured in production evidence shell | `false` |
| Succeeded attempt `exact_target_required` / `exact_target_verified` | already recorded as `true` in the prior report |

Judgment: exact-target enforcement was present in the succeeded attempt, but a
separate receiver allowlist source record was not attached. This remains a
residual evidence gap for final closeout.

## Gray-Window Evidence

| Required evidence | Observed |
| --- | --- |
| Gray-window approval source reference redacted | `not_attached` |
| Gray-window start redacted | `not_attached` |
| Gray-window end redacted | `not_attached` |
| `AICRM_GROUP_OPS_GRAY_WINDOW_APPROVED` configured in production evidence shell | `false` |
| `AICRM_GROUP_OPS_GRAY_WINDOW_START` configured in production evidence shell | `false` |
| `AICRM_GROUP_OPS_GRAY_WINDOW_END` configured in production evidence shell | `false` |
| Prior send executed_at | `2026-06-23T09:02:03+08:00` |

Judgment: the send timestamp is known, but no independent approved gray-window
record was attached. Therefore this supplement cannot prove that the send fell
inside an approved gray window.

## Push Center Sent Reconciliation

Read-only reconciliation remained healthy:

```text
GET /api/admin/push-center/jobs/external_effect_job:97/reconciliation
```

| Field | Evidence |
| --- | --- |
| HTTP status | `200` |
| `ok` | `true` |
| `projection_id` | `external_effect_job:97` |
| `effective_status` | `sent` |
| `retryable` | `false` |
| `operator_action_required` | `false` |
| `next_action_label` | `无需操作` |
| `business_explanation` | `主发送链路已完成，当前不需要运营处理。` |
| linked external effect jobs | `1` |
| linked external effect attempts | `2` |
| linked broadcast jobs | `0` |
| linked outbound tasks | `0` |
| route owner | `ai_crm_next` |
| read-only probe real external call | `false` |

Attempt summary:

| Attempt | Status | Error |
| --- | --- | --- |
| previous attempt | `failed_terminal` | `group_ops_webhook_key_not_allowed` |
| succeeded attempt | `succeeded` | none |

This continues to prove that the operational send result is visible and
operator-explainable in Push Center.

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
- full webhook key

Only internal numeric ids, redacted attempt ids, route names, status fields,
boolean configuration presence, counts, and business explanations are recorded.

## Result

`EVIDENCE_COLLECTED`

The Group Ops / Push Center operational send evidence remains strong:

- `external_effect_job:97` exists.
- Push Center effective status is `sent`.
- A succeeded attempt exists and the prior report recorded
  `real_external_call_executed=true`.
- Push Center says `retryable=false` and `operator_action_required=false`.

However, this supplement cannot elevate the chain because the three independent
governance records remain missing:

1. operator approval record,
2. receiver allowlist source/membership record,
3. approved gray-window source/start/end record.

## Residual Risk

Final closeout should treat Group Ops as `EVIDENCE_COLLECTED` with this
residual risk:

```text
Operational send path is proven and Push Center is explainable, but governance
evidence for approval / allowlist / gray window remains incomplete.
```

If the reviewer accepts the absence of separate governance records as a
non-blocking historical limitation, final closeout may choose `PASS_WITH_NOTES`.
Without that explicit review decision, this report should not be treated as
`PASS_90_PLUS_CANDIDATE`.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` requires all core business chains to have complete
evidence and no blocking reason. This supplement covers only Group Ops. It also
keeps a Group Ops residual governance risk, so it cannot independently unlock
global `PASS_90_PLUS`.

## Risk / Rollback

This PR is document-only. Rollback is to revert this supplement. There is no
runtime rollback, deploy rollback, env rollback, DB rollback, migration
rollback, or external-effect rollback.

## Next Action

Either:

1. attach a redacted operator approval / receiver allowlist / gray-window record
   from an approved source and reclassify Group Ops, or
2. keep Group Ops as `EVIDENCE_COLLECTED` and carry this residual risk into the
   final Business Closure closeout.
