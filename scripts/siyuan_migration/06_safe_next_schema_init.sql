-- Safe, idempotent AI-CRM Next schema init for siyuan staging rehearsal.
-- This file only creates missing Next read-model tables and indexes.
-- It must not DROP, TRUNCATE, or overwrite production data.

CREATE TABLE IF NOT EXISTS customer_list_index_next (
    id BIGSERIAL PRIMARY KEY,
    person_id TEXT,
    external_userid TEXT NOT NULL,
    customer_name TEXT NOT NULL DEFAULT '',
    owner_userid TEXT NOT NULL DEFAULT '',
    owner_display_name TEXT NOT NULL DEFAULT '',
    remark TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    mobile TEXT,
    is_bound BOOLEAN NOT NULL DEFAULT false,
    binding_status TEXT NOT NULL DEFAULT 'unbound',
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    class_user_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_message_at TIMESTAMPTZ,
    last_touch_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_detail_snapshot_next (
    id BIGSERIAL PRIMARY KEY,
    person_id TEXT,
    external_userid TEXT NOT NULL,
    customer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    binding_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    follow_users_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    marketing_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    marketing_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    contact_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sidebar_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_timeline_event_next (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    person_id TEXT,
    external_userid TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    source_table TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_recent_message_next (
    id BIGSERIAL PRIMARY KEY,
    msgid TEXT NOT NULL,
    external_userid TEXT NOT NULL,
    msgtype TEXT NOT NULL DEFAULT 'text',
    content TEXT NOT NULL DEFAULT '',
    send_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_userid TEXT,
    chat_type TEXT NOT NULL DEFAULT 'single',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_external_userid ON customer_list_index_next (external_userid);
CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_owner_userid ON customer_list_index_next (owner_userid);
CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_mobile ON customer_list_index_next (mobile);
CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_updated_at ON customer_list_index_next (updated_at);
CREATE INDEX IF NOT EXISTS ix_customer_detail_snapshot_next_external_userid ON customer_detail_snapshot_next (external_userid);
CREATE INDEX IF NOT EXISTS ix_customer_timeline_event_next_external_userid ON customer_timeline_event_next (external_userid);
CREATE INDEX IF NOT EXISTS ix_customer_timeline_event_next_event_type ON customer_timeline_event_next (event_type);
CREATE INDEX IF NOT EXISTS ix_customer_timeline_event_next_event_time ON customer_timeline_event_next (event_time);
CREATE INDEX IF NOT EXISTS ix_customer_recent_message_next_external_userid ON customer_recent_message_next (external_userid);
CREATE INDEX IF NOT EXISTS ix_customer_recent_message_next_send_time ON customer_recent_message_next (send_time);

CREATE TABLE IF NOT EXISTS user_ops_pool_current_next (
    id BIGSERIAL PRIMARY KEY,
    person_id TEXT,
    mobile TEXT,
    external_userid TEXT,
    customer_name TEXT NOT NULL DEFAULT '',
    owner_userid TEXT,
    owner_display_name TEXT NOT NULL DEFAULT '',
    class_term_no TEXT,
    class_term_label TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'lead_pool',
    activation_bucket TEXT NOT NULL DEFAULT 'pending_input',
    activation_bucket_label TEXT NOT NULL DEFAULT '激活待录入',
    is_mobile_bound BOOLEAN NOT NULL DEFAULT false,
    auto_do_not_disturb_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_ops_do_not_disturb_next (
    id BIGSERIAL PRIMARY KEY,
    external_userid TEXT,
    mobile TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual',
    reason_code TEXT NOT NULL DEFAULT 'manual_set',
    reason_text TEXT NOT NULL DEFAULT '运营设置',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_ops_send_records_next (
    id BIGSERIAL PRIMARY KEY,
    record_key TEXT NOT NULL UNIQUE,
    task_type TEXT NOT NULL DEFAULT 'user_ops_batch_send',
    outbound_task_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    task_results_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_count INTEGER NOT NULL DEFAULT 0,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    skipped_reasons_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    include_do_not_disturb BOOLEAN NOT NULL DEFAULT false,
    content_preview TEXT NOT NULL DEFAULT '',
    image_count INTEGER NOT NULL DEFAULT 0,
    sender_userids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    filter_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    status_label TEXT NOT NULL DEFAULT '已创建任务',
    last_status_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_external_userid ON user_ops_pool_current_next (external_userid);
CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_mobile ON user_ops_pool_current_next (mobile);
CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_owner_userid ON user_ops_pool_current_next (owner_userid);
CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_class_term_no ON user_ops_pool_current_next (class_term_no);
CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_activation_bucket ON user_ops_pool_current_next (activation_bucket);
CREATE INDEX IF NOT EXISTS ix_user_ops_dnd_next_external_userid ON user_ops_do_not_disturb_next (external_userid);
CREATE INDEX IF NOT EXISTS ix_user_ops_dnd_next_mobile ON user_ops_do_not_disturb_next (mobile);
CREATE INDEX IF NOT EXISTS ix_user_ops_dnd_next_active_reason ON user_ops_do_not_disturb_next (is_active, reason_code);
CREATE INDEX IF NOT EXISTS ix_user_ops_send_records_next_created_at ON user_ops_send_records_next (created_at);
CREATE INDEX IF NOT EXISTS ix_user_ops_send_records_next_status ON user_ops_send_records_next (status);
