# Task 014 — Mobile Security, Offline Sync, Privacy and Release Hardening

**Priority:** P0 release gate  
**Depends on:** Apply throughout all connected work; complete final verification after feature tasks

## Goal

Make the Android patient app safe to distribute with authenticated hospital data and establish repeatable build, test, privacy, and release controls.

## Scope

- Restore/commit a working Gradle wrapper and create repeatable debug/release build instructions and CI checks.
- Store access/refresh credentials using approved Android secure storage; implement rotation, expiry, logout, revoke-all, and device replacement behavior.
- Minimize Room data, document retention, clear account-scoped data on logout/unlink, and use encryption where sensitive offline data remains.
- Disable or explicitly exclude clinical, identity, insurance, billing, and token data from Android backup/device transfer. Review `allowBackup`, backup rules, screenshots, clipboard, notifications, and recent-app previews.
- Make network logging debug-only with authorization/PII redaction. Enforce HTTPS outside local development and define safe certificate/network-security configuration.
- Establish deterministic offline/read-only behavior, cache freshness, conflict handling, idempotency keys for writes, retry/backoff, and account separation.
- Add dependency/version scanning, static analysis, secret scanning, ProGuard/R8 release configuration, signed-build handling, and least-privilege permissions.
- Add privacy-safe crash/analytics telemetry only after consent/configuration review; never capture clinical payloads or tokens.
- Review accessibility, localization/timezones, notification permissions, deep links, rooted/debug device posture decisions, and app update compatibility.
- Remove synthetic patients, doctors, invoices, reviews, insurance policies, and clinical records from release builds.

## Acceptance and Tests

- A clean clone can run unit tests and produce a debug build with documented commands.
- Release artefacts contain no API/provider secrets, sample patient data, verbose HTTP logging, or debuggable configuration.
- Logout/account switch removes cached data and notifications belonging to the prior account.
- Backup/restore and device-transfer tests do not restore protected data unexpectedly.
- Token expiry/refresh/revocation, offline transitions, duplicate writes, process death, reboot, timezone change, and app upgrade are tested.
- A security checklist and threat model cover account takeover, IDOR, token theft, lost device, QR replay, notification leakage, local database extraction, API abuse, and supply-chain risk.

Create `agent-bridge/to-claude/014-mobile-security-release-completion.md` when complete. This task is a release gate: do not call the connected mobile app production-ready until it passes.
