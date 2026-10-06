# Task 002 — Secure Mobile API Foundation and Appointment Vertical Slice

**Owner:** Antigravity  
**Status:** READY  
**Priority:** P0  
**Depends on:** None  
**Created:** 2026-10-06  
**Repositories:**

- Django HMS: `hospital-management-system`
- Android patient app: `https://github.com/abhishek-sahu-ai/hospital-vedant.git`
- Android revision reviewed for this task: `76dd8a5d8c8c52c9324b83e65dd28cb263e6e0c8`

## Goal

Create the first real, secure end-to-end connection between the Android patient app and the Django HMS. Implement a patient-authenticated appointment vertical slice in which Django is the only source of truth for patient identity, doctors, appointment availability, booking, cancellation, status, queue/token information, and OPD slips.

This task intentionally replaces the Android app's locally generated sample data and random appointment/token behavior for this slice. Room may remain as an offline cache, but it must not be authoritative.

## Read Before Starting

1. Read `agent-bridge/001-mobile-app-feature-audit-and-integration-plan.md` as background only.
2. Read `docs/requirements.md`, `docs/workflows.md`, `docs/security.md`, `docs/roles-and-permissions.md`, and `docs/decisions.md` before changing the Django application.
3. Inspect both repositories at their current revisions. Do not assume the earlier audit is fully accurate.
4. Run `git status` in both repositories and preserve all existing user/agent changes. Do not reset, overwrite, or reformat unrelated files.

## Verified Current-State Facts

- The Django HMS already has authoritative `Patient`, `StaffProfile`, `Department`, `VisitType`, `Appointment`, consultation, prescription, invoice, payment, and audit models.
- Django already enforces active doctor slot conflicts and appointment lifecycle permissions.
- The HMS currently has no `/api/v1/` application API and no patient portal authentication.
- The Android app stores patients, doctors, and appointments locally. Its `HospitalRepository` does not call Django.
- Retrofit is declared in Android dependencies but no Retrofit service is implemented.
- Android currently generates random UHIDs, appointment tokens, and queue positions. These must not be used once the API slice is connected.
- Do not copy the current Android QR payload; it contains excessive patient information and a predictable token.

## Scope

### A. Django API foundation

Implement a versioned `/api/v1/` API using an appropriate maintained Django API library. Add and pin required dependencies.

Provide a secure patient-account linkage model. A patient user must be linked to exactly one `Patient` record, and staff roles must not accidentally gain patient-portal access through this linkage. Do not implement a fake OTP flow. If real phone/email verification is not available, provide a documented development/test provisioning path and clearly mark production verification as pending.

Use short-lived access credentials with a safe refresh/revocation design suitable for an Android client. Never place tokens in URLs or logs.

Required endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/token/` | Authenticate a provisioned patient account |
| `POST` | `/api/v1/auth/token/refresh/` | Refresh an authenticated session |
| `GET` | `/api/v1/me/` | Return the minimum patient profile and server-issued MRN |
| `GET` | `/api/v1/doctors/` | Return active Doctor-group staff with department information |
| `GET` | `/api/v1/visit-types/` | Return active visit types |
| `GET` | `/api/v1/appointments/` | Return only the authenticated patient's appointments |
| `POST` | `/api/v1/appointments/` | Book an appointment for the authenticated patient |
| `GET` | `/api/v1/appointments/<id>/` | Return an owned appointment and OPD-slip fields |
| `POST` | `/api/v1/appointments/<id>/cancel/` | Cancel an owned appointment only when the existing lifecycle permits it |

API rules:

- Never accept `patient_id`, MRN/UHID, patient name, queue number, status, or token number from the mobile booking request. Derive all of them server-side.
- Reuse the existing slot-conflict and appointment lifecycle rules; do not create a second inconsistent implementation.
- Use ISO-8601 timestamps with timezone offsets and stable machine-readable status values.
- Return a consistent JSON error structure for validation, authentication, authorization, conflicts, and not-found responses.
- Return only fields needed by the patient app. Do not expose clinical notes, staff account fields, internal permissions, audit events, or other patients.
- Preserve server-side auditability for booking and cancellation.
- Add rate limiting/throttling appropriate for authentication and appointment writes.

### B. Android integration

Replace the local-only doctor and appointment flow with a real Retrofit-backed data source.

Required work:

1. Add API DTOs, Retrofit interfaces, authentication interceptor/authenticator, and a repository boundary between network, Room cache, and UI models.
2. Make the API base URL environment-specific through BuildConfig or another safe configuration mechanism. Do not commit credentials or production secrets.
3. Add a minimal patient login/session flow appropriate for the backend implementation.
4. Load the patient profile, doctors, visit types, appointment list, appointment detail, and OPD slip from Django.
5. Book and cancel appointments through Django, displaying server validation and slot-conflict errors clearly.
6. Cache successful reads in Room for offline viewing. Offline mode must be read-only for appointment mutations unless a deliberate, idempotent queued-write design is implemented and tested.
7. Remove or disable random UHID, token, queue-position, and appointment generation from the production path. Synthetic seeding may remain only in an explicit demo/test build variant.
8. Do not send the current free-text `symptoms` field until its data-access and clinical classification are explicitly approved.
9. Redact authorization headers and patient information from network logs, especially in release builds.
10. Schedule appointment reminders from server-issued appointment timestamps, update/cancel them after reschedule or cancellation, and never present an immediate notification as a future scheduled reminder.

### C. Tests and verification

Django tests must cover at least:

- Unauthenticated requests are rejected.
- A patient can read only their own profile and appointments.
- Guessing another appointment ID does not reveal whether it exists.
- Staff accounts cannot use patient endpoints merely because they are authenticated.
- Patient identity, status, token/queue data, and MRN cannot be overridden by request payloads.
- Valid booking succeeds and uses the authenticated patient.
- Exact and overlapping doctor-slot conflicts are rejected, including a concurrency-oriented test.
- Cancellation follows the existing state transition rules and is idempotent or returns a defined conflict.
- Inactive doctors and visit types cannot be booked.
- Authentication and write endpoints are throttled.

Android tests must cover at least:

- DTO/domain mapping.
- Token attachment and refresh behavior without logging secrets.
- Repository success, validation-error, unauthorized, conflict, and offline-cache paths.
- ViewModel behavior for booking, cancellation, loading, empty state, and retry.

Verification commands and results must be recorded in the completion report. At minimum run Django system checks and the relevant Django test suite. Restore or add a working Gradle wrapper if required, then run Android unit tests and a debug build.

## Explicitly Out of Scope

Do not implement these in Task 002:

- QR check-in or QR scanning
- Insurance/TPA or ABHA integration
- Online payment processing
- Medication schedules or adherence sync
- Feedback/ratings
- OPD crowd forecasting
- AI-generated health advice
- Patient editing or deletion of clinical records
- Large visual redesigns unrelated to the connected appointment flow

Do not add placeholder "verified," "paid," "ABHA active," or "checked in" states that are not backed by a server-side workflow.

## Definition of Done

- Django is the sole authority for the connected patient's identity and appointments.
- The Android app can authenticate, list doctors/visit types, book an appointment, show its server status/OPD slip, list appointment history, and cancel when permitted.
- Cross-patient access and payload tampering are covered by tests.
- The existing staff web portal continues to pass its tests and workflows.
- No secrets, patient data, or authorization headers are introduced into source control or logs.
- API documentation includes request/response examples, status/error definitions, local setup, and Android base-URL configuration.
- Unrelated working-tree changes in either repository remain intact.

## Completion Handoff

When complete:

1. Create `agent-bridge/to-claude/002-secure-mobile-api-and-appointments-completion.md` containing:
   - summary of changes in each repository;
   - migrations and new dependencies;
   - endpoint contract and authentication choice;
   - tests/build commands and results;
   - known limitations and production follow-ups;
   - commit hashes or pull-request links for both repositories.
2. Update `agent-bridge/STATUS.md` to `READY-FOR-REVIEW` and reference the completion report.
3. Do not mark the task complete if either repository is untested or if Android is still using random/local appointment data in the production path.
