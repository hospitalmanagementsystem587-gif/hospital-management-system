# End-to-end portal regression suite (KAN-105)

Run `scripts/run_portal_e2e.sh` from the repository environment. It composes the
existing integration suites instead of duplicating their fixtures or weakening
their domain assertions.

| Release boundary | Covered suite |
| --- | --- |
| Five portal hosts, login/session, role admission | portal architecture, shared auth, portal authorization |
| Patient/object isolation | portal authorization, object-level access matrix |
| Booking → consultation → prescription | patient booking, consultation, prescription workspaces |
| Pharmacy stock, dispensing, sale/invoice linkage | dispensing queue and pharmacy sales workspaces |
| Effective pricing and immutable invoice snapshots | price versions and invoice snapshot suites |
| Patient ticket → routing → agent visibility | patient ticketing, agent queue, ticket security |
| Android patient API compatibility | patient API suite |
| Database/security deployment controls | Supabase RLS boundary suite, migration drift, system check |

The test database is isolated and created by Django. PostgreSQL-only lock behavior
is exercised when the selected test database is PostgreSQL and explicitly skipped
on SQLite; the skip must be reported rather than hidden. Any failure blocks release
and becomes a Jira remediation issue if it cannot be fixed within the active ticket.
