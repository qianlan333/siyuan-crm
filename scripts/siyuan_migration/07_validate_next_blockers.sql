CREATE TEMP TABLE IF NOT EXISTS _siyuan_next_blocker_validation (
    check_name text,
    status text,
    count_value bigint
);

DELETE FROM _siyuan_next_blocker_validation;

DO $$
DECLARE
    table_name text;
    table_names text[] := ARRAY[
        'customer_list_index_next',
        'customer_detail_snapshot_next',
        'customer_timeline_event_next',
        'customer_recent_message_next',
        'user_ops_pool_current_next',
        'user_ops_do_not_disturb_next',
        'user_ops_send_records_next'
    ];
    row_count bigint;
BEGIN
    FOREACH table_name IN ARRAY table_names LOOP
        IF to_regclass('public.' || table_name) IS NULL THEN
            INSERT INTO _siyuan_next_blocker_validation VALUES (table_name, 'table_missing', NULL);
        ELSE
            EXECUTE format('SELECT count(*) FROM %I', table_name) INTO row_count;
            INSERT INTO _siyuan_next_blocker_validation VALUES (table_name, 'present', row_count);
        END IF;
    END LOOP;
END $$;

SELECT check_name, status, count_value
FROM _siyuan_next_blocker_validation
ORDER BY check_name;
