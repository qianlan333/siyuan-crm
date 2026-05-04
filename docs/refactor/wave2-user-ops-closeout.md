# Wave 2 User Ops Closeout

## 已收口写面

- `schedule_user_ops_auto_assign_class_term_job`
- `run_due_user_ops_deferred_jobs`
- `upsert_sidebar_lead_pool_class_term`
- `import_experience_leads`
- `import_mobile_class_term_source`
- `import_activation_status_source`
- `backfill_owner_class_terms_into_lead_pool`
- `backfill_class_term_for_owner`
- `refresh_contact_tags_for_external_userid`
- `refresh_user_ops_contact_tags_for_external_userid`
- `refresh_user_ops_contact_tags_for_owner`
- `upsert_user_ops_huangxiaocan_activation_source`
- `migrate_legacy_user_ops_pool_to_lead_pool`

以上入口的正式 owner 已统一收敛到 `wecom_ability_service/application/user_ops/*`。当前阶段仍通过 `_legacy_delegate.py` 薄包装转调 legacy domain，实现行为兼容优先。

## 保留例外

- `write_user_ops_lead_pool_history`
- `upsert_user_ops_lead_pool_member`

这两个符号仍保留在 `services.py` 兼容层可见，但定位为 internal primitive。后续新 caller 不允许直接使用；仅允许 application command 内部或测试兼容路径继续引用。

## 当前阶段结论

- `services.py` 不再承担 user_ops 主写入口 owner。
- admin / background / sidebar / import / backfill / deferred jobs 的主要写入口已统一经由 `application/user_ops/*`。
- `domains/user_ops/service.py` 仍然是底层 legacy delegate 实现承载体，但不再是新 caller 默认入口。

这意味着 user_ops 已达到“主写入口统一”的阶段性完成标准，可以在后续独立 PR 中进入内部模块拆分，而不是继续扩大 caller cutover 范围。
