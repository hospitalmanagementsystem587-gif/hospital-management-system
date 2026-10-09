# KAN-70 Completion: Inventory and Batch Management

## Overview
Implemented ticket KAN-70 — Inventory and Batch Management.
Established the dedicated Inventory & Batch Management workspace in the Store portal:
- Dedicated endpoints:
  - Batch list directory: `/store/batches/`
  - Batch detail & audit movement ledger: `/store/batches/<int:pk>/`
- Role scoping: Accessible strictly to `Pharmacy` and `Administrator` roles. Doctor, Reception, Ordinary, and unauthenticated users receive 403 Forbidden / login redirect.
- FEFO Integrity: Sorts batches by `expiry_date ASC, pk ASC` to uphold First-Expiry-First-Out dispensing standards.
- Advanced Filtering & Search: Supports search across batch number, medicine generic name, brand name, code, and supplier, with dedicated status filters (`all`, `active`, `low_stock`, `expired`, `quarantined`) and pagination.
- Full Audit Trail & Ledger: Displays chronological stock movements (`StockMovement`) for each batch with delta, before/after balances, reference type/id, and actor.
- Governed Stock Adjustments & Quality Quarantine Controls: Integrated validated stock adjustment and batch quarantine toggles with idempotency request keys, row locking (`select_for_update()`), and audit event logging (`AuditEvent`).
- Boundary Preservation: Built cleanly on existing canonical `MedicineBatch`, `StockMovement`, `Supplier`, and `StockReceipt` models without duplicate schemas or premature KAN-71+ workflows.

## Key Changes
1. **Views (`core/views.py`)**:
   - Added `batch_list` and `batch_detail` views with permissions check (`core.view_medicinebatch`), filtering, FEFO ordering, and pagination.
   - Enhanced `stock_adjustment` and `batch_quarantine` to accept an optional `next` redirect target parameter to seamlessly support actions from batch directory/detail workspaces.
2. **URLs (`config/urls.py`)**:
   - Registered `/store/batches/` (`batch_list`) and `/store/batches/<int:pk>/` (`batch_detail`).
3. **Role Permissions (`core/roles.py`)**:
   - Added `core.view_medicinebatch` to `Administrator` role permissions.
4. **Templates (`core/templates/core/store/batch_list.html`, `core/templates/core/store/batch_detail.html`, `core/templates/core/store/dashboard.html`)**:
   - Created `batch_list.html`: FEFO batch directory with search, filter tabs, stock status badges, and quick controls.
   - Created `batch_detail.html`: Full batch specifications, stock on hand vs received, pricing, adjustment & quarantine forms, and complete `StockMovement` ledger table.
   - Updated `dashboard.html`: Added quick action link to `batch_list` ("Inventory & Batches").
5. **Tests (`core/test_inventory_batch_workspace.py`)**:
   - 11 comprehensive acceptance tests covering anonymous redirect, role restriction (Doctor/Reception/Ordinary 403), Pharmacy and Administrator access, FEFO ordering, status filtering, batch/medicine search, movement ledger rendering, stock adjustment, quarantine toggling, and negative stock prevention.

## Verification
- `core.test_inventory_batch_workspace`: 11/11 passed
- Regressions (`core.test_portal_authorization`, `core.test_pharmacy_dashboard`, `core.test_medicine_catalog`): 35/35 passed
- Django system check: 0 issues
- Migrations: clean, no drift
- Git diff whitespace check: clean
