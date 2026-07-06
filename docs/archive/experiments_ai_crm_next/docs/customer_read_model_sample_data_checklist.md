# Customer Read Model Sample Data Readiness Checklist

Customer detail, timeline, and recent-message gray checks require a safe `external_userid` sample. The smoke tools must choose the sample from a list response instead of hard-coding a real customer id.

## Why A Sample Is Required

- `GET /api/customers/{external_userid}` needs a concrete customer id.
- `GET /api/customers/{external_userid}/timeline` needs a concrete customer id and timeline projection rows.
- `GET /api/messages/{external_userid}/recent` needs a concrete customer id and message archive projection rows.
- Full readonly dual-run evidence requires the same style of sample to exist on the old Flask test service and AI-CRM Next.

## Minimum Old Flask Test Data

Use masked or synthetic data only. Do not use real customer PII.

| data area | minimum requirement | example safe value |
| --- | --- | --- |
| contact/external_userid | at least 1 customer list row with non-empty `external_userid` | `external_user_masked_001` |
| timeline event | at least 1 event for that external user | `timeline_event_masked_001` |
| recent message | at least 1 recent message for that external user | `msg_masked_001` |
| owner_userid | at least 1 owner value for filter checks | `owner_masked_001` |
| mobile | masked/mobile placeholder only | `mobile_masked_001` |
| tag | at least 1 safe tag if tag filters are tested | `tag_masked_001` |
| class_user_status | at least partial activation/status coverage | `activated`, `not_activated`, or `pending_input` |

## How To Verify The Old Service Sample

Run only GET requests against a local/test old Flask service:

```bash
curl -sS 'http://127.0.0.1:5001/api/customers?limit=5&offset=0'
```

Confirm that at least one item contains a non-empty `external_userid`. Then verify the sample-only read endpoints:

```bash
curl -sS 'http://127.0.0.1:5001/api/customers/{external_userid}'
curl -sS 'http://127.0.0.1:5001/api/customers/{external_userid}/timeline?limit=5&offset=0'
curl -sS 'http://127.0.0.1:5001/api/messages/{external_userid}/recent?limit=5'
```

## If Sample Data Is Missing

The gray smoke and readonly dual-run reports must skip these endpoints with an explicit reason:

- `customer_detail.sample`: `no_customer_sample`
- `customer_timeline.sample`: `no_customer_sample`
- `customer_timeline.page`: `no_customer_sample`
- `recent_messages.sample`: `no_customer_sample`
- `recent_messages.limit`: `no_customer_sample`

Missing sample data blocks full readonly gray evidence for detail/timeline/recent-message routes, but it does not invalidate Next-only list/page smoke.

## Preparing Safe Test Data

- Use synthetic or masked external ids, mobile placeholders, owner ids, tags, and message ids.
- Keep data in local/test databases only.
- Do not backfill production customer data for this preparation step.
- Do not trigger WeCom sync, OpenClaw webhook, tag refresh, message archive sync, or any write endpoint while preparing samples.

## Local Sample Seed Evidence

2026-05-20 local run prepared a masked sample in the old Flask test database only.

The historical customer sample seed helper is retired; see
`docs/archive/experiments_ai_crm_next/retired_tools.md`.

Safety guard:

- Host must be `127.0.0.1`, `localhost`, or `::1`.
- Database name must be exactly `aicrm_old_flask_test` and contain `test`.
- Default mode is dry-run; `--apply` is required to write.
- Passwords are redacted in output.
- The tool does not import `wecom_ability_service` or `openclaw_service`.

Seed data:

| field | value |
| --- | --- |
| `external_userid` | `external_user_masked_001` |
| `customer_name` | `customer_masked_001` |
| `mobile` | `mobile_masked_001` |
| `owner_userid` | `owner_masked_001` |
| `signup_label_name` / tag marker | `tag_masked_001` |
| `msgid` | `msg_masked_001` |

The seed writes only masked local rows into `people`, `contacts`, `external_contact_bindings`, `wecom_external_contact_identity_map`, `wecom_external_contact_follow_users`, `owner_role_map`, `class_user_status_current`, `class_user_status_history`, and `archived_messages`. It keeps tag coverage in `class_user_status_current.signup_label_name` and clears the masked sample's `contact_tags` row so the real old response remains compatible with the current `tags: list[str]` fixture contract.

Old API verification after seed:

- `GET /api/customers`: `200`, `total=1`, sample `external_userid=external_user_masked_001`.
- `GET /api/customers/external_user_masked_001`: `200`, detail includes binding, identity, and sidebar context.
- `GET /api/customers/external_user_masked_001/timeline`: `200`, `total=2`.
- `GET /api/messages/external_user_masked_001/recent?limit=5`: `200`, one masked message.

Old admin page note:

- `GET /admin/customers` on old Flask returns `302 Location: /login?next=/admin/customers`.
- This is a legacy admin-auth/page-layer redirect and is recorded as `legacy_admin_auth_redirect`, not as a Customer API dual-run blocker.
- Next `/admin/customers` must still return `200`.
