-- A compliant deployment returns one row with false, false, true and the trigger.
SELECT
    has_function_privilege('anon', 'public.rls_auto_enable()', 'EXECUTE')
        AS anon_can_execute,
    has_function_privilege('authenticated', 'public.rls_auto_enable()', 'EXECUTE')
        AS authenticated_can_execute,
    has_function_privilege('postgres', 'public.rls_auto_enable()', 'EXECUTE')
        AS owner_can_execute;

SELECT e.evtname, e.evtenabled, e.evtevent,
       e.evtfoid::regprocedure::text AS function_name
FROM pg_event_trigger e
WHERE e.evtfoid = 'public.rls_auto_enable()'::regprocedure;
