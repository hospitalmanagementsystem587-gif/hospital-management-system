# KAN-69 Completion: Medicine Catalog

## Overview
Implemented ticket KAN-69 — Medicine Catalog.
Established the full formulary and medicine catalog management workspace within the store portal:
- Dedicated endpoints:
  - Catalog list: `/store/medicines/`
  - Medicine create: `/store/medicines/create/`
  - Medicine update: `/store/medicines/<int:pk>/edit/`
- Role scoping: Accessible exclusively to `Pharmacy` and `Administrator` roles (plus superusers). Unauthorized roles (`Doctor`, `Reception`, unauthenticated users) receive 403 Forbidden / login redirect.
- Filtering & Search: Supports querying by code, generic name, brand name, and barcode, with status filtering (`all`, `active`, `inactive`) and pagination.
- Master Record Integrity: Enforces unique code and barcode validation across medicines.
- Historical Reference Continuity: Deactivating a medicine (`is_active=False`) soft-disables it for new prescription and dispensing workflows while strictly preserving all historical prescriptions, items, and inventory batches without cascading deletion or orphaned records.
- Audit Logging: Captures audited financial/clinical events on medicine creation (`pharmacy.medicine_created`) and updates (`pharmacy.medicine_updated`).
- Boundary Protection: Strictly preserves boundary with KAN-70+; no inventory batch receiving, stock intake, or supplier workflows were introduced.

## Key Changes
1. **Forms (`core/forms.py`)**:
   - Added `MedicineForm` handling `code`, `generic_name`, `brand_name`, `strength`, `dosage_form`, `unit`, `barcode`, `is_otc`, and `is_active` with code/barcode uniqueness validation.
2. **Views & Routing (`core/views.py`, `config/urls.py`)**:
   - Added `medicine_list`, `medicine_create`, and `medicine_update` with permission checks and audit logging.
   - Wired routes in `config/urls.py` under `store/medicines/`.
3. **Templates (`core/templates/core/store/medicine_list.html`, `core/templates/core/store/medicine_form.html`, `core/templates/core/store/dashboard.html`)**:
   - Built responsive catalog list and create/edit form templates styled with the shared design system.
   - Linked catalog directly from the pharmacy dashboard.
4. **Tests (`core/test_medicine_catalog.py`)**:
   - 8 acceptance tests covering:
     - Anonymous redirect to login.
     - Role denial for Doctor, Reception, and Ordinary users (403).
     - Pharmacy and Administrator access.
     - Code, generic name search, and status filtering.
     - Medicine creation with uniqueness checks and audit event emission.
     - Medicine editing and audit logging.
     - Historical continuity preservation when deactivating medicines.

## Verification
- `core.test_medicine_catalog`: 8/8 passed
- Cumulative batch suite (KAN-60 to KAN-69): 89/89 passed
- Django system check: 0 issues
- Migrations: clean, no drift
- Git diff whitespace check: clean
