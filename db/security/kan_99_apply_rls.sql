-- KAN-99: Supabase/PostgreSQL RLS boundary for Django-owned HMS tables.
-- Run as the schema owner in a transaction after setting the exact runtime role:
--   SET hms.django_role = 'the_role_used_by_DJANGO_DATABASE_URL';
-- This deliberately does not use Supabase Auth/JWT claims.

BEGIN;

DO $kan99$
DECLARE
    target record;
    django_role text := current_setting('hms.django_role', true);
BEGIN
    IF django_role IS NULL OR btrim(django_role) = '' THEN
        RAISE EXCEPTION 'Set hms.django_role to the exact Django PostgreSQL runtime role';
    END IF;
    IF lower(django_role) IN ('anon', 'authenticated', 'public') THEN
        RAISE EXCEPTION 'hms.django_role must not be a Supabase browser/PostgREST role';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = django_role) THEN
        RAISE EXCEPTION 'Configured Django role % does not exist', django_role;
    END IF;

    FOR target IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename ~ '^(core_|auth_|django_|token_blacklist_)'
        ORDER BY tablename
    LOOP
        EXECUTE format('REVOKE ALL ON TABLE %I.%I FROM anon, authenticated', target.schemaname, target.tablename);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target.schemaname, target.tablename);
        EXECUTE format('DROP POLICY IF EXISTS hms_django_backend_all ON %I.%I', target.schemaname, target.tablename);
        EXECUTE format(
            'CREATE POLICY hms_django_backend_all ON %I.%I FOR ALL TO %I USING (true) WITH CHECK (true)',
            target.schemaname, target.tablename, django_role
        );
    END LOOP;
END
$kan99$;

COMMIT;
