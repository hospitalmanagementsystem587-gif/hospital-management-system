# KAN-71 Completion: Supplier Management

## Overview
Implemented ticket KAN-71 — Supplier Management.
Established the full vendor and supplier management workspace in the Store portal:
- Dedicated endpoints:
  - Supplier list: `/store/suppliers/`
  - Supplier create: `/store/suppliers/create/`
  - Supplier edit: `/store/suppliers/<int:pk>/edit/`
- Role scoping: Accessible strictly to `Pharmacy` and `Administrator` roles. Doctor, Reception, Ordinary users receive 403 Forbidden. Unauthenticated requests redirect to login.
- Search & Filtering: Real-time search across supplier code, name, phone, email, and status filtering (`all`, `active`, `inactive`) with pagination.
- Integrity & Unique Codes: Enforces unique supplier code validation case-insensitively.
- Historical Reference Continuity: Deactivating a supplier soft-disables them from new procurement/receipt intake workflows while strictly preserving all existing `StockReceipt` and `MedicineBatch` records and pricing history without data loss or cascading deletes.
- Audit Logging: Tracks audited events on supplier creation (`pharmacy.supplier_created`) and updates (`pharmacy.supplier_updated`).
- Boundary Preservation: Reused existing canonical `Supplier` model without duplicate models or migrations. Preserves boundary with KAN-72+ stock intake workflows.

## Key Changes
1. **Forms (`core/forms.py`)**:
   - Added `SupplierForm` handling `code`, `name`, `phone`, `email`, `address`, `is_active` with unique code and non-empty name validations.
2. **Views & URLs (`core/views.py`, `config/urls.py`)**:
   - Added `supplier_list`, `supplier_create`, `supplier_update` views with permissions (`core.view_supplier`, `core.add_supplier`, `core.change_supplier`) and audit logging.
   - Wired routes in `config/urls.py` under `/store/suppliers/`.
3. **Templates (`core/templates/core/store/supplier_list.html`, `core/templates/core/store/supplier_form.html`, `core/templates/core/store/dashboard.html`)**:
   - Built responsive `supplier_list.html` and `supplier_form.html` templates.
   - Added `Supplier Directory` quick action link to Store Portal Dashboard.
4. **Tests (`core/test_supplier_workspace.py`)**:
   - 8 acceptance tests covering anonymous redirect, role restriction (Doctor/Reception/Ordinary 403), Pharmacy and Administrator access, search and filtering, supplier creation with audit logging, duplicate code prevention, and deactivation with historical continuity preservation.

## Verification
- `core.test_supplier_workspace`: 8/8 passed
- Regressions (`test_inventory_batch_workspace`, `test_medicine_catalog`, `test_pharmacy_dashboard`, `test_portal_authorization`): 46/46 passed
- Django system check: 0 issues
- Migrations: clean, no drift
- Git diff whitespace check: clean
