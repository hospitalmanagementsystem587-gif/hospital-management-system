# KAN-61 Completion: Appointment Workspace

## Overview
Implemented ticket KAN-61 — Appointment Workspace.
Ensured scoped access across Doctor, Reception, and Administrator roles, safe conflict prevention with duration checking, canonical consultation price rendering, audit event emission, and server-side status transition validation.

## Key Changes
1. **Scoping and Permissions (`core/authorization.py`, `core/roles.py`, `core/views.py`)**:
   - Extended `get_authorized_appointment_queryset` and `_appointment_read_queryset` to include the `Administrator` role alongside `Reception` (all appointments) while preserving strict doctor scoping (only their own assigned appointments).
   - Added `core.view_appointment`, `core.add_appointment`, and `core.change_appointment` to `ROLE_PERMISSIONS["Administrator"]`.
   - Enabled `can_manage_appointments` flag for Reception and Administrator in `appointment_list`, `appointment_create`, `appointment_reschedule`, and `appointment_transition`.

2. **Canonical Price Display (`core/templates/core/appointments/list.html`)**:
   - In the appointment list Care Assignment column, integrated resolved canonical consultation pricing: `₹{{ appointment.doctor.get_consultation_price }}` alongside the visit type.

3. **Status Transitions & Audit Logging (`core/views.py`)**:
   - Retained server-side state machine separation between reception/admin check-ins/cancellations and doctor-specific start/complete actions.
   - Emits `appointment.created` and `appointment.rescheduled` audit logs.

4. **Testing (`core/test_appointment_workspace.py`)**:
   - Added 11 focused acceptance criteria tests covering:
     - Anonymous redirect to login.
     - Role denial for unauthorized users (Pharmacy, ordinary non-staff).
     - Doctor queryset scoping (Doctor 1 sees only Doctor 1 appointments).
     - Reception and Administrator visibility over all appointments.
     - Appointment booking with conflict prevention and audit logging.
     - Reschedule slot conflict validation.
     - Doctor prevention from creating/rescheduling appointments.
     - Status transitions by Reception and Doctor.
     - Cross-doctor transition rejection (404).
     - Canonical consultation fee display in the workspace.

## Verification
- `core.test_appointment_workspace`: 11/11 passed
- `core.test_patient_api`: 28/28 passed (Android patient API compatibility intact)
- `core.test_staff_dashboard`: 10/10 passed
- `check` and `makemigrations --check --dry-run`: 0 issues, no migrations required
