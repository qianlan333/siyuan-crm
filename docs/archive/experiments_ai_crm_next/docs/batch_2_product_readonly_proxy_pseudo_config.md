# Batch 2 Product Readonly Proxy Pseudo Config

Every example in this file is PSEUDO ONLY. Do not apply directly to production. The examples do not contain production hosts or secrets.

## Route Flags

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_PRODUCT_READONLY=true
AICRM_NEXT_ROUTE_PRODUCT_WRITES=false
AICRM_NEXT_ROUTE_CHECKOUT=false
AICRM_NEXT_EXTERNAL_WECHAT_PAY=false
AICRM_NEXT_EXTERNAL_ALIPAY=false
```

Rollback:

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
```

## Header Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/wechat-pay/products {
    if ($http_x_aicrm_next_canary = "product-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/wechat-pay/products {
    if ($http_x_aicrm_next_canary = "product-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Public Product Routes

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /p/ {
    if ($http_x_aicrm_next_canary = "product-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/products/ {
    if ($http_x_aicrm_next_canary = "product-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Checkout And Payment Remain Excluded

```nginx
# PSEUDO ONLY - checkout excluded from Batch 2, do not apply to production
location /api/checkout/wechat {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - checkout excluded from Batch 2, do not apply to production
location /api/checkout/alipay {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - payment notify excluded from Batch 2, do not apply to production
location /api/wechat-pay/notify {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - payment notify excluded from Batch 2, do not apply to production
location /api/alipay/notify {
    proxy_pass http://old_flask_staging;
}
```

## Safety

- PSEUDO ONLY examples.
- Staging router only.
- No production host.
- No secrets.
- No product write routes.
- No checkout.
- No payment notify.
- No WeChat Pay or Alipay provider call.
