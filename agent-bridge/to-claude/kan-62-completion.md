# KAN-62 Completion: Patient Workspace

## Overview
Implemented ticket KAN-62 — Patient Workspace.
Enforced server-side queryset and object scoping across roles:
- Reception and Administrator users have operational access to register, update demographics, and view all non-archived patient records.
- Attending doctors only see assigned/clinically related patients (via appointments or consultations) and their safety/allergy notes; access to unassigned patient charts returns 404.
- Pharmacy and unauthorized users cannot access patient management workspaces.
- Archived patients are excluded from search, list, and detail views.
- Audit events are emitted on patient registration (`patient.created`) and demographic updates (`patient.demographics_updated`).
- Android patient self-access and booking endpoints remain fully intact.

## Key Changes
1. **Authorization & Role Scoping (`core/authorization.py`, `core/roles.py`, `core/views.py`)**:
   - Updated `get_authorized_patient_queryset` and `_patient_read_queryset` to include `Administrator` alongside `Reception`.
   - Added `"core.view_patient"`, `"core.add_patient"`, and `"core.change_patient"` to `ROLE_PERMISSIONS["Administrator"]`.
   - Updated `patient_list`, `patient_create`, `patient_detail`, and `patient_update` to authorize Reception and Administrator roles while restricting doctors from patient creation/update mutations.

2. **Testing (`core/test_patient_workspace.py`)**:
   - Added 10 acceptance criteria tests covering:
     - Anonymous redirect to login.
     - Role denial for Pharmacy users.
     - Scoped visibility for Reception and Administrator (all non-archived patients).
     - Doctor clinical scoping (only assigned/clinically related patients).
     - Doctor prevention from viewing unassigned patient detail (404).
     - Search scoping preventing leaking out-of-scope patients.
     - Archived patient exclusion.
     - Patient registration with sequence numbering and audit logging by Reception and Administrator.
     - Patient demographics updates and audit logging.
     - Doctor prevention from creating/updating patients (403).

## Verification
- `core.test_patient_workspace`: 10/10 passed
- `core.test_appointment_workspace`: 11/11 passed
- `core.test_staff_dashboard`: 10/10 passed
- `core.test_patient_api`: 28/28 passed
- Django system check: 0 issues
- Migrations: clean, no drift
