# Business Closure 90%+ Evidence Closeout

Status: `READINESS_ONLY`

This closeout document is the control surface for deciding whether business
capabilities 3-7 can be treated as 90%+ ready for trial operations. It does not
collect real production evidence, does not make external calls, and does not
claim production readiness by itself.

## Scope

The closeout summary covers four evidence chains:

| Scenario | Evidence template | Business capability |
| --- | --- | --- |
| `group_ops_gray_send` | `docs/reports/group_ops_gray_send_evidence_template.md` | Push Center / Group Ops |
| `ops_plan_to_broadcast` | `docs/reports/ops_plan_to_broadcast_e2e_evidence_template.md` | Event / Approval / Task loop |
| `external_orders` | `docs/reports/external_orders_enablement_evidence_template.md` | External Orders enablement |
| `wecom_auth` | `docs/reports/wecom_operator_auth_callback_evidence_template.md` | WeCom operator auth / callback |

## Summary Command

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py --scenario all
```

The command is read-only. It must keep:

- `real_external_call_executed=false`
- `production_write_executed=false`
- `deploy_or_env_modified=false`
- no token, secret, `Authorization` header, raw `external_userid`, phone
  number, `access_token`, or `corpsecret` in output

## Summary Fields

Each closeout item must include:

- `scenario`
- `readiness_status`
- `evidence_status`
- `derived_status`
- `blocking_reasons`
- `missing_operator_evidence`
- `sensitive_data_redaction_ok`
- `real_external_call_executed`
- `production_write_executed`
- `can_claim_90_plus`
- `next_required_operator_action`
- `business_explanation`

## Status Model

| Status | Meaning |
| --- | --- |
| `READINESS_ONLY` | The scaffold exists, but real operator evidence is missing. |
| `EVIDENCE_COLLECTED` | Required evidence ids/status fields are attached, but the final closeout has not elevated every chain. |
| `PASS_WITH_NOTES` | Evidence is mostly complete with non-blocking notes. This closeout command currently reserves the value for future operator review; it does not emit it automatically. |
| `PASS_90_PLUS` | All four core chains have complete evidence and no blocking reasons. |
| `BLOCKED` | Critical config, auth, token, receiver, plan, event, job, permission, or visibility evidence is missing. |

## 90%+ Claim Rules

The system must not output `PASS_90_PLUS` by default.

`PASS_90_PLUS` is allowed only when all of the following are true:

- `group_ops_gray_send` has plan, effect job, attempt, Push Center job, and
  operator approval / receiver allowlist evidence.
- `ops_plan_to_broadcast` has plan, internal event, consumer run, generated
  broadcast or external effect job, and Push Center projection evidence.
- `external_orders` has valid-token readiness plus order, external order,
  idempotency, customer, channel, source, internal event, and admin visibility
  evidence.
- `wecom_auth` has operator identity, auth start, callback signature, callback
  event, inbound event, idempotency, duplicate handling, and permission scope
  evidence.
- Every closeout item has no blocking reason except terminal success markers
  such as `order_linked` or `callback_linked`.
- Every closeout item has `sensitive_data_redaction_ok=true`.
- Every diagnostic item has `real_external_call_executed=false`.
- Every diagnostic item has `production_write_executed=false`.

## Default Interpretation

When run without operator evidence, the closeout should be interpreted as
`READINESS_ONLY` or `BLOCKED`. That is expected and safe. It means the system is
ready for operator-owned evidence collection, not that real gray validation has
already happened.

## Operator Evidence Checklist

### Group Ops / Push Center

- Receiver allowlist proof:
- Operator approval:
- Plan id:
- External effect job id:
- Attempt id:
- Push Center job id:
- Push Center reconciliation:

### Ops Plan -> Broadcast

- Plan id:
- Approval event id:
- Internal event id:
- Consumer run id:
- Broadcast job or external effect job id:
- Push Center job id:
- Duplicate approval handling:

### External Orders

- Token configured outside git:
- Request-token path checked without logging token:
- Order id:
- External order id:
- Idempotency key:
- Customer id:
- Channel id:
- Source:
- Internal event id:
- Admin visibility:

### WeCom Auth / Callback

- Corp id / agent id / redirect URI readiness:
- Auth start 302 readiness:
- Missing code / invalid state controlled failure:
- Redacted operator identity:
- Callback signature status:
- Callback event id:
- Inbound event id:
- Idempotency key:
- Duplicate callback handling:
- Customer/group/material permission scope:

## Non-Goals

- No production deploy/systemd/nginx/env modification.
- No production migration execution.
- No production DB write.
- No real WeCom / Payment / OAuth / OpenClaw / MCP external call.
- No P1 TypeScript frontend work.
- No new route or runtime behavior change.

## Next Operator Actions

1. Collect Group Ops gray-send evidence in an approved operator window.
2. Collect Ops Plan -> Broadcast E2E evidence.
3. Collect External Orders valid-token and order-linkage evidence.
4. Collect WeCom operator auth and callback gray evidence.
5. Re-run the closeout command and attach the output to the business closeout
   review.
