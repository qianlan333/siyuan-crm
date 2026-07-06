# customer.phone_bound Internal Event

`customer.phone_bound` records the business fact that a customer identity has
successfully bound a mobile number. It does not mean a notification was sent, a
tag was changed, or automation has run.

## Event Schema

- `event_type`: `customer.phone_bound`
- `aggregate_type`: `customer`
- `aggregate_id`: `person_id`, then `external_userid`, then `mobile:<hash>`
- `subject_type`: `customer`
- `subject_id`: redacted external userid or masked mobile
- `idempotency_key`: `customer.phone_bound:{stable_identity_key}:{mobile_hash}`
- `source_module`: `identity_contact.application`
- `source_route`: `identity_contact.bind_mobile`

`payload_json` may keep internal diagnostic fields such as `person_id`,
`external_userid`, `mobile`, `identity_map_id`, `follow_user_userid`,
`matched_by`, and binding source metadata. Admin list/detail responses do not
show raw `payload_json` by default.

`payload_summary_json` only includes safe observability fields:

- `person_id_present`
- `external_userid_present`
- `mobile_masked`
- `binding_status`
- `matched_by`
- `source`
- `identity_map_id_present`

It must not contain raw mobile, raw external userid, openid, unionid, token, or
secret values.

## Feature Flag

Production default is off:

```bash
AICRM_INTERNAL_EVENTS_CUSTOMER_IDENTITY_ENABLED=0
```

Emit requires all of:

- `AICRM_INTERNAL_EVENTS_ENABLED=1`
- `AICRM_INTERNAL_EVENTS_CUSTOMER_IDENTITY_ENABLED=1`
- `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES` is empty or includes
  `customer.phone_bound`

Diagnostics expose `customer_identity_internal_events_enabled`.

## Write Path

The emit happens after `BindMobileToExternalContactCommand` successfully returns
a bound result. Questionnaire mobile binding already calls this command, so it
uses the same path and does not need a separate emit.

Emit is wrapped with `safe_emit`; failure to write the internal event must not
fail the mobile binding request. Duplicate binding of the same stable identity
and mobile reuses the same internal event through the idempotency key.

## Consumers

- `customer_identity_projection_consumer`
  Confirms the phone-bound fact and returns `succeeded` with
  `customer_identity_projection=phone_bound_confirmed`.
- `customer_summary_consumer`
  Currently `skipped`, `reason=customer_summary_not_configured`.
- `automation_phone_bound_consumer`
  Currently `skipped`, `reason=automation_phone_bound_not_configured`.
- `customer_identity_ai_assist_notify_consumer`
  Currently `skipped`, `reason=customer_identity_ai_assist_notify_not_configured`.

None of these consumers performs external calls.

## Worker Pair Allowlist Safety

Do not add `customer.phone_bound:*` pairs to production
`AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` during Q0/Q1. Payment worker
automation can continue using only payment pairs, for example:

```bash
AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer,payment.succeeded:automation_payment_consumer
```

With pair allowlist enabled, `customer.phone_bound` can emit and remain pending
without being picked up by the worker.

## Production Verification

### Q0: Flag Off

1. Set `AICRM_INTERNAL_EVENTS_CUSTOMER_IDENTITY_ENABLED=0`.
2. Execute a safe mobile binding.
3. Verify binding succeeds.
4. Verify no `customer.phone_bound` event or consumer run is created.

### Q1: Shadow Emit

1. Set `AICRM_INTERNAL_EVENTS_CUSTOMER_IDENTITY_ENABLED=1`.
2. Add `customer.phone_bound` to `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES`.
3. Keep `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` limited to payment pairs.
4. Execute a safe mobile binding.
5. Verify exactly one `customer.phone_bound` event and four pending consumer runs.
6. Verify worker preview does not select phone-bound consumers.

### Q2: Single Consumer

Use only the single-consumer endpoint:

```bash
POST /api/admin/internal-events/{event_id}/consumers/customer_identity_projection_consumer/run
```

Run dry-run first, then `dry_run=false` without `force`. Confirm:

- `status=succeeded`
- `attempt_count=1`
- `real_external_call_executed=false`
- no external effect attempt

## Rollback

```bash
AICRM_INTERNAL_EVENTS_CUSTOMER_IDENTITY_ENABLED=0
```

Remove `customer.phone_bound` from `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES`.
Keep payment, questionnaire, and customer tag configuration unchanged.
