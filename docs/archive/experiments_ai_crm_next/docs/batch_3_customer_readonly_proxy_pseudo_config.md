# Batch 3 Customer Readonly Proxy Pseudo Config

Every example in this file is PSEUDO ONLY. Do not apply directly to production. The examples do not contain production hosts or secrets.

## Route Flags

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=true
AICRM_NEXT_ROUTE_CUSTOMER_WRITES=false
AICRM_NEXT_EXTERNAL_WECOM_SYNC=false
AICRM_NEXT_EXTERNAL_ARCHIVE_SYNC=false
AICRM_NEXT_EXTERNAL_TAG_REFRESH=false
AICRM_NEXT_EXTERNAL_OPENCLAW=false
```

Rollback:

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
```

## Header Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/customers {
    if ($http_x_aicrm_next_canary = "customer-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/customers {
    if ($http_x_aicrm_next_canary = "customer-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/messages {
    if ($http_x_aicrm_next_canary = "customer-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## External Operations Remain Excluded

```nginx
# PSEUDO ONLY - external operations excluded from Batch 3, do not apply to production
# WeCom contact sync: disabled
# Archive sync: disabled
# Tag refresh: disabled
# OpenClaw push/webhook: disabled
# Customer writes: disabled
```

## Safety

- PSEUDO ONLY examples.
- Staging router only.
- No production host.
- No secrets.
- No customer write routes.
- No WeCom sync.
- No archive sync.
- No tag refresh.
- No OpenClaw push or webhook.
