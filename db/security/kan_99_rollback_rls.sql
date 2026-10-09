-- Emergency rollback only. This does not restore browser grants because HMS
-- tables must not be exposed directly to anon/authenticated. Review before use.
BEGIN;
DO $kan99$
DECLARE target record;
BEGIN
    FOR target IN
        SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename ~ '^(core_|auth_|django_|token_blacklist_)'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS hms_django_backend_all ON %I.%I', target.schemaname, target.tablename);
        EXECUTE format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY', target.schemaname, target.tablename);
    END LOOP;
END
$kan99$;
COMMIT;
