# Post-Legacy Next Development Rules

Post-Legacy Architecture Freeze 后，AI-CRM production runtime 的默认架构是 Next-owned。本文档是后续 PR、Codex 执行、route owner 审核和 smoke 验收的硬规则。

## 1. 全局原则

- 所有新功能必须 Next-owned。
- 禁止新增 production_compat。也禁止新增 `production_compat` 变体或别名。
- 禁止新增 legacy Flask forward。
- 禁止新增 compatibility facade。
- 禁止在新 runtime path 中引用 `wecom_ability_service` 旧 Flask handler。
- 禁止在新 runtime path 中引用 `legacy_flask_facade`。
- 新 route 必须登记 route registry、production route ownership manifest、owner、lifecycle、smoke、no-real-external 默认行为。
- 新页面必须有页面 route、template / JS、API matrix、smoke、no empty shell check。
- runtime route 必须保持 `production_compat_route_count=0`、`production_compat_catch_all_count=0`、`wildcard_legacy_forward_count=0`、`legacy_fallback_routes_count=0`。
- `DEFERRED_FRONTEND_API_PATTERNS` 必须保持空集合；如确需 API-only route，必须在 PR 说明 API-only 生命周期和 smoke 覆盖。

## 2. 禁止重复造轮子规则

### 成员 / 客户选择

必须优先复用：

- `aicrm_next.customer_read_model`
- `aicrm_next.identity_contact`
- `aicrm_next.common_operation_members`
- `aicrm_next.ops_enrollment`
- 现有 customer drawer / member selector / API contract

禁止：

- 新建平行客户查询 service
- 新建重复 customer/member lookup endpoint
- 直接读旧 Flask customer service
- 为单个页面私有复制 member selector

### 群发 / 运营发送 / 触达

必须优先复用：

- `aicrm_next.cloud_orchestrator`
- `aicrm_next.automation_engine`
- `aicrm_next.user_ops`
- `CommandBus`
- `AuditLedger`
- `SideEffectPlan`
- `ExternalCallAttempt`
- 现有 safe-mode send plan contract

禁止：

- 在页面里直接执行真实发送
- 新建绕过 `SideEffectPlan` 的发送 adapter
- 默认开启 WeCom/Bazhuayu/OpenClaw
- 绕过 idempotency / audit

### 支付 / 商品 / 订单

必须优先复用：

- `aicrm_next.commerce`
- `aicrm_next.public_product`
- `CheckoutCommand`
- `GetOrderQuery`
- `NotifyPaymentCommand`
- `PaymentReturnCommand`
- existing guarded payment adapters

禁止：

- 新建第二套 checkout
- 新建第二套 order repo
- 新建第二套 payment notify parser
- 默认开启真实 WeChat Pay / Alipay
- 绕过 fake/real_blocked adapter

### 媒体 / 图片 / 附件 / 小程序素材

必须优先复用：

- `aicrm_next.media_library`
- existing image / attachment / miniprogram APIs
- existing picker contract
- existing no-real-storage guard

禁止：

- 新建页面私有 upload endpoint
- 直接 `requests`/`httpx` 拉远程素材
- 直接调用外部 storage
- 直接上传企微素材

### WeCom tags / customer acquisition / JSSDK

必须优先复用：

- `aicrm_next.customer_tags`
- `aicrm_next.auth_wecom`
- `aicrm_next.identity_contact.sidebar_jssdk`
- `aicrm_next.automation_engine.channels_api` 中的 customer acquisition safe-mode API

禁止：

- 新建第二套标签 catalog
- 直接调用 WeCom token / access_token
- 默认开启真实 WeCom API
- 页面按钮直连外部 WeCom

### Questionnaire / H5 / OAuth

必须优先复用：

- `aicrm_next.questionnaire`
- questionnaire admin read/write
- H5 submit / diagnostics
- Next OAuth adapter

禁止：

- 新建 parallel H5 submit
- 新建 parallel OAuth flow
- 恢复 legacy H5 route

## 3. 新功能 PR 必须包含

- inventory
- frontend/API/backend matrix
- route registry
- production manifest
- route precedence test
- no compatibility facade test
- no real external default test
- representative smoke
- final 验收结论

PR 验收语言必须区分本地验证、production route resolution、strict guard、representative smoke。没有完成 route registry / production manifest / smoke 的页面或 API 不能称为 production accepted。
