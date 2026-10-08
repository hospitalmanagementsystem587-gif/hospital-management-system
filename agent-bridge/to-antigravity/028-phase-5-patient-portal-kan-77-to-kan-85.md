# Antigravity Prompt Queue — Phase 5 Patient Portal (KAN-77–KAN-85)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-77 — Patient Web Authentication

Implement only patient browser authentication over existing Django User and
PatientAccount. Reuse KAN-36 session policy; test verification, archived/inactive
accounts, redirects, logout and API compatibility. No Supabase Auth.

## KAN-78 — Patient Dashboard

Build an owner-scoped dashboard with existing appointments, released clinical
data, prescriptions and billing summaries. Test two-patient isolation and empty states.

## KAN-79 — Appointment Booking

Implement patient-owned booking through existing appointment rules/services.
Test active doctors/visit types, department consistency, future times, conflicts,
duplicates, safe errors and ownership.

## KAN-80 — Doctor Directory

Expose only active/public doctors, departments, specialties and schedules allowed
by Jira. Preserve Android directory contracts and test public filtering.

## KAN-81 — Prescription History

Show only patient-owned, clinically released/non-revoked prescriptions. Test
cross-patient, draft, revoked and direct URL cases.

## KAN-82 — Documents and Reports

Expose only patient-owned released clean documents through private downloads.
Test scan states, revoked/unreleased files, enumeration resistance and headers.

## KAN-83 — Billing and Payment View

Show owner-scoped invoices, snapshots, payments and receipts without enabling an
unconfigured gateway. Test draft visibility, balances and cross-patient denial.

## KAN-84 — Insurance and ABHA

Expose the existing readiness data with minimum necessary disclosure. Preserve
verification/consent semantics; do not claim external ABHA integration without it.

## KAN-85 — Patient Feedback

Implement patient feedback using existing eligibility/moderation models. Test
ownership, duplicate/withdrawal rules, XSS handling and public moderation state.

