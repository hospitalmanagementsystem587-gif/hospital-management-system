# Task 015 — Complete and Validate Portal Architecture

**Status:** READY — execute end-to-end without pausing for routine decisions  
**Priority:** P0 security and completeness  
**Repository:** `hospital-management-system`  
**Depends on:** Existing portal implementation and completed Tasks 002–014

## Mission

Take ownership of the current staff, store, and patient portal implementation. Inspect the code first, then implement every in-scope item below, run the complete validation suite, correct any failures, and return only after the whole task is complete or a genuine external blocker makes further progress impossible.

Do not stop after analysis, partial implementation, or the first passing test. Do not ask for routine implementation choices. Make conservative, security-first decisions consistent with the existing Django architecture and document those decisions in the completion report. Preserve unrelated work and uncommitted changes.

The starting audit is recorded in `agent-bridge/015-portal-audit-follow-up-tasks.md`. Re-verify its findings against the current code rather than assuming every detail remains unchanged.

## Required Work

### 1. Protect released patient records and documents

- Show patient consultations only when `patient_released_at` is set and `patient_access_revoked_at` is null.
- List and download patient documents only when they belong to the authenticated patient, are validated clean, have been released, and have not been revoked.
- Direct requests for pending, rejected, unreleased, revoked, or another patient's documents must fail without disclosing metadata.
- Apply consistent release/revocation rules to any patient-facing prescriptions or related clinical data where the model relationship makes release state applicable.

### 2. Harden portal resolution middleware

- Make portal selection request-local and restore/clear URLconf state in a `finally` block, including when downstream code raises an exception.
- Do not trust `X-Portal-Subdomain` from arbitrary internet clients in production. Add an explicit setting and safe trust rule for proxy/header overrides; default it off outside controlled development/testing.
- Keep `?__portal=` strictly development-controlled and disabled by default in production.
- Define and test deterministic precedence among trusted proxy header, development query override, and hostname.
- Remove dead imports and avoid leaking portal state between sequential, concurrent, or asynchronous requests.

### 3. Resolve API portal-boundary behavior

- Do not leave all `/api/` requests silently exempt while exposing the API from every portal URLconf.
- Treat the existing API as host-neutral unless repository documentation clearly requires portal-specific APIs: expose it through the default URLconf and remove it from staff/store/patient URLconfs. Health and static behavior may remain appropriately exempt.
- Confirm existing API authentication, permissions, ownership checks, and API tests remain intact.
- Document this architecture decision.

### 4. Complete store operational worklists

- Add discoverable list/detail views and templates, reusing existing models and authorization helpers, for:
  - stock receipts / GRNs;
  - counter sales;
  - customer returns;
  - medicine batches and stock health;
  - quarantined batches.
- Link adjustment, quarantine/unquarantine, receipt, sale, return, and dispensing actions from appropriate worklists.
- Render recent sales and recent receipts on the store dashboard, or remove unused queries if a better worklist supersedes them.
- Preserve stock integrity, transaction safety, existing permissions, and audit behavior.

### 5. Align staff portal scope

- Add staff administration using the existing Django admin only if it is already configured safely; otherwise add the smallest application-specific staff administration entry consistent with current models and role helpers.
- Only administrators/superusers may access staff administration.
- Decide whether prescription dispensing should remain reachable from staff. Prefer store-only dispensing unless an existing documented clinical workflow requires otherwise; preserve read-only clinical review where useful.

### 6. Harden appointment booking

- Replace raw POST parsing and broad exception disclosure with an explicit Django form/service and user-safe validation errors.
- Validate active visit type, public/active doctor, selected department, and doctor/department consistency.
- Preserve the patient's stated booking reason in an appropriate model field. If the current `Appointment` model has no suitable field, add a backward-compatible migration.
- Preserve conflict detection and make duplicate/race behavior safe to the practical extent supported by the current database and service design.
- Do not expose internal exception strings to patients.

### 7. Finish reasonable patient self-service gaps

- Add patient invoice detail and downloadable receipt/document behavior by reusing existing secure document/receipt services where available.
- Add appointment cancellation/rescheduling only for statuses and time windows that can be enforced safely with existing domain rules. Do not allow patients to mutate completed, checked-in, cancelled, or clinically locked appointments.
- Keep identity/profile fields read-only unless a verified update workflow already exists; clearly label read-only data rather than inventing an insecure edit flow.

### 8. Correct portal-aware UI details

- Make authenticated brand links, top-bar titles, portal labels, and account-role labels correct for staff, store, and patient contexts.
- Add navigation links for every new discoverable worklist/action.
- Preserve responsive and accessible markup conventions used by the existing templates.

### 9. Production configuration and documentation

- Document required production values for portal hosts, trusted origins, trusted proxy/header behavior, and local-development URLs.
- Add practical Django system checks or settings validation where missing production configuration would otherwise fail insecurely or ambiguously.
- Do not hard-code a real deployment domain.

## Mandatory Test Coverage

Expand `core/test_portals.py` or split it into focused portal test modules. Tests must include at least:

- hostname, port-bearing hostname, trusted/untrusted header, invalid header, development query override, production-disabled override, URLconf cleanup, and request isolation;
- anonymous and authenticated access for Doctor, Reception, Pharmacy, Administrator, pure patient, dual-role account, unverified patient, archived patient, and ordinary user without a role;
- two distinct patients with negative assertions proving appointments, consultations, prescriptions, invoices, payments, receipts, and documents never cross accounts;
- consultation/document unreleased, released, revoked, pending, clean, rejected, wrong-owner, and direct-download states;
- every staff, store, and patient portal route, including new list/detail/action routes;
- booking success and invalid doctor, visit type, department mismatch, past/malformed date, conflict, duplicate submission, and safe error handling;
- patient reschedule/cancel allowed and forbidden transitions if implemented;
- API availability only on the intended URLconf/host and preservation of API permission behavior;
- portal-aware template navigation and labels.

Use synthetic test data only.

## Validation Loop

Run all of the following, fix failures, and rerun until clean:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test core.test_portals -v 2
.venv/bin/python manage.py test -v 1
```

Also run any existing formatting, lint, or browser smoke tests that apply to files changed by this task. If Playwright cannot run because a browser/runtime is unavailable, record the exact command and blocker, but do not treat that as permission to skip all other validation.

Manually inspect representative rendered pages for all three portals and check that links resolve within the correct portal URLconf.

## Definition of Done

This task is done only when:

- all nine required-work sections are implemented or an item is explicitly demonstrated to be already correct;
- security and cross-patient isolation tests cover the stated cases;
- the full Django suite passes;
- there is no model migration drift;
- documentation reflects the final portal/API/proxy design;
- no unrelated changes were overwritten;
- a completion report exists at `agent-bridge/to-claude/015-portal-architecture-completion.md`.

## Completion Response

After completing and validating the entire task, write `agent-bridge/to-claude/015-portal-architecture-completion.md` containing:

- concise outcome and architecture decisions;
- every changed file;
- migrations and compatibility notes;
- security controls and negative tests added;
- exact commands and pass/fail counts;
- manual UI validation performed;
- any remaining limitation that genuinely requires a product, infrastructure, or policy owner;
- commit/branch/PR identifiers if created.

Then update `agent-bridge/STATUS.md` with one `READY-FOR-REVIEW` line and respond with a concise summary pointing to the completion report. Do not report completion based only on implementation; report it only after the validation loop is clean.

## Genuine Blocker Rule

Continue autonomously through normal ambiguity, test failures, migrations, refactoring, and implementation decisions. Pause only when completion requires unavailable credentials, an inaccessible external system, destructive handling of unrelated user changes, or a product/legal decision that cannot be safely represented by a conservative default. Before declaring a blocker, complete every independent portion, record exact evidence and attempted alternatives, and state the single decision or resource needed.
