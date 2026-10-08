# KAN-64 Completion: Prescription Workspace

## Overview
Implemented ticket KAN-64 — Prescription Workspace.
Enforced server-side doctor ownership, inactive medicine filtering, pharmacy dispensing queues, and HTML-escaped print layouts:
- Prescriptions are issued strictly linked to authorized consultations and patients by attending physicians.
- Unassigned doctors cannot view, edit, or print other doctors' prescriptions (404 returned on cross-physician access).
- Inactive medicines are strictly excluded from prescribing formsets (`PrescriptionItemFormSet`).
- Pharmacy and Administrator users have access to view and print issued prescriptions and inspect the dispensing queue.
- Prescription print template escapes all user-supplied input (demographics, instructions, safety notes) to prevent XSS.
- Audit logging records print actions (`clinical.prescription_printed`).

## Key Changes
1. **Roles & Authorization (`core/roles.py`, `core/views.py`)**:
   - Added `"core.view_prescription"` to `ROLE_PERMISSIONS["Administrator"]`.
   - Updated `prescription_print` to allow Administrator alongside Pharmacy and Doctor roles.
2. **Testing (`core/test_prescription_workspace.py`)**:
   - Added 7 acceptance criteria tests verifying:
     - Anonymous redirect to login.
     - Reception access rejection (403).
     - Cross-physician print rejection (404).
     - Authoring doctor print access, audit logging, and XSS escaping.
     - Pharmacy and Administrator view/print access.
     - Inactive medicine exclusion from prescription formset.
     - Pharmacy queue visibility for issued prescriptions.

## Verification
- `core.test_prescription_workspace`: 7/7 passed
- Regression suite (KAN-60 to KAN-64): 45/45 passed
- Django system check: 0 issues
- Migrations: clean, no drift
