# Task 005 Completion — Secure Digital Patient Pass and QR Check-In

- Authenticated patients can issue a five-minute opaque pass for one owned, scheduled appointment.
- Refreshing revokes prior active passes. Tokens contain no patient or clinical data and only their SHA-256 digest is stored.
- Reception consumption requires an active Reception group member with a staff profile.
- Consumption locks both pass and appointment, performs the existing scheduled-to-checked-in transition, and creates a staff-attributed audit event without storing the raw token.
- Forged, expired, revoked, cross-patient and unauthorized requests fail safely; repeat consumption returns conflict and creates no second queue effect.
- Android removed the PII QR payload and simulated success path. It displays only a server-issued opaque QR, expiry countdown, refresh/revocation control, privacy warning, and honest offline/error state.
- Global screenshot protection and HTTPS-only release networking are supplied by Task 014.

Verification: three backend security/ownership/replay tests pass; Android unit suite passes. Migration is `0021_digitalcheckinpass`, depending on `0020_insurance_abha_readiness`.
