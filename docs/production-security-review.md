# Production security review (KAN-106)

Review date: 2026-10-10. Scope: the completed Django multi-portal HMS, Android
patient API, PostgreSQL/Supabase boundary, and release configuration.

## Result

No open critical or high code-level security finding was identified. The full
suite passed 611 tests with one documented SQLite-only skip for a PostgreSQL
concurrency assertion. The focused end-to-end gate passed 132 tests with the same
skip. `manage.py check`, migration drift, and `manage.py check --deploy` with the
documented production HTTPS/HSTS settings all passed.

Supabase production verification found 61/61 HMS tables RLS-enabled with 61
Django backend policies, zero `anon`/`authenticated` table grants, and no API-role
execution of `public.rls_auto_enable()`. A fresh Security Advisor run showed zero
errors, warnings, or suggestions.

## Findings

| Severity | Component/evidence | Remediation/status | Jira follow-up |
| --- | --- | --- | --- |
| Resolved high | Supabase API roles previously had HMS table grants and tables lacked policies | KAN-99 transaction applied and independently verified | None |
| Resolved high | API roles could execute the `SECURITY DEFINER` RLS event-trigger function | KAN-100 revoked `PUBLIC`, `anon`, and `authenticated`; owner/trigger retained | None |
| Resolved medium | General audit records allowed model-level mutation | KAN-101 makes audit records append-only and tests update/delete rejection | None |
| Operational gate | Live environment must supply unique strong secrets, exact hosts/origins, HTTPS redirect and HSTS | Required by rollout checklist; deployment check is clean with production values | Create incident/remediation ticket if validation fails |
| Operational gate | Backup restore, monitoring/alert routing, malware scanner, private media access, and audit retention need owner evidence | Must be validated by authorized operators before traffic cutover | Create remediation ticket for any failed item |

Operational gates are not permission to declare production ready without the
listed evidence. Secrets and patient data were not copied into this review.

## Boundary review

- Django sessions/JWT and Django permissions remain authoritative; Supabase Auth
  is not used.
- Admin, staff, store, patient, and agent host admission and object-level isolation
  are covered by positive and adversarial tests.
- Patient records, clinical documents, prescriptions, pharmacy inventory,
  financial objects, and ticket visibility are server-side scoped.
- Pharmacy dispensing and sales preserve batch/stock and shared invoice behavior.
- Pricing effective dates and immutable invoice price snapshots pass regression.
- `AuditEvent` and `TicketAuditEvent` are append-only through application APIs and
  avoid secrets/document contents in structured context.
- Android API authentication and compatibility smoke/regression tests pass.

## Production rollout checklist

1. Pin the reviewed commit and deploy to staging from `main`; do not deploy an
   unreviewed worktree branch.
2. Set a unique random `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, exact
   `DJANGO_ALLOWED_HOSTS`, portal hosts, cookie domains, and trusted HTTPS origins.
3. Enable proxy HTTPS forwarding, `DJANGO_SECURE_SSL_REDIRECT=true`, HSTS only
   after HTTPS validation, secure session/CSRF cookies, and certificate monitoring.
4. Run `manage.py check --deploy`, migrations, migration-drift check, the E2E
   script, and Android API smoke tests against staging.
5. Apply/verify the versioned KAN-99/KAN-100 SQL on each target database and require
   a clean Security Advisor result.
6. Verify private document/media authorization, malware scanning, error reporting,
   redaction, rate limiting/proxy controls, and alert destinations.
7. Perform and record an encrypted backup restore drill; approve retention,
   recovery objectives, audit retention, and incident contacts.
8. Use synthetic data for final portal smoke tests, then obtain security/product/
   clinical/finance sign-off before traffic cutover.
9. Monitor authentication failures, authorization denials, database errors, audit
   creation, ticket SLA processing, stock movements, and payment reconciliation.
10. Roll back application release on regression; use reviewed SQL rollback only
    with security-owner approval because it can reopen database access.

Any failed checklist item or newly discovered critical/high finding blocks release
and must receive a new Jira remediation ticket before production rollout.
