# Supabase security remediation evidence (KAN-99/KAN-100)

Production project `crodzhehsiwlpnzlphcb` was reviewed on 2026-10-10.

Before remediation, Supabase Security Advisor reported 61 `RLS Enabled No Policy`
suggestions and two warnings for public/signed-in execution of the
`SECURITY DEFINER` function `public.rls_auto_enable()`.

The approved transaction:

- revoked all HMS table privileges from `anon` and `authenticated`;
- retained RLS on all 61 `core_`, `auth_`, `django_`, and `token_blacklist_` tables;
- installed `hms_django_backend_all` for the PostgreSQL/Django `postgres` role;
- revoked function execution from `PUBLIC`, `anon`, and `authenticated`;
- retained execution for owner `postgres` so event trigger `ensure_rls` continues
  enabling RLS on newly created public tables.

Post-change SQL verification returned: 61 tables, 61 RLS-enabled tables, 61
Django policies, zero browser-role table grants, `anon=false`,
`authenticated=false`, and `postgres=true` for function execution. A fresh
Security Advisor run returned 0 errors, 0 warnings, and 0 suggestions.
