# Customer Center Design

## Goal

Merge the current CRM customer list, sidebar customer context, identity/binding data, and class user status into one minimal `customer_center` module.

This round only adds:

- `customer_center` module
- `customer_profile_service`
- `GET /api/customers`
- `GET /api/customers/<external_userid>`

Legacy routes such as `/api/contacts` and `/api/identity/resolve` remain unchanged.

## New Directory Tree

```text
wecom_ability_service/
  customer_center/
    __init__.py
    dto.py
    customer_profile_service.py
```

## Data Contract

Core DTOs:

- `CustomerListItemDTO`
- `CustomerDetailDTO`
- `CustomerTagDTO`
- `CustomerFollowUserDTO`
- `CustomerBindingDTO`
- `CustomerIdentityDTO`
- `CustomerClassStatusDTO`

The detail DTO intentionally mirrors sidebar concerns:

- contact snapshot
- binding status
- identity resolution
- follow users
- tags
- class user status
- `sidebar_context`

## API Draft

### GET `/api/customers`

Query params:

- `owner`
- `tag`
- `status`
- `is_bound`
- `mobile`
- `keyword`

Response:

```json
{
  "ok": true,
  "total": 1,
  "filters": {
    "owner": "sales_01",
    "tag": "高意向",
    "status": "signed_999",
    "is_bound": "true",
    "mobile": "1390",
    "keyword": "客户甲"
  },
  "items": [
    {
      "external_userid": "wm_customer_001",
      "customer_name": "客户甲",
      "display_name": "客户甲",
      "owner_userid": "sales_01",
      "owner_display_name": "顾问一号",
      "mobile": "13900000001",
      "is_bound": true,
      "signup_status": "signed_999",
      "signup_label_name": "已报名999",
      "tags": [],
      "updated_at": "2026-03-24 10:00:00"
    }
  ]
}
```

### GET `/api/customers/<external_userid>`

Response:

```json
{
  "ok": true,
  "customer": {
    "external_userid": "wm_customer_detail_001",
    "customer_name": "客户详情",
    "display_name": "客户详情",
    "owner_userid": "sales_09",
    "owner_display_name": "顾问九号",
    "mobile": "13700000009",
    "binding": {},
    "identity": {},
    "class_status": {},
    "tags": [],
    "follow_users": [],
    "sidebar_context": {}
  }
}
```

## Compatibility

- `/api/contacts` remains the legacy contact snapshot API
- `/api/identity/resolve` remains the legacy identity resolver
- No callback/job/openclaw/questionnaire rewrites in this round
- New customer center reads from existing local tables only

## Risks

- Current implementation aggregates in Python and may become slower when customer volume grows materially
- Tag filtering currently matches local `contact_tags` snapshots and class status label names, so stale local tag snapshots can still affect list filtering
- `sidebar_context` is a read model assembled from existing local sources, not a new canonical model yet

## Test Plan

- keep existing test suite green
- add `/api/customers` list filter test
- add `/api/customers/<external_userid>` detail aggregation test
- manually verify old `/api/contacts` and `/api/identity/resolve` behavior remains unchanged

## Rollback Plan

If needed, rollback is low-risk:

1. remove the two new routes
2. stop importing `customer_center`
3. keep old CRM/sidebar routes as-is
4. leave the new module files unused until the next iteration
