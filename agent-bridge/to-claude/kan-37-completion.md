# KAN-37 Completion Report — Portal Foundation: Portal-Aware Authorization

**Date:** 2026-10-08
**Ticket:** KAN-37 (Portal Foundation — Portal-Aware Authorization)
**Branch:** `codex/kan-37-portal-authorization`
**Base Commit (KAN-36):** `d248f41a16ced64b0731b5629e4da3e5b2d9eaab`
**Status:** Done after independent remediation

---

## 1. Executive Summary

Implemented reusable, server-side portal-aware authorization and resource-level access control across all five browser portals (`admin.{domain}`, `staff.{domain}`, `store.{domain}`, `patient.{domain}`, `agent.{domain}`). Reused existing Django authentication, groups, permissions, `StaffProfile`, `PatientAccount`, and model relationships without introducing Supabase Auth, secondary identity databases, or speculative support-agent logic.

All portal admissions and object/record access boundaries are enforced server-side. Navigation and templates are never treated as security controls. Direct URL manipulation and unauthorized API requests fail closed. Non-disclosing 404 responses are returned where revealing existence poses a privacy risk (clinical consultations, prescriptions, sensitive patient documents), while HTTP 403 is returned where permission boundaries can safely be disclosed. Android `/api/v1/` JWT authentication and endpoints remain 100% compatible and intact.

---

## 2. Authorization & Role Mapping Matrix

### Portal Admission Gate

| Portal Host | Allowed Identities | Prohibited / Rejected | Response on Unauthorized |
| --- | --- | --- | --- |
| `admin.{domain}` | Active superusers, active Django staff (`user.is_staff and user.is_active`) | Anonymous, inactive, non-staff users (Doctors, Reception, Pharmacy, Patients) | 302 to `/accounts/login/` (anonymous) / 403 Forbidden (authenticated) |
| `staff.{domain}` | Active superusers, active members of `Administrator`, `Doctor`, `Reception`, `Pharmacy` | Anonymous, inactive, patients without staff profiles, ordinary users | 302 to `/accounts/login/` (anonymous) / 403 Forbidden (authenticated) |
| `store.{domain}` | Active superusers, active members of `Administrator`, `Pharmacy` | Anonymous, inactive, Doctor, Reception, patients, ordinary users | 302 to `/accounts/login/` (anonymous) / 403 Forbidden (authenticated) |
| `patient.{domain}` | Active superusers, active users with verified `PatientAccount` (`patient.archived_at is None`) | Anonymous, inactive, unverified patients, archived patients, staff without patient accounts | 302 to `/accounts/login/` (anonymous) / 403 Forbidden (authenticated) |
| `agent.{domain}` | Active superusers, active members of `Administrator` (fail-closed policy) | All other roles (Doctor, Reception, Pharmacy, patients, ordinary users) | 302 to `/accounts/login/` (anonymous) / 403 Forbidden (authenticated) |

### Object & Resource Authorization

| Resource / Action | Administrator | Reception | Doctor | Pharmacy | Verified Patient |
| --- | --- | --- | --- | --- | --- |
| **Patient Directory** | Denied (existing finance/master-data scope) | All active patients | Assigned patients only (`doctor_patient_queryset`) | Lookup only within authorized pharmacy workflows | Self only (via API) |
| **Appointments** | Denied | All appointments (scheduling/queue) | Own assigned schedule | Denied | Own appointments (via API) |
| **Clinical Consultations** | Denied | Denied | Attending doctor only | Denied | Self only (via API when released) |
| **Prescriptions** | Denied | Denied | Prescribing doctor | Issued prescriptions (`Status.ISSUED`) | Self only (via API when released) |
| **Documents & Downloads** | Denied through staff patient routes | Clean files for active patients | Clean files for assigned patients | Denied | Own released, non-revoked clean documents |
| **Inpatient (IPD)** | View all, deposits, discharge | View all, admit, deposits, discharge | View all, discharge | Denied | Denied |
| **Invoices & Billing** | All, discounts, voids, refunds | All, create, payments | Denied | Denied | Own invoices (via API) |
| **Pharmacy Stock & Dispense** | Denied (master data only) | Denied | Denied | Receipts, OTC sales, dispenses, adjustments, quarantine | Denied |

---

## 3. Files Changed

- `core/authorization.py`:
  - Added centralized `PORTAL_ALLOWED_GROUPS` constant.
  - Implemented `user_can_access_portal(user, portal)` enforcing active status, superuser admission, staff requirements, group permissions, and verified non-archived patient accounts.
  - Added `get_authorized_patient_queryset(user)` and `get_authorized_appointment_queryset(user)` providing clean object-level filtering.
- `core/portal/middleware.py`:
  - Refactored `user_can_access_portal` to delegate to `core.authorization`.
  - Enforced portal boundaries server-side with proper URLconf selection.
- `core/views.py`:
  - Integrated `_patient_read_queryset` and `_appointment_read_queryset` with the centralized helpers.
  - Preserved explicit 403 responses for Administrator, Pharmacy, and other roles outside operational patient/appointment workspaces.
- `core/test_portal_authorization.py`:
  - Created 19 comprehensive positive and negative test cases covering all 5 portals, live-route scopes, roles, object isolation, two-patient privacy, and non-disclosing 404 responses.
- `docs/portal-architecture.md`:
  - Documented the Portal-Aware Authorization & Role Mapping Matrix specification.

---

## 4. Database & Migrations

- **Database migrations added:** 0
- **Migration drift check:** `python manage.py makemigrations --check --dry-run` → "No changes detected".

---

## 5. Security Controls & Privacy Protection

1. **Non-Disclosing 404 Responses:** Direct URL access to consultations, prescriptions, or patient documents outside an identity's authorized scope returns HTTP 404 rather than 403, preventing object existence leakage.
2. **Two-Patient Isolation:** Verified that Patient A and Patient B cannot view, query, or download each other's invoices, appointments, or medical documents across both portal and API routes.
3. **Malware & Validation Enforced:** All document downloads verify stored-file integrity and clean validation status. Patient-facing downloads additionally enforce ownership, release, and non-revocation; authorized staff may access clean internal documents before patient release.
4. **Agent Portal Fail-Closed:** The agent portal strictly permits only superusers and `Administrator` accounts; no speculative support-agent role was introduced.

---

## 6. Verification & Test Evidence

- **Django system checks:** `python manage.py check` → 0 issues.
- **Migration drift check:** `python manage.py makemigrations --check --dry-run` → No changes detected.
- **KAN-37 Authorization test suite:** `python manage.py test core.test_portal_authorization` → 19/19 passed, including live-route scope integration coverage.
- **KAN-35 Portal architecture tests:** `python manage.py test core.test_portal_architecture` → 7/7 tests passed.
- **KAN-36 Shared auth/session tests:** `python manage.py test core.test_shared_auth_session` → 6/6 tests passed.
- **Android JWT API tests:** `python manage.py test core.test_patient_api.PatientApiTests.test_token_refresh_and_blacklisting_revocation core.test_patient_api.PatientApiTests.test_logout_all_devices core.test_patient_api.PatientApiTests.test_auth_throttling_rejects_excessive_attempts` → 3/3 tests passed.
- **Role/auth lifecycle regression:** `python manage.py test core.tests.RolePermissionTests core.tests.AuthenticationLifecycleTests` → 11/11 tests passed.
- **Full Django test suite:** `python manage.py test -v 1` → 156/156 passed after independent remediation.
- **Git diff whitespace check:** `git diff --check` → clean after remediation.

---

## 7. Next Ticket

**KAN-38 — UI/Design System Foundation & Token Architecture**
*(Ready to proceed in the next planned run)*
