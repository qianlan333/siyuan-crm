# Batch 1 Media Readonly Proxy Pseudo Config

Every example in this file is PSEUDO ONLY. Do not apply directly to production. The examples do not contain production hosts or secrets.

## Route Flags

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_MEDIA_READONLY=true
AICRM_NEXT_ROUTE_MEDIA_WRITES=false
AICRM_NEXT_EXTERNAL_CLOUD_STORAGE=false
AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false
```

Rollback:

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_MEDIA_READONLY=false
```

## Header Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/image-library {
    if ($http_x_aicrm_next_canary = "media-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/image-library {
    if ($http_x_aicrm_next_canary = "media-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Cookie Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/attachment-library {
    if ($cookie_aicrm_next_canary = "media-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/attachment-library {
    if ($cookie_aicrm_next_canary = "media-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Miniprogram Routes

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/miniprogram-library {
    if ($http_x_aicrm_next_canary = "media-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/miniprogram-library {
    if ($http_x_aicrm_next_canary = "media-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Safety

- PSEUDO ONLY examples.
- Staging router only.
- No production host.
- No secrets.
- No write routes.
- No cloud storage upload.
- No WeCom media upload.
