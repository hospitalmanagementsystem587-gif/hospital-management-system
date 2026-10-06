# Task 005 — Secure Digital Patient ID and QR Check-In

**Priority:** P1  
**Depends on:** Tasks 002 and 003

## Goal

Implement a production-safe digital patient pass and reception QR check-in without exposing patient information or allowing forged/replayed check-ins.

## Scope

- Design a server-issued QR token containing only an opaque random identifier or compact signed reference. Do not encode name, phone, age, gender, blood group, MRN, clinical alerts, or insurance details.
- Tokens must be short-lived, revocable, purpose-bound, and protected against replay. Document expiry and clock-skew behavior.
- Add an authenticated patient endpoint to issue/refresh the digital pass and a staff-only reception endpoint to resolve and consume it.
- Reuse the existing Django appointment transition/check-in and audit logic. Do not create a parallel queue implementation.
- Define behavior for multiple same-day appointments, no appointment, expired token, already checked in, cancelled/no-show appointment, wrong hospital, and offline scanner.
- Implement the Android QR display, expiry countdown/refresh, privacy warning, screen-capture policy decision, and offline/error states.
- Implement the reception web scanner only after browser permission, device compatibility, manual fallback, and accessibility behavior are defined.

## Security Requirements

- Reception resolution must require the correct staff permission and return minimum patient data.
- Token lookup responses must not enable enumeration.
- Use TLS only outside local development; never log raw QR tokens.
- Check-in must be idempotent and transactionally safe under repeat scans.
- Remove `simulateReceptionScan` and the current PII QR payload from production code.

## Acceptance and Tests

- Valid pass checks in the correct owned appointment once.
- Expired, revoked, forged, replayed, cross-patient, and unauthorized scans fail safely.
- Concurrent duplicate scans cannot create multiple queue effects.
- Audit events identify the staff actor and appointment transition without storing raw tokens.
- Android never displays a false successful check-in before server confirmation.

Create `agent-bridge/to-claude/005-secure-qr-checkin-completion.md` when complete.
