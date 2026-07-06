# Product Management Route Cutover Manifest

This manifest describes route ownership and side-effect risk for a future Product Management gray release. It is preparation evidence only; no production traffic is switched by this document.

| route | method | old_owner | next_owner | route_type | side_effect_risk | current_next_status | gray_ready | rollback_route | smoke_command | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/wechat-pay/products` | GET | old Flask product admin page | AI-CRM Next `frontend_compat` | page | read | partial adapter, screenshot baseline pass | yes_readonly | old Flask `/admin/wechat-pay/products` | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Product management shell only; no payment call. |
| `/api/admin/wechat-pay/products` | GET | old Flask product API | AI-CRM Next commerce API | api | read | parity_ready partial | yes_readonly | old Flask `/api/admin/wechat-pay/products` | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | List shape compatibility. |
| `/api/admin/wechat-pay/products/{product_id}` | GET | old Flask product detail API | AI-CRM Next commerce API | api | read | contract_ready partial | yes_after_sample | old Flask detail route | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Smoke uses a sample product from Next list. |
| `/api/admin/wechat-pay/products` | POST | old Flask product API | AI-CRM Next commerce API | api | write | contract_ready fake/in-memory | fake_write_only | old Flask `/api/admin/wechat-pay/products` | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient --include-fake-writes` | Next fake-write smoke only; never old Flask. |
| `/api/admin/wechat-pay/products/{product_id}` | PUT | old Flask product update API | AI-CRM Next commerce API | api | write | contract_ready fake/in-memory | fake_write_only | old Flask detail route | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient --include-fake-writes` | Next fake-write smoke only. |
| `/api/admin/wechat-pay/products/{product_id}/enable` | POST | old Flask product enable API | AI-CRM Next commerce API | api | write | contract_ready fake/in-memory | fake_write_only | old Flask enable route | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient --include-fake-writes` | Next fake-write smoke only. |
| `/api/admin/wechat-pay/products/{product_id}/disable` | POST | old Flask product disable API | AI-CRM Next commerce API | api | write | contract_ready fake/in-memory | fake_write_only | old Flask disable route | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient --include-fake-writes` | Next fake-write smoke only. |
| `/api/admin/wechat-pay/products/{product_id}` | DELETE | old Flask product delete API | AI-CRM Next commerce API | api | write | contract_ready soft delete | no_production | old Flask delete route | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient --include-fake-writes` | No production destructive operation in this phase. |
| `/p/{page_slug}` | GET | old Flask public product page | AI-CRM Next commerce page | page | read | contract_ready partial | yes_after_sample | old Flask public product route | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Smoke uses fixture slug `course-masked-001`. |
| `/api/products/{page_slug}` | GET | old Flask public product API | AI-CRM Next commerce API | api | read | contract_ready partial | yes_after_sample | old Flask public product API | `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md --next-testclient` | Public shape compatibility only. |
| `/api/checkout/wechat` | POST | old Flask WeChat checkout | AI-CRM Next fake checkout | api | payment_external | fake/stubbed | no_production | old Flask checkout route | not in gray smoke | Checkout is not a Product Management gray route. |
| `/api/checkout/alipay` | POST | old Flask Alipay checkout | AI-CRM Next fake checkout | api | payment_external | fake/stubbed | no_production | old Flask checkout route | not in gray smoke | Checkout is not a Product Management gray route. |

## Safety Notes

- Default gray smoke only runs read endpoints.
- Fake-write smoke is explicit opt-in and only targets AI-CRM Next TestClient.
- Checkout, notify, provider signing, and external payment calls remain not gray-ready.
- Rollback always points to old Flask route ownership until production cutover is approved.
