# Batch 4 User Ops Readonly Proxy Pseudo Config

Every example in this file is PSEUDO ONLY. Do not apply directly to production. The examples do not contain production hosts or secrets.

## Route Flags

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_USER_OPS_READONLY=true
AICRM_NEXT_ROUTE_USER_OPS_WRITES=false
AICRM_NEXT_USER_OPS_DND=false
AICRM_NEXT_USER_OPS_BATCH_SEND=false
AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false
AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

Rollback:

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
```

## Header Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/user-ops/ui {
    if ($http_x_aicrm_next_canary = "user-ops-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/user-ops/overview {
    if ($http_x_aicrm_next_canary = "user-ops-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/user-ops/list {
    if ($http_x_aicrm_next_canary = "user-ops-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/user-ops/send-records {
    if ($http_x_aicrm_next_canary = "user-ops-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Excluded Write And External Routes

```nginx
# PSEUDO ONLY - DND excluded from Batch 4, do not apply to production
location /api/admin/user-ops/do-not-disturb {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - batch-send preview excluded from Batch 4, do not apply to production
location /api/admin/user-ops/batch-send/preview {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - batch-send execute excluded from Batch 4, do not apply to production
location /api/admin/user-ops/batch-send/execute {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - deferred jobs excluded from Batch 4, do not apply to production
location /api/admin/user-ops/run-deferred-jobs {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - internal User Ops writes excluded from Batch 4, do not apply to production
location /api/internal/user-ops/ {
    proxy_pass http://old_flask_staging;
}
```

## Safety

- PSEUDO ONLY examples.
- Staging router only.
- No production host.
- No secrets.
- No DND writes.
- No batch-send preview or execute.
- No deferred jobs.
- No internal User Ops jobs.
- No WeCom dispatch.
- No WeCom media upload.
