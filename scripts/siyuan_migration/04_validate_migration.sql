CREATE TEMP TABLE IF NOT EXISTS siyuan_migration_validation (
  metric text PRIMARY KEY,
  value text NOT NULL
);

TRUNCATE siyuan_migration_validation;

DO $$
DECLARE
  tbl_name text;
  table_count bigint;
  scene_count bigint := 0;
  covered_count bigint := 0;
  ratio text;
  alias_status_pred text := '';
  asset_status_pred text := '';
  tables text[] := ARRAY[
    'automation_channel',
    'automation_channel_scene_alias',
    'automation_channel_qrcode_asset',
    'automation_channel_contact',
    'automation_channel_entry_effect_log',
    'wecom_external_contact_event_logs',
    'contacts',
    'external_contact_bindings',
    'people',
    'admin_users',
    'admin_user_roles',
    'user_ops_pool_current',
    'user_ops_do_not_disturb',
    'user_ops_send_records'
  ];
BEGIN
  FOREACH tbl_name IN ARRAY tables LOOP
    IF to_regclass('public.' || tbl_name) IS NULL THEN
      INSERT INTO siyuan_migration_validation(metric, value) VALUES (tbl_name, 'table_missing')
      ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
    ELSE
      EXECUTE format('SELECT count(*) FROM %I', tbl_name) INTO table_count;
      INSERT INTO siyuan_migration_validation(metric, value) VALUES (tbl_name, table_count::text)
      ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
    END IF;
  END LOOP;

  IF to_regclass('public.automation_channel') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM automation_channel WHERE NULLIF(scene_value, '''') IS NOT NULL' INTO scene_count;
    INSERT INTO siyuan_migration_validation(metric, value) VALUES ('automation_channel.scene_value_non_empty', scene_count::text)
    ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
  END IF;

  IF to_regclass('public.automation_channel') IS NOT NULL AND to_regclass('public.automation_channel_scene_alias') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'automation_channel_scene_alias' AND column_name = 'status'
    ) THEN
      alias_status_pred := ' AND alias.status = ''active''';
    END IF;
    EXECUTE format('
      SELECT count(DISTINCT ac.id)
      FROM automation_channel ac
      WHERE NULLIF(ac.scene_value, '''') IS NOT NULL
        AND EXISTS (
          SELECT 1 FROM automation_channel_scene_alias alias
          WHERE alias.scene_value = ac.scene_value%s
        )', alias_status_pred) INTO covered_count;
    ratio := CASE WHEN scene_count = 0 THEN 'n/a' ELSE covered_count::text || '/' || scene_count::text END;
    INSERT INTO siyuan_migration_validation(metric, value) VALUES ('scene_alias_coverage', ratio)
    ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
  END IF;

  IF to_regclass('public.automation_channel') IS NOT NULL AND to_regclass('public.automation_channel_qrcode_asset') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'automation_channel_qrcode_asset' AND column_name = 'status'
    ) THEN
      asset_status_pred := ' AND asset.status = ''active''';
    END IF;
    EXECUTE format('
      SELECT count(DISTINCT ac.id)
      FROM automation_channel ac
      WHERE NULLIF(ac.scene_value, '''') IS NOT NULL
        AND EXISTS (
          SELECT 1 FROM automation_channel_qrcode_asset asset
          WHERE asset.scene_value = ac.scene_value%s
        )', asset_status_pred) INTO covered_count;
    ratio := CASE WHEN scene_count = 0 THEN 'n/a' ELSE covered_count::text || '/' || scene_count::text END;
    INSERT INTO siyuan_migration_validation(metric, value) VALUES ('qrcode_asset_coverage', ratio)
    ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
  END IF;

  IF to_regclass('public.contacts') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM contacts' INTO table_count;
    INSERT INTO siyuan_migration_validation(metric, value) VALUES ('contacts.total', table_count::text)
    ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
  END IF;

  IF to_regclass('public.external_contact_bindings') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM external_contact_bindings' INTO table_count;
    INSERT INTO siyuan_migration_validation(metric, value) VALUES ('external_contact_bindings.total', table_count::text)
    ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
  END IF;

  IF to_regclass('public.admin_users') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM admin_users' INTO table_count;
    INSERT INTO siyuan_migration_validation(metric, value) VALUES ('admin_users.total', table_count::text)
    ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value;
  END IF;
END $$;

SELECT metric, value
FROM siyuan_migration_validation
ORDER BY metric;
