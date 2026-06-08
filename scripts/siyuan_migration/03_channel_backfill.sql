-- Backfill legacy siyuan automation_channel rows into AI-CRM Next channel-entry lookup tables.
-- Safe to run multiple times. It only inserts missing active scene aliases/assets.

DO $$
DECLARE
  has_channel boolean := to_regclass('public.automation_channel') IS NOT NULL;
  has_alias boolean := to_regclass('public.automation_channel_scene_alias') IS NOT NULL;
  has_asset boolean := to_regclass('public.automation_channel_qrcode_asset') IS NOT NULL;
  source_has_corp boolean;
  source_has_config boolean;
  source_has_qr_ticket boolean;
  source_has_qr_url boolean;
  source_has_owner boolean;
  alias_has_status boolean;
  alias_has_corp boolean;
  asset_has_status boolean;
  asset_has_corp boolean;
  corp_expr text;
  config_expr text;
  qr_url_expr text;
  owner_expr text;
  cols text;
  vals text;
  active_alias_pred text;
  active_asset_pred text;
  inserted_count bigint;
BEGIN
  IF NOT has_channel THEN
    RAISE NOTICE 'automation_channel missing; skip channel backfill';
    RETURN;
  END IF;

  source_has_corp := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel' AND column_name='corp_id');
  source_has_config := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel' AND column_name='config_id');
  source_has_qr_ticket := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel' AND column_name='qr_ticket');
  source_has_qr_url := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel' AND column_name='qr_url');
  source_has_owner := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel' AND column_name='owner_staff_id');

  corp_expr := CASE WHEN source_has_corp THEN 'COALESCE(NULLIF(ac.corp_id, ''''), '''')' ELSE '''''' END;
  IF source_has_config THEN
    config_expr := 'COALESCE(NULLIF(ac.config_id, ''''), ' || CASE WHEN source_has_qr_ticket THEN 'NULLIF(ac.qr_ticket, '''')' ELSE 'NULL' END || ', '''')';
  ELSIF source_has_qr_ticket THEN
    config_expr := 'COALESCE(NULLIF(ac.qr_ticket, ''''), '''')';
  ELSE
    config_expr := '''''';
  END IF;
  qr_url_expr := CASE WHEN source_has_qr_url THEN 'COALESCE(ac.qr_url, '''')' ELSE '''''' END;
  owner_expr := CASE WHEN source_has_owner THEN 'COALESCE(ac.owner_staff_id, '''')' ELSE '''''' END;

  IF has_alias THEN
    alias_has_status := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='status');
    alias_has_corp := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='corp_id');
    cols := 'channel_id, scene_value';
    vals := 'ac.id, ac.scene_value';
    IF alias_has_corp THEN cols := cols || ', corp_id'; vals := vals || ', ' || corp_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='config_id') THEN cols := cols || ', config_id'; vals := vals || ', ' || config_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='qr_url') THEN cols := cols || ', qr_url'; vals := vals || ', ' || qr_url_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='carrier_type') THEN cols := cols || ', carrier_type'; vals := vals || ', ''qrcode'''; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='provider_name') THEN cols := cols || ', provider_name'; vals := vals || ', ''wecom_contact_way'''; END IF;
    IF alias_has_status THEN cols := cols || ', status'; vals := vals || ', ''active'''; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='source') THEN cols := cols || ', source'; vals := vals || ', ''legacy_import_confirmed'''; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='first_seen_at') THEN cols := cols || ', first_seen_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='last_seen_at') THEN cols := cols || ', last_seen_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='created_at') THEN cols := cols || ', created_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_scene_alias' AND column_name='updated_at') THEN cols := cols || ', updated_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    active_alias_pred := CASE WHEN alias_has_status THEN ' AND existing.status = ''active''' ELSE '' END;
    EXECUTE format(
      'INSERT INTO automation_channel_scene_alias (%s)
       SELECT %s
       FROM automation_channel ac
       WHERE NULLIF(ac.scene_value, '''') IS NOT NULL
         AND NOT EXISTS (
           SELECT 1 FROM automation_channel_scene_alias existing
           WHERE existing.scene_value = ac.scene_value %s %s
         )
       ON CONFLICT DO NOTHING',
      cols,
      vals,
      CASE WHEN alias_has_corp THEN 'AND existing.corp_id = ' || corp_expr ELSE '' END,
      active_alias_pred
    );
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RAISE NOTICE 'automation_channel_scene_alias rows inserted: %', inserted_count;
  ELSE
    RAISE NOTICE 'automation_channel_scene_alias missing; run schema init first';
  END IF;

  IF has_asset THEN
    asset_has_status := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='status');
    asset_has_corp := EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='corp_id');
    cols := 'channel_id, scene_value';
    vals := 'ac.id, ac.scene_value';
    IF asset_has_corp THEN cols := cols || ', corp_id'; vals := vals || ', ' || corp_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='config_id') THEN cols := cols || ', config_id'; vals := vals || ', ' || config_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='qr_url') THEN cols := cols || ', qr_url'; vals := vals || ', ' || qr_url_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='provider_name') THEN cols := cols || ', provider_name'; vals := vals || ', ''wecom_contact_way'''; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='provider_payload_json') THEN cols := cols || ', provider_payload_json'; vals := vals || ', ''{}''::jsonb'; END IF;
    IF asset_has_status THEN cols := cols || ', status'; vals := vals || ', ''active'''; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='generation_source') THEN cols := cols || ', generation_source'; vals := vals || ', ''legacy_import_confirmed'''; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='created_by') THEN cols := cols || ', created_by'; vals := vals || ', ' || owner_expr; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='generated_at') THEN cols := cols || ', generated_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='created_at') THEN cols := cols || ', created_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='automation_channel_qrcode_asset' AND column_name='updated_at') THEN cols := cols || ', updated_at'; vals := vals || ', CURRENT_TIMESTAMP'; END IF;
    active_asset_pred := CASE WHEN asset_has_status THEN ' AND existing.status = ''active''' ELSE '' END;
    EXECUTE format(
      'INSERT INTO automation_channel_qrcode_asset (%s)
       SELECT %s
       FROM automation_channel ac
       WHERE NULLIF(ac.scene_value, '''') IS NOT NULL
         AND NOT EXISTS (
           SELECT 1 FROM automation_channel_qrcode_asset existing
           WHERE existing.scene_value = ac.scene_value %s %s
         )
       ON CONFLICT DO NOTHING',
      cols,
      vals,
      CASE WHEN asset_has_corp THEN 'AND existing.corp_id = ' || corp_expr ELSE '' END,
      active_asset_pred
    );
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RAISE NOTICE 'automation_channel_qrcode_asset rows inserted: %', inserted_count;
  ELSE
    RAISE NOTICE 'automation_channel_qrcode_asset missing; run schema init first';
  END IF;
END $$;
