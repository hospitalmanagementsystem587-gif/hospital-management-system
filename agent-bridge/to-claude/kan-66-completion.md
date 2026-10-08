# KAN-66 Completion: IPD Workspace

## Overview
Implemented ticket KAN-66 — IPD Workspace.
Enforced server-side inpatient admission control, concurrent bed allocation safety via row-level locks, immutable pricing snapshots, advance deposit accounting boundaries, and patient discharge workflows:
- Admission creation enforces `select_for_update` bed locking to prevent race conditions or double booking.
- `daily_rate_snapshot` captures the exact daily ward charge at the time of admission; retroactive ward tariff modifications cannot mutate existing admission snapshots.
- Inpatient advance deposits are recorded with receipt sequence generation and audited financial events (`ipd.deposit_received`).
- Discharging patients releases occupied beds back to `AVAILABLE` status and emits discharge audit records (`ipd.patient_discharged`).
- Unauthorized roles (such as Pharmacy users) receive 403 on IPD management views.

## Key Changes
1. **Concurrency & Safe Bed Allocation (`core/views.py`)**:
   - Updated `admission_create` to lock the selected bed using `Bed.objects.select_for_update()` and verify its status is `AVAILABLE` before creating the admission record.
2. **Testing (`core/test_ipd_workspace.py`)**:
   - Added 7 acceptance criteria tests verifying:
     - Anonymous redirect to login.
     - Role restriction for Pharmacy users (403).
     - Admission list visibility for Reception and Administrator.
     - Admission creation with bed status updating to `OCCUPIED`, `daily_rate_snapshot` preservation against retroactive ward price changes, and audit event emission.
     - Prevention of double-allocation for already occupied beds.
     - Inpatient advance deposit recording, sequence numbering, and audit logging.
     - Discharge processing, bed release back to `AVAILABLE`, and discharge audit logging.

## Verification
- `core.test_ipd_workspace`: 7/7 passed
- Regression suite (KAN-60 to KAN-66): 59/59 passed
- Django system check: 0 issues
- Migrations: clean, no drift
