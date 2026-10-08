# Antigravity Prompt Queue — Phase 9 Final Hardening (KAN-105–KAN-106)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-105 — End-to-End Portal Test Suite

Run only after every feature predecessor is integrated. Build deterministic E2E
coverage across admin, staff, store, patient and agent portals, including auth,
authorization, critical workflows, cross-user isolation and Android API smoke
compatibility. Use synthetic data and document browser/runtime requirements.

## KAN-106 — Production Security Review

Run only after KAN-105. Perform the Jira-defined production review across Django,
database/RLS, proxy/DNS/TLS/cookies/CSRF, secrets, storage, uploads, audit logs,
dependencies and deployment configuration. Remediate only in-ticket findings,
record residual risk owners, run all gates, and do not claim production readiness
without evidence.

