# Task 006 — Health Records, Prescriptions and Documents

## Status

Implemented in isolated, unpushed branches named `codex/task-006-health-records` in both repositories. The work is based on the Task 003 branch and does not modify Antigravity's active checkout.

## Django HMS

- Added patient-owned, read-only APIs for released consultations, issued prescriptions/items, and released documents under `/api/v1/me/`.
- Added explicit consultation/document release and revocation state.
- Prevented API exposure of diagnoses, clinical notes, uploader identities, storage paths, draft/cancelled prescriptions, and pharmacy data.
- Moved patient documents to non-public storage and added UUID-authorized downloads, size/type/digest validation, fail-closed malware-scan state, and no-store/nosniff headers.
- Added upload validation and protected staff downloads.
- Added migration `0016_patient_health_record_release_and_private_documents` and 10 API/security tests.

## Android

- Replaced production seeded/editable clinical records with authenticated network sync and a Room offline cache.
- Added released consultation, prescription-item, and protected document support.
- Reconciles revoked rows only after a fully successful collection sync and retains cached detail fields.
- Clearly labels cached/offline state and clears clinical data/downloads on logout or account change.
- Removed the mobile-generated “doctor-signed/ABDM-valid” prescription PDF from production.
- Excluded databases, session preferences, and app files from backup/device transfer.

## Verification

- Django: `manage.py makemigrations --check --dry-run` — pass.
- Django: 109 tests — pass after rebasing onto the repaired Task 003 branch.
- Android: `testDebugUnitTest` — pass.
- Both repositories: `git diff --check` — pass.

## Deployment prerequisites

- Configure `PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK`; uploads remain pending and cannot be released without a scanner.
- Existing document database rows and bytes intentionally remain fail-closed. A reviewed operational migration/import is required before legacy files can be served from private storage.
- Staff must deliberately set release/revocation fields (admin or a future reviewed clinical-release workflow). No record is released automatically.

## Integration note

Rebase these branches after the Task 002/003 remediation is finalized, then review and push. They have not been merged or pushed.
