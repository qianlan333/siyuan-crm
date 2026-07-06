# AI-CRM Next Fast Readonly Human Test Tasks

Use this checklist after each readonly batch is manually routed. The user only needs to record `pass` or `issue` for each item. Do not test writes in this checklist.

## Batch 1: Media Library Readonly

Tester opens:

- `/admin/image-library`
- `/admin/attachment-library`
- `/admin/miniprogram-library`

Check:

- image library page opens
- attachment library page opens
- miniprogram library page opens
- list data looks plausible
- no upload/create/edit/delete action is triggered
- no cloud upload or WeCom media upload appears

Result:

| item | pass / issue | notes |
| --- | --- | --- |
| image library page |  |  |
| attachment library page |  |  |
| miniprogram library page |  |  |
| no write/upload action |  |  |

## Batch 2: Product Management Readonly

Tester opens:

- `/admin/wechat-pay/products`
- one product detail if available
- one public product page `/p/{page_slug}` if available

Check:

- admin product list opens
- product detail reads normally
- public product page reads normally
- checkout/payment is not triggered
- no product create/update/enable/disable/delete is triggered

Result:

| item | pass / issue | notes |
| --- | --- | --- |
| product admin list |  |  |
| product detail |  |  |
| public product page |  |  |
| no checkout/payment |  |  |

## Batch 3: Customer Read Model Readonly

Tester opens:

- `/admin/customers`
- one customer detail if available
- that customer's timeline
- that customer's recent messages

Check:

- customer list opens
- filters/search behave as expected for read use
- detail page fields look plausible
- timeline appears
- recent messages appear
- no WeCom sync, archive sync, tag refresh, or OpenClaw action is triggered

Result:

| item | pass / issue | notes |
| --- | --- | --- |
| customer list |  |  |
| customer detail |  |  |
| timeline |  |  |
| recent messages |  |  |
| no external sync |  |  |

## Batch 4: User Ops Readonly

Tester opens:

- `/admin/user-ops/ui`
- overview area
- user list with common filters
- send records list

Check:

- overview cards display
- `激活待录入` exists in Next view
- list opens and filters work for read use
- send records opens
- DND/batch-send/deferred jobs are not executed
- no WeCom dispatch/media upload is triggered

Result:

| item | pass / issue | notes |
| --- | --- | --- |
| overview |  |  |
| `激活待录入` card |  |  |
| list filters |  |  |
| send records |  |  |
| no write/WeCom action |  |  |

## Batch 5: Questionnaire Readonly

Tester opens:

- `/admin/questionnaires`
- one questionnaire detail if available
- one public H5 page `/s/{slug}` if available
- readonly result if sample exists

Check:

- admin list opens
- detail/export/debug read views are normal
- public H5 page opens
- result read route works or documented legacy drift is acceptable
- no submit, OAuth, WeCom tag, or webhook is triggered

Result:

| item | pass / issue | notes |
| --- | --- | --- |
| admin list |  |  |
| questionnaire detail |  |  |
| public H5 page |  |  |
| readonly result |  |  |
| no submit/external action |  |  |

## Retired Automation Conversion Readonly Batch

Do not test old automation program overview, pool, member detail, execution-record,
manual override, confirm conversion, activation webhook, OpenClaw push, workflow
runtime, or Runtime V2 routes. Those surfaces are retired. The surviving
`/admin/automation-conversion` page belongs to `ai_audience_ops` and should be
validated by the main application AI Audience admin page tests instead.

## User Response Format

After each batch, reply with:

```text
Batch:
Result: pass / issue
Issues:
Screenshots or notes:
Continue next batch: yes / no
```
