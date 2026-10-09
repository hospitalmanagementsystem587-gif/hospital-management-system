# Supabase RLS boundary (KAN-99)

Django authentication, permissions and object querysets remain the HMS
authorization authority. The browser and Android app call Django; they do not
query HMS tables through Supabase PostgREST, and Supabase Auth is not used.

## Deployment

1. Take a database backup and record current grants, policies and Security
   Advisor output.
2. Confirm the exact PostgreSQL role used by Django's production
   `DATABASE_URL`. Do not guess it from a dashboard label.
3. In one owner session run `SET hms.django_role = '<exact-role>';` followed by
   `db/security/kan_99_apply_rls.sql`.
4. Run `db/security/kan_99_verify_rls.sql`. Its first query must return zero
   rows. Review every row of the policy inventory manually.
5. Run Django migrations, `manage.py check`, a login smoke test, patient API
   ownership tests and the complete suite using the same runtime role.
6. Re-run Supabase Security Advisor and attach its dated output to KAN-99.

The apply script covers Django-managed `core_`, `auth_`, `django_` and
`token_blacklist_` tables. It revokes table privileges from Supabase `anon` and
`authenticated`, enables RLS, and gives the explicitly configured Django role a
single backend policy. It does not inspect or change the `rls_auto_enable()`
function; that is KAN-100.

## Limitations and rollback

No live Supabase credentials or project metadata are stored in this repository,
so production policy inventory and Security Advisor results cannot be truthfully
verified from local tests. Existing non-HMS tables and pre-existing custom
policies require manual review. The rollback script disables RLS and removes the
named backend policy but intentionally does not restore browser grants.
