-- PostgreSQL connection diagnostics for aicrm_next connection pool incidents.
-- Copy into psql. This file is read-only diagnostics and does not kill sessions.

-- 1. Current connection state grouped by app/user/database/state.
SELECT
  COALESCE(application_name, '') AS application_name,
  usename,
  datname,
  state,
  COUNT(*) AS connection_count,
  MIN(backend_start) AS oldest_backend_start,
  MAX(now() - COALESCE(state_change, backend_start)) AS longest_state_age
FROM pg_stat_activity
GROUP BY application_name, usename, datname, state
ORDER BY connection_count DESC, application_name, usename, datname, state;

-- 2. idle in transaction sessions older than 60 seconds.
SELECT
  pid,
  usename,
  datname,
  COALESCE(application_name, '') AS application_name,
  client_addr,
  now() - xact_start AS transaction_age,
  now() - state_change AS state_age,
  wait_event_type,
  wait_event,
  left(query, 500) AS query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < now() - interval '60 seconds'
ORDER BY state_age DESC;

-- 3. Longest transactions.
SELECT
  pid,
  usename,
  datname,
  COALESCE(application_name, '') AS application_name,
  client_addr,
  state,
  now() - xact_start AS transaction_age,
  now() - query_start AS query_age,
  wait_event_type,
  wait_event,
  left(query, 500) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC
LIMIT 20;

-- 4. Current total connections and max_connections.
SELECT
  (SELECT COUNT(*) FROM pg_stat_activity) AS current_connections,
  current_setting('max_connections')::int AS max_connections,
  ROUND(
    (SELECT COUNT(*) FROM pg_stat_activity)::numeric
    / NULLIF(current_setting('max_connections')::numeric, 0)
    * 100,
    2
  ) AS connection_usage_percent;

-- 5. Connection sources by client/application/user/database.
SELECT
  client_addr,
  COALESCE(application_name, '') AS application_name,
  usename,
  datname,
  COUNT(*) AS connection_count,
  COUNT(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction_count,
  COUNT(*) FILTER (WHERE state = 'idle') AS idle_count,
  COUNT(*) FILTER (WHERE state = 'active') AS active_count
FROM pg_stat_activity
GROUP BY client_addr, application_name, usename, datname
ORDER BY connection_count DESC, client_addr, application_name;

-- 6. Idle sessions older than 5 minutes. Diagnostic only; do not kill from this file.
SELECT
  pid,
  usename,
  datname,
  COALESCE(application_name, '') AS application_name,
  client_addr,
  state,
  now() - state_change AS idle_age,
  wait_event_type,
  wait_event,
  left(query, 500) AS last_query
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < now() - interval '5 minutes'
ORDER BY idle_age DESC
LIMIT 50;
