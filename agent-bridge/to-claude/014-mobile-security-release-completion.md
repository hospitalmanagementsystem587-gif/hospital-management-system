# Task 014 — Mobile Security Release Gate

The integrated release branch applies secure token storage, refresh/revocation behavior, HTTPS-only release networking, redacted debug-only logging, screenshot protection, comprehensive backup/device-transfer exclusion, R8 shrinking, externally supplied signing credentials, least-privilege permissions, account-wide logout cache/notification purge, CI build/lint/secret scanning, and a documented threat model/release checklist.

Tasks 010, 011, 012 and 013 are integrated. Migrations are linear: `0018_healthpackage`, `0019_healthcontent`, `0020_insurance_abha_readiness`.

Task 009 is not part of this stacked branch. Its `0018_patientfeedback` migration must be rebased after this branch and renumbered to `0021` before merge; no conflicting `0018` migrations may reach `main`.

Production distribution remains conditional on the documented manual device checks and valid external signing/API configuration. CI and automated suites are the repeatable automated gate.

## Automated gate evidence

- Django: `manage.py makemigrations --check --dry-run` — no changes; `manage.py test core` — 119 passed.
- Android: `testDebugUnitTest lintDebug assembleDebug` — successful.
- Minified release: `assembleRelease` succeeded with a temporary external keystore and HTTPS API URL.
- Release DEX scan found none of the provider-key patterns or known synthetic patient/policy identifiers checked by the gate.
