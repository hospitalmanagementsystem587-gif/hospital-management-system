# KAN-63 Completion: Doctor Consultation Workspace

## Overview
Implemented ticket KAN-63 — Doctor Consultation Workspace.
Enforced clinical authoring boundaries, object-level physician ownership, status-gated encounter initiation, idempotency against repeated submissions, and clinical privacy:
- Only attending doctors assigned to an in-progress appointment can open or document consultations.
- Appointments must be in `IN_PROGRESS` status; scheduled, checked-in, or completed encounters reject direct creation.
- Doctors cannot access or update consultations belonging to other physicians; unauthorized attempts return 404.
- Clinical notes and longitudinal histories are strictly scoped to the authoring physician to prevent cross-doctor leakage.
- Direct URL and POST access cannot bypass assignment scoping.
- Repeated or concurrent submissions return the existing consultation gracefully without creating duplicates.
- Audit events are emitted upon consultation creation (`clinical.consultation_created`) and chart access (`clinical.consultation_viewed`, `clinical.history_viewed`).

## Key Changes
1. **Clinical Scoping & Verification (`core/views.py`, `core/test_consultation_workspace.py`)**:
   - Audited existing `consultation_create`, `consultation_detail`, and `clinical_history` endpoints to ensure strict ownership checks against `_doctor_profile(request.user)`.
   - Verified that unassigned doctors receive 404 on attempt to open or detail another doctor's encounter.
   - Added acceptance test suite `core/test_consultation_workspace.py` (7 tests).

## Verification
- `core.test_consultation_workspace`: 7/7 passed
- Full regression suite (`core.test_appointment_workspace`, `core.test_patient_workspace`, `core.test_consultation_workspace`, `core.test_staff_dashboard`): 38/38 passed
- Django system check: 0 issues
- Migrations: clean, no drift
