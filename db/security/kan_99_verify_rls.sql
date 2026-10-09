-- Returns a row for every problem. A compliant deployment returns zero rows.
WITH hms_tables AS (
    SELECT c.oid, n.nspname AS schema_name, c.relname AS table_name, c.relrowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname ~ '^(core_|auth_|django_|token_blacklist_)'
), policy_counts AS (
    SELECT ht.oid, count(p.polname) AS policy_count
    FROM hms_tables ht
    LEFT JOIN pg_policy p ON p.polrelid = ht.oid
    GROUP BY ht.oid
), browser_grants AS (
    SELECT table_schema, table_name, string_agg(DISTINCT grantee, ',') AS grantees
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated')
    GROUP BY table_schema, table_name
)
SELECT ht.schema_name, ht.table_name,
       CASE
           WHEN NOT ht.relrowsecurity THEN 'RLS_DISABLED'
           WHEN pc.policy_count = 0 THEN 'NO_USABLE_POLICY'
           WHEN bg.grantees IS NOT NULL THEN 'BROWSER_ROLE_HAS_TABLE_GRANT'
       END AS finding
FROM hms_tables ht
JOIN policy_counts pc ON pc.oid = ht.oid
LEFT JOIN browser_grants bg ON bg.table_schema = ht.schema_name AND bg.table_name = ht.table_name
WHERE NOT ht.relrowsecurity OR pc.policy_count = 0 OR bg.grantees IS NOT NULL
ORDER BY ht.table_name;

-- Manual review: any policy naming anon/authenticated/public must be justified.
SELECT schemaname, tablename, policyname, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename ~ '^(core_|auth_|django_|token_blacklist_)'
ORDER BY tablename, policyname;
