# User Ops Readonly Sample And Drift Checklist

Readonly gray preparation does not require and must not execute write endpoints. Data samples improve filter coverage and send-record detail coverage, but missing samples should be recorded honestly rather than filled with real customer data.

## Current Overview Contract

The current User Ops overview contract has 8 cards:

- `引流品总数`
- `已加微`
- `未加微`
- `已绑手机号`
- `未绑手机号`
- `黄小璨已激活`
- `黄小璨未激活`
- `激活待录入`

Old Flask missing `激活待录入` while Next includes it is legacy drift. It is acceptable for readonly gray preparation when recorded as `legacy_missing_required_card_label`. Next missing `激活待录入` is a blocker.

Old `/admin/user-ops/ui` returning a login redirect in unauthenticated local checks is page-layer auth behavior. Record it as `legacy_admin_auth_redirect` if Next returns `200`; do not change old auth logic to make the smoke pass.

## Minimum Test Data For Stronger Readonly Coverage

| area | recommended masked sample | impact if missing |
| --- | --- | --- |
| WeCom status | one `added`, one `not_added` item | Filter route can still pass shape-only, but full filter semantics remain partial. |
| Mobile binding | one `bound`, one `unbound` item | `mobile_binding_status=bound` can pass shape-only, but unbound coverage remains partial. |
| Activation bucket | one `activated`, one `not_activated`, one `pending_input` item | `activation_bucket=activated` can pass shape-only; pending input drift should be checked before full gray. |
| Class term | at least one masked `class_term_no` and label | Class-term filter coverage remains partial. |
| Owner | at least one masked `owner_userid` | Owner filter coverage remains partial. |
| Send records | at least one send record with masked operator/sender | `/send-records/{record_id}` remains sample-dependent if no record exists. |

## Allowed Shape-Only Cases

- Empty list results are acceptable for list/filter shape smoke if required response keys are present.
- Send-record list can pass with `items=[]`; detail smoke must be skipped unless a record id is available.
- Old missing `激活待录入` is accepted only when Next satisfies the current contract.

## Full Readonly Gray Blockers

- Default smoke includes any POST/PUT/PATCH/DELETE route.
- Old Flask receives DND, batch-send preview/execute, deferred jobs, or internal User Ops writes.
- Real WeCom dispatch or media upload is triggered.
- Next misses any required overview/list/send-record contract key.
- Old and Next both miss a required overview card.

## Preparing Masked Samples

Use only local test databases and masked identifiers such as:

- `mobile_masked_001`
- `external_user_masked_001`
- `owner_masked_001`
- `class_term_masked_001`
- `record_masked_001`

Do not use real phone-number formats, real external user ids, real customer names, or production database connections.
