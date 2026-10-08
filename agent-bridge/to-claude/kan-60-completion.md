# KAN-60 Completion Report — Staff Dashboard

## 1. Overview
Implemented role-scoped, accessible, and bounded Staff Dashboard as specified in Jira ticket **KAN-60**.
The implementation verifies coarse portal access control (`staff.hms.test` / `config.urls_staff`), role-aware KPI grids (Reception, Doctor, Pharmacy, Administrator), doctor-specific metric scoping by assigned doctor profile, safe empty states, bounded aggregate queries, and permission-checked workspace navigation links.

## 2. Acceptance Criteria Mapping
- **Role-Aware Staff Dashboard**: Doctor, Reception, Pharmacy, and Administrator users see only appropriate summaries and operational KPIs.
- **Bounded Aggregate Queries**: Metrics use bounded single-query aggregates (`.count()` and `.aggregate(total=Sum(...))`), preventing high query volumes or full-table memory loading.
- **Patient Privacy**: No patient medical notes or personally identifiable clinical details are leaked on dashboard summaries.
- **Authorized Workspace Links**: Links point only to implemented and authorized workspaces (`/patients/`, `/appointments/`, `/ipd/admissions/`, `/invoices/`, `/pharmacy/prescriptions/`).
- **Safe Empty States**: Renders default values (`0`, `₹0.00`) safely without errors or unhandled exceptions when staff profile or records are missing.
- **Shared Design System Reused**: Reuses KAN-38 shared design components and responsive tokens.

## 3. Changes
- `core/views.py`: Initialized safe zero defaults for doctor dashboard metrics when `StaffProfile` is missing.
- `core/templates/core/home.html`: Added permission-checked quick action link for Inpatient (IPD) Admissions (`perms.core.view_admission`).
- `core/test_staff_dashboard.py`: Created test suite covering role scoping, anonymous access, wrong-role denial, doctor assignment scoping, safe defaults, workspace links, and query count bounding.

## 4. Verification
- `manage.py check`: Passed (0 issues).
- `manage.py makemigrations --check --dry-run`: Passed (no changes detected).
- `manage.py test core.test_staff_dashboard -v 2`: 10 passed.
- `git diff --check`: Clean.
