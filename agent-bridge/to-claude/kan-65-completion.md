# KAN-65 Completion: Clinical Document Workspace

## Overview
Implemented ticket KAN-65 — Clinical Document Workspace.
Enforced server-side private storage protection, object-level patient access scoping, integrity verification, validation gating, and audit logging:
- Private documents are stored securely with verified SHA-256 digests and file metadata.
- Document viewing and downloading is object-scoped via `_patient_read_queryset(request.user)`.
- Doctors can only download clean documents for their clinically assigned patients. Attempts by unassigned doctors return non-disclosing 404 responses.
- Reception and Administrator users have operational access to upload and download patient documents.
- Pharmacy and unauthorized users receive 403 on upload and download endpoints.
- Rejected or unvalidated documents cannot be downloaded (returns 404).
- Safe HTTP download headers are enforced: `Cache-Control: private, no-store`, `Pragma: no-cache`, `X-Content-Type-Options: nosniff`.
- Audit logs are recorded on upload (`patient.document_uploaded`) and download (`patient.document_downloaded`).

## Key Changes
1. **Audit Logging & Verification (`core/views.py`)**:
   - Added `patient.document_downloaded` audit emission in `patient_document_download`.
2. **Testing (`core/test_clinical_document_workspace.py`)**:
   - Added 7 acceptance criteria tests verifying:
     - Anonymous redirect to login.
     - Pharmacy role denial (403).
     - Assigned doctor clean document download, audit logging, and security headers.
     - Unassigned doctor access rejection (non-disclosing 404).
     - Rejected/unclean document non-disclosure (404).
     - Reception and Administrator document download.
     - Document upload by Reception with metadata inspection and audit emission.

## Verification
- `core.test_clinical_document_workspace`: 7/7 passed
- Regression suite (KAN-60 to KAN-65): 52/52 passed
- Django system check: 0 issues
- Migrations: clean, no drift
