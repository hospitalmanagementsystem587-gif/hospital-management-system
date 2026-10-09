# KAN-68 Completion: Pharmacy Dashboard

## Overview
Implemented ticket KAN-68 — Pharmacy Dashboard.
Established the dedicated store/pharmacy dashboard on the store portal host (`store.hms.test`) and direct endpoint (`/pharmacy/`):
- Restricts dashboard access strictly to `Pharmacy` and `Administrator` roles (plus superusers); unauthorized roles (Doctor, Reception, unverified accounts) receive 403 Forbidden.
- Bounded single-query aggregates for operational metrics:
  - Active/Issued Prescriptions awaiting fulfillment (`Prescription.objects.filter(status=ISSUED).count()`)
  - Low stock batches below reorder threshold (`MedicineBatch.objects.filter(quantity_on_hand__lt=10, is_quarantined=False).count()`)
  - Expired batch holds (`MedicineBatch.objects.filter(expiry_date__lt=today).count()`)
  - Active catalog medicines count (`Medicine.objects.filter(is_active=True).count()`)
- Patient privacy protection: strict minimization of patient data, clinical notes, and medical diagnoses from dashboard views.
- Safe default values and empty states.
- Clean integration with the shared design system with store portal thematic accents (`[data-portal="store"]`).

## Key Changes
1. **Views & Routing (`core/views.py`, `config/urls.py`, `config/urls_store.py`)**:
   - Added `pharmacy_dashboard` view with role checks and bounded metric queries.
   - Wired `pharmacy_dashboard` to `/pharmacy/` and to the store portal root (`/` on `store.hms.test`), including legacy pharmacy endpoints while preserving `Store portal` markers.
2. **Templates (`core/templates/core/store/dashboard.html`)**:
   - Created clean, responsive store dashboard reusing Stitch KPI cards, quick actions for dispensing queue and OTC sales, and safety protocol notices.
3. **Tests (`core/test_pharmacy_dashboard.py`)**:
   - 6 acceptance tests verifying:
     - Anonymous redirect to login.
     - Role denial for Doctor, Reception, and Ordinary users (403).
     - Pharmacy and Administrator access (200).
     - Accurate bounded metrics calculation for prescriptions, batches, and active medicines.
     - Patient PII minimization.
     - Safe empty states.

## Verification
- `core.test_pharmacy_dashboard`: 6/6 passed
- Cumulative regression suite (KAN-60 to KAN-68): 74/74 passed
- Django system check: 0 issues
- Migrations: clean, no drift
