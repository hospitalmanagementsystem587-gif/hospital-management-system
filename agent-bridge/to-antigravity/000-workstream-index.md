# Antigravity Workstream Index — Django HMS and Android Patient App

**Status:** READY  
**Created:** 2026-10-06  
**Purpose:** Complete, dependency-ordered backlog derived from the verified feature audit.

## Execution Rules

1. Complete tasks in dependency order. Do not start a task whose prerequisite is incomplete.
2. Inspect both repositories and run `git status` before every task. Preserve unrelated and uncommitted changes.
3. Django is the authority for identity, appointments, clinical records, invoices, payments, verification states, and operational status. Android Room is a cache, not a competing database.
4. Never introduce fake production states such as verified insurance, successful payment, ABHA active, checked-in, or doctor-approved medical advice.
5. Every endpoint must enforce authentication, object ownership/role permissions, data minimization, throttling where relevant, and tests for cross-patient access.
6. Use synthetic data in tests and documentation. Never commit credentials, tokens, real patient data, or authorization headers.
7. Each task requires a completion report under `agent-bridge/to-claude/` with changed files, migrations/dependencies, API changes, tests/build results, limitations, and commit/PR links.

## Task Order

| Task | Workstream | Priority | Depends on |
|---|---|---:|---|
| 002 | Secure API foundation and appointments | P0 | None |
| 003 | Production patient onboarding and identity | P0 | 002 |
| 004 | Doctor directory, hospital content, emergency and FAQ | P1 | 002 |
| 005 | Secure digital patient ID and QR check-in | P1 | 002, 003 |
| 006 | Patient health records, prescriptions and documents | P1 | 002, 003 |
| 007 | Patient billing, receipts and online-payment readiness | P1 | 002, 003 |
| 008 | Medication schedules, reminders and adherence | P1 | 006 |
| 009 | Verified feedback, ratings and satisfaction reporting | P2 | 002, 003 |
| 010 | Facility, aggregate bed availability and health packages | P2 | 002, 004 |
| 011 | OPD analytics, historical wait times and forecasting | P2 | 002 plus sufficient production-quality data |
| 012 | Insurance/TPA and ABHA readiness | P3 | 003, 006, 007, Task 014 baseline controls, plus policy approval |
| 013 | Governed health content and optional AI assistance | P3 | 004 plus clinical governance approval |
| 014 | Mobile security, offline sync, privacy and release hardening | P0 release gate | Applies throughout; final gate after connected features |

## Suggested Delivery Waves

- **Wave 1:** 002, then 003. Apply Task 014 requirements continuously.
- **Wave 2:** 004 and 006; 010 may begin after the content model in 004 is stable.
- **Wave 3:** 005, 007, 008, and 009.
- **Wave 4:** 011 after lifecycle data quality is verified.
- **Wave 5:** 012 and 013 only after the named owner, compliance, vendor, and clinical approvals exist.

Do not collapse all tasks into one unreviewable change. Use separate branches/PRs or clearly separated commits and completion reports per task.
