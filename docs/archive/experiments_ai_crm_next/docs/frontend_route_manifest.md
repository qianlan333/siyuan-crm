# Frontend Route Manifest

This manifest defines the AI-CRM Next route-level frontend smoke baseline. It does not redesign pages and does not compare full visual parity. It verifies that copied legacy adapters render, expected text appears, forbidden new-UI placeholder text is absent, and a screenshot or HTML snapshot artifact can be produced.

Forbidden placeholder text for every route:

- `New UI`
- `redesign`
- `TODO replace old frontend`
- `experimental replacement UI`
- `new dashboard placeholder`

| route | expected_status | frontend_source | parity_status | must_contain_text | must_not_contain_text | screenshot_required | notes |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `GET /admin` | 200 | copied legacy admin shell via `frontend_compat` | partial adapter | `后台`, `客户`, `问卷` | forbidden placeholder list | yes | Dashboard shell baseline; not production auth. |
| `GET /admin/customers` | 200 | copied `aicrm_next/frontend_compat/templates/admin_console/customers.html` | partial adapter | `客户`, `筛选`, `负责人` | forbidden placeholder list | yes | Fixture customer list; real dual-run sample detail remains pending richer old data. |
| `GET /admin/user-ops/ui` | 200 | active admin shell target for legacy entry | route-level smoke only | `客户激活 / 客户列表`, `客户管理后台`, `问卷` | forbidden placeholder list | yes | Current smoke follows the active admin shell target for this legacy entry. |
| `GET /admin/questionnaires` | 200 | copied `aicrm_next/questionnaire/templates/admin_console/questionnaires.html` | partial adapter | `问卷`, `创建`, `编辑` | forbidden placeholder list | yes | Admin questionnaire list/editor baseline. |
| `GET /admin/questionnaires/ui` | 200 | copied `aicrm_next/questionnaire/templates/admin_console/questionnaires.html` | partial adapter | `问卷`, `创建`, `编辑` | forbidden placeholder list | yes | Alias kept for old entry compatibility. |
| `GET /admin/wechat-pay/products` | 200 | legacy admin shell partial adapter | partial adapter | `微信支付商品管理`, `商品`, `价格` | forbidden placeholder list | yes | Product management contract surfaced through partial shell. |
| `GET /admin/wechat-pay/transactions` | 200 | copied `aicrm_next/frontend_compat/templates/admin_console/wechat_pay_transactions.html` | partial adapter | `微信支付`, `交易`, `订单` | forbidden placeholder list | yes | Fake payment transaction data only. |
| `GET /admin/alipay/transactions` | 200 | legacy admin shell partial adapter | partial adapter | `支付宝交易管理`, `支付宝`, `交易` | forbidden placeholder list | yes | Fake Alipay transaction contract; exact old page still partial. |
| `GET /admin/image-library` | 200 | copied `aicrm_next/frontend_compat/templates/admin_console/image_library.html` | partial adapter | `图片`, `素材`, `上传` | forbidden placeholder list | yes | Fixture media only; no cloud or WeCom upload. |
| `GET /admin/attachment-library` | 200 | legacy admin shell partial adapter | partial adapter | `附件素材库`, `附件`, `素材` | forbidden placeholder list | yes | Attachment page is partial shell until exact old template is available. |
| `GET /admin/miniprogram-library` | 200 | copied `aicrm_next/frontend_compat/templates/admin_console/miniprogram_library.html` | partial adapter | `小程序`, `素材`, `appid` | forbidden placeholder list | yes | Fixture mini-program materials only. |
| `GET /s/hxc-activation-v1` | 200 | copied `questionnaire_h5_page.html` | partial adapter | `问卷`, `提交` | forbidden placeholder list | yes | Public H5 questionnaire fixture; fake identity/OAuth only. |
| `GET /p/course-masked-001` | 200 | simple public product contract page | partial adapter | `商品`, `购买` | forbidden placeholder list | yes | Uses current fixture page_slug `course-masked-001`; no real payment. |

`/p/course-masked-001` is the current fixture-backed public product slug. Do not hard-code `/p/product-demo` unless that fixture is added later.
