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

CREATE TABLE IF NOT EXISTS automation_event_v2 (
    id BIGSERIAL PRIMARY KEY,
    event_uid TEXT NOT NULL,
    event_type TEXT NOT NULL,
    program_id BIGINT,
    channel_id BIGINT,
    binding_id BIGINT,
    external_userid TEXT,
    phone TEXT,
    person_id BIGINT,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    raw_occurred_at TIMESTAMPTZ,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_automation_event_v2_source UNIQUE (source_type, source_id),
    CONSTRAINT uq_automation_event_v2_idempotency UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_automation_event_v2_program_event ON automation_event_v2 (program_id, event_type, occurred_at);
CREATE INDEX IF NOT EXISTS idx_automation_event_v2_external ON automation_event_v2 (external_userid);

CREATE TABLE IF NOT EXISTS automation_membership_v2 (
    id BIGSERIAL PRIMARY KEY,
    program_id BIGINT NOT NULL,
    external_userid TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    person_id BIGINT,
    source_channel_id BIGINT,
    source_binding_id BIGINT,
    status TEXT NOT NULL DEFAULT 'active',
    current_stage TEXT NOT NULL DEFAULT 'pending_questionnaire',
    current_stage_entry_id BIGINT,
    joined_at TIMESTAMPTZ NOT NULL,
    exited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_automation_membership_v2_program_external UNIQUE (program_id, external_userid)
);

CREATE INDEX IF NOT EXISTS idx_automation_membership_v2_program_stage ON automation_membership_v2 (program_id, current_stage, status);

CREATE TABLE IF NOT EXISTS automation_stage_entry_v2 (
    id BIGSERIAL PRIMARY KEY,
    membership_id BIGINT NOT NULL,
    program_id BIGINT NOT NULL,
    stage_code TEXT NOT NULL,
    entered_at TIMESTAMPTZ NOT NULL,
    exited_at TIMESTAMPTZ,
    source_event_id BIGINT NOT NULL,
    entry_reason TEXT NOT NULL,
    snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_automation_stage_entry_v2_source UNIQUE (membership_id, stage_code, source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_automation_stage_entry_v2_program_stage ON automation_stage_entry_v2 (program_id, stage_code, entered_at);

CREATE TABLE IF NOT EXISTS automation_task_plan_v2 (
    id BIGSERIAL PRIMARY KEY,
    program_id BIGINT NOT NULL,
    task_id BIGINT NOT NULL,
    membership_id BIGINT NOT NULL,
    event_id BIGINT,
    stage_entry_id BIGINT,
    schedule_key TEXT NOT NULL DEFAULT '',
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    skip_reason TEXT NOT NULL DEFAULT '',
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rendered_content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    broadcast_job_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_task_plan_v2_event ON automation_task_plan_v2 (task_id, membership_id, event_id) WHERE event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_task_plan_v2_stage ON automation_task_plan_v2 (task_id, membership_id, stage_entry_id) WHERE stage_entry_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_task_plan_v2_schedule ON automation_task_plan_v2 (task_id, membership_id, schedule_key) WHERE schedule_key <> '';
CREATE INDEX IF NOT EXISTS idx_automation_task_plan_v2_program_status ON automation_task_plan_v2 (program_id, status, created_at);

CREATE TABLE IF NOT EXISTS wechat_shop_refunds (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL DEFAULT '',
    transaction_id TEXT NOT NULL DEFAULT '',
    out_refund_no TEXT NOT NULL UNIQUE,
    aftersale_id TEXT NOT NULL DEFAULT '',
    refund_amount_total INTEGER NOT NULL DEFAULT 0,
    order_amount_total INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'CNY',
    status TEXT NOT NULL DEFAULT 'requested',
    reason TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wechat_shop_refunds_order ON wechat_shop_refunds (order_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_wechat_shop_refunds_status ON wechat_shop_refunds (status, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_wechat_shop_refunds_aftersale ON wechat_shop_refunds (aftersale_id) WHERE aftersale_id <> '';

CREATE TABLE IF NOT EXISTS wechat_shop_sync_runs (
    id BIGSERIAL PRIMARY KEY,
    sync_type TEXT NOT NULL DEFAULT '',
    time_mode TEXT NOT NULL DEFAULT '',
    range_start TIMESTAMPTZ,
    range_end TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    scanned_count INTEGER NOT NULL DEFAULT 0,
    synced_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    next_key TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wechat_shop_sync_runs_started ON wechat_shop_sync_runs (started_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_wechat_shop_sync_runs_type_status ON wechat_shop_sync_runs (sync_type, status, range_end DESC, id DESC);

CREATE TABLE IF NOT EXISTS admin_sso_states (
    state_token TEXT PRIMARY KEY,
    login_kind TEXT NOT NULL DEFAULT 'wecom_qr',
    next_path TEXT NOT NULL DEFAULT '/admin',
    expires_at TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_sso_states_expires ON admin_sso_states (expires_at);
