CREATE TEMP TABLE IF NOT EXISTS _siyuan_customer_projection_validation (
    metric text,
    result text,
    count_value bigint
);

DELETE FROM _siyuan_customer_projection_validation;

DO $$
DECLARE
    table_name text;
    count_value bigint;
    projected_count bigint;
    source_count bigint;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'customer_list_index_next',
        'customer_detail_snapshot_next',
        'customer_timeline_event_next',
        'customer_recent_message_next',
        'contacts',
        'external_contact_bindings',
        'people'
    ]
    LOOP
        IF to_regclass('public.' || table_name) IS NULL THEN
            INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
            VALUES (table_name || '.count', 'table_missing', NULL);
        ELSE
            EXECUTE format('SELECT count(*) FROM public.%I', table_name) INTO count_value;
            INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
            VALUES (table_name || '.count', 'ok', count_value);
        END IF;
    END LOOP;

    IF to_regclass('public.customer_detail_snapshot_next') IS NULL THEN
        INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
        VALUES ('projected_external_userid_count', 'table_missing', NULL);
    ELSE
        SELECT count(DISTINCT external_userid)
        INTO count_value
        FROM public.customer_detail_snapshot_next
        WHERE nullif(external_userid, '') IS NOT NULL;
        INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
        VALUES ('projected_external_userid_count', 'ok', count_value);
    END IF;

    IF to_regclass('public.customer_detail_snapshot_next') IS NULL OR to_regclass('public.contacts') IS NULL THEN
        INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
        VALUES ('projection_coverage_against_contacts', 'table_missing', NULL);
    ELSE
        SELECT count(DISTINCT external_userid)
        INTO source_count
        FROM public.contacts
        WHERE nullif(external_userid, '') IS NOT NULL;

        SELECT count(DISTINCT d.external_userid)
        INTO projected_count
        FROM public.customer_detail_snapshot_next d
        JOIN public.contacts c ON c.external_userid = d.external_userid
        WHERE nullif(d.external_userid, '') IS NOT NULL;

        INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
        VALUES (
            'projection_coverage_against_contacts',
            projected_count::text || '/' || source_count::text,
            projected_count
        );
    END IF;

    IF to_regclass('public.customer_detail_snapshot_next') IS NULL OR to_regclass('public.external_contact_bindings') IS NULL THEN
        INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
        VALUES ('projection_coverage_against_bindings', 'table_missing', NULL);
    ELSE
        SELECT count(DISTINCT external_userid)
        INTO source_count
        FROM public.external_contact_bindings
        WHERE nullif(external_userid, '') IS NOT NULL;

        SELECT count(DISTINCT d.external_userid)
        INTO projected_count
        FROM public.customer_detail_snapshot_next d
        JOIN public.external_contact_bindings b ON b.external_userid = d.external_userid
        WHERE nullif(d.external_userid, '') IS NOT NULL;

        INSERT INTO _siyuan_customer_projection_validation(metric, result, count_value)
        VALUES (
            'projection_coverage_against_bindings',
            projected_count::text || '/' || source_count::text,
            projected_count
        );
    END IF;
END $$;

SELECT metric, result, count_value
FROM _siyuan_customer_projection_validation
ORDER BY metric;
