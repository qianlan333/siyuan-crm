# Batch 5 Questionnaire Readonly Proxy Pseudo Config

Every example in this file is PSEUDO ONLY. Do not apply directly to production. The examples do not contain production hosts or secrets.

## Route Flags

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true
AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false
AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false
AICRM_NEXT_QUESTIONNAIRE_OAUTH=false
AICRM_NEXT_EXTERNAL_WECOM_TAG=false
AICRM_NEXT_EXTERNAL_WEBHOOK=false
```

Rollback:

```bash
# PSEUDO ONLY - staging example, do not apply to production
AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
```

## Header Allowlist

```nginx
# PSEUDO ONLY - staging example, do not apply to production
location /admin/questionnaires {
    if ($http_x_aicrm_next_canary = "questionnaire-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/admin/questionnaires {
    if ($http_x_aicrm_next_canary = "questionnaire-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /s/ {
    if ($http_x_aicrm_next_canary = "questionnaire-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - staging example, do not apply to production
location /api/h5/questionnaires/ {
    if ($http_x_aicrm_next_canary = "questionnaire-readonly") {
        proxy_pass http://aicrm_next_staging;
    }
    proxy_pass http://old_flask_staging;
}
```

## Excluded Write And External Routes

```nginx
# PSEUDO ONLY - admin writes excluded from Batch 5, do not apply to production
location /api/admin/questionnaires-write-placeholder {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - submit excluded from Batch 5, do not apply to production
location /api/h5/questionnaires-submit-placeholder {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - OAuth excluded from Batch 5, do not apply to production
location /api/h5/wechat/oauth/ {
    proxy_pass http://old_flask_staging;
}

# PSEUDO ONLY - external push/retry/webhook excluded from Batch 5, do not apply to production
location /api/questionnaire-external-placeholder {
    proxy_pass http://old_flask_staging;
}
```

## Safety

- PSEUDO ONLY examples.
- Staging router only.
- No production host.
- No secrets.
- No admin writes.
- No H5 submit.
- No real OAuth.
- No WeCom tag mutation.
- No external webhook push or retry.
