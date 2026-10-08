# Antigravity Prompt Queue — Phase 7 Security (KAN-97–KAN-101)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-97 — Portal Permission Matrix

Inventory every portal route/action and formalize the authoritative role matrix.
Close enforcement gaps without changing business scope. Test all roles and dual roles.

## KAN-98 — Object-Level Access Tests

Create exhaustive negative ownership tests across patient, clinical, documents,
billing, pharmacy and tickets. Fix only access defects proven within Jira scope.

## KAN-99 — Supabase RLS Policy Remediation

Inspect actual production/staging schema and policies before changes. Align RLS
with Django ownership while preserving the Django service path. Apply reviewed,
reversible SQL/migrations and prove no direct cross-tenant/patient leakage.

## KAN-100 — `rls_auto_enable()` Function Remediation

Audit the exact database function, triggers, privileges and search path. Remediate
securely with idempotent SQL and rollback notes. Never disable RLS broadly.

## KAN-101 — Audit Logging Coverage

Map sensitive state changes and add complete, non-secret, actor-attributed audit
events with retention/access rules. Test coverage and failure behavior without
logging credentials, tokens or excessive clinical content.

