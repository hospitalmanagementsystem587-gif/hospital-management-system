-- KAN-100: keep the DDL event trigger operational while removing API execution.
-- Reviewed production state: owner postgres; trigger ensure_rls at ddl_command_end.
BEGIN;

REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM anon;
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM authenticated;
GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO postgres;

COMMIT;
