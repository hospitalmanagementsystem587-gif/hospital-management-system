# KAN-40 Completion Report — Hospital Profile CMS

**Date:** 2026-10-08
**Ticket:** KAN-40 (Hospital Profile CMS)
**Branch:** `codex/kan-40-hospital-profile-cms`
**Base Commit (KAN-39):** `744e099bdd7abdebb013fb652e652b588fc06763`
**Status:** Completed and Verified

---

## 1. Executive Summary

Implemented the **Hospital Profile CMS** for the `admin.{domain}` portal host (`/admin/core/hospitalsettings/`). The implementation leverages the existing `HospitalSettings` singleton model (`pk=1`, enforced via `models.CheckConstraint(condition=Q(id=1), name="hospital_settings_one_row")`) and integrates seamlessly into the Django admin CMS ecosystem established in KAN-35 through KAN-39.

Zero new database migrations were added, zero duplicate models were introduced, and all validation (including IANA timezones, 3-letter ISO currency codes, clean strings, and required fields) executes server-side.

All authorization rules are enforced strictly server-side: only authenticated staff users with `core.view_hospitalsettings` and `core.change_hospitalsettings` permissions can view or edit the hospital profile. Unauthorized roles (Doctors, Receptionists, Pharmacists, Patients, and Unauthenticated visitors) are denied access with HTTP 302/403.

---

## 2. Acceptance Criteria Mapping

| Acceptance Criteria | Status | Implementation Details |
|---|---|---|
| **AC 1: Canonical Singleton Profile Enforcement** | Satisfied | Uses the existing `HospitalSettings` model. Deletion is forbidden (`has_delete_permission = False`), duplicate record addition is blocked (`has_add_permission` returns `False` when singleton exists), and changelist access automatically redirects straight to the canonical change view (`/admin/core/hospitalsettings/1/change/`). |
| **AC 2: Structured Administration Fieldsets** | Satisfied | Configured `HospitalSettingsAdmin` with 4 clear semantic fieldsets: `Hospital Identity` (name, tagline), `Localization & Regional Settings` (timezone, currency_code), `Emergency & Clinical Contacts` (emergency/ambulance/reception phones and display labels), and `General Communications & Location` (phone, email, address, landmark, city, maps_query). |
| **AC 3: Server-Side Form Validation** | Satisfied | `HospitalSettingsForm` validates required fields (`name`), verifies IANA timezone identifiers via Python `zoneinfo.ZoneInfo`, validates 3-letter alphabetic ISO currency codes (`INR`, `USD`), strips whitespace, and preserves existing database state on validation failures. |
| **AC 4: Server-Side Authorization & Role-Based Access Control** | Satisfied | Server-side Django permissions `core.view_hospitalsettings` and `core.change_hospitalsettings` govern viewing and updating. Portal boundary isolation prevents access from non-admin roles (Doctor, Reception, Pharmacy, Patient), and staff users without change permissions cannot mutate settings. |
| **AC 5: Public & Android API Backward Compatibility** | Satisfied | The public/Android endpoint `/api/v1/hospital-info/` (`HospitalInfoSerializer`) continues to operate seamlessly across all portal hosts without breaking contracts or schema changes. |
| **AC 6: Security & Content Escaping** | Satisfied | User-controlled profile values (such as hospital name and tagline) are safely HTML-escaped by Django template rendering engines, preventing XSS injection. |
| **AC 7: Zero Unnecessary Database Migrations** | Satisfied | All required profile fields already exist on `HospitalSettings`. Migration check confirmed zero schema drift. |

---

## 3. Files Changed

| File | Change Type | Description |
|---|---|---|
| `core/forms.py` | Modified | Added `HospitalSettingsForm` with custom cleaning and validation logic for `name`, `timezone` (via `zoneinfo`), `currency_code` (3-letter ISO), and contact numbers. |
| `core/admin.py` | Modified | Updated `HospitalSettingsAdmin` to use `HospitalSettingsForm`, structured fieldsets, disabled delete permission, disabled duplicate add permission, and redirected `changelist_view` directly to singleton `change_view`. |
| `config/urls_admin.py` | Modified | Included fallback legacy urlpatterns to ensure standard error templates (403, 404, 500) and shared route resolvers render correctly within the admin portal context. |
| `core/test_hospital_profile_cms.py` | Created | Comprehensive unit and integration test suite (13 test cases) covering authorization, viewing, updating, validation errors, duplicate prevention, delete restrictions, XSS escaping, and public API compatibility. |
| `agent-bridge/to-claude/kan-40-completion.md` | Created | This completion report. |

---

## 4. Database Migrations & Dependencies

- **Database migrations added:** 0
- **Migration drift verification:** `python manage.py makemigrations --check --dry-run` returned `No changes detected`.
- **Dependencies added:** 0 (uses Python 3.14 standard library `zoneinfo` and Django core).

---

## 5. Test Suite Verification

### New Test Suite (`core/test_hospital_profile_cms.py`)
Ran: `python manage.py test core.test_hospital_profile_cms -v 2`
Result: **13/13 passed** in 4.24s.

Tests included:
1. `test_singleton_changelist_redirects_to_singleton_change_view`: Changelist redirects to `/admin/core/hospitalsettings/1/change/`.
2. `test_authorized_admin_can_view_hospital_profile`: Staff Administrator can view profile form and fieldsets.
3. `test_authorized_admin_can_update_hospital_profile`: Staff Administrator can save valid updates.
4. `test_unauthenticated_user_redirected_to_login`: Anonymous users redirect to login with `next` param.
5. `test_unauthorized_portal_user_denied`: Doctor and Patient users receive 403 Forbidden on admin portal.
6. `test_admin_without_change_permission_cannot_post_updates`: View-only staff cannot mutate settings.
7. `test_validation_empty_required_name`: Blank name triggers form validation error and preserves DB data.
8. `test_validation_invalid_timezone`: Invalid timezone raises IANA error and preserves DB data.
9. `test_validation_invalid_currency_code`: Invalid currency code raises ISO 3-letter error and preserves DB data.
10. `test_singleton_delete_is_forbidden`: Profile deletion is rejected with 403 Forbidden.
11. `test_cannot_add_duplicate_singleton`: Adding a duplicate profile is rejected with 403 Forbidden.
12. `test_html_escaping_prevents_xss`: Malicious scripts in profile fields are escaped.
13. `test_public_android_api_reflects_updated_profile`: `/api/v1/hospital-info/` returns updated profile fields.

### Pre-Existing Test Suites Baseline (KAN-35 through KAN-39)
Ran: `python manage.py test core.test_portal_architecture core.test_shared_auth_session core.test_portal_authorization core.test_design_system core.test_admin_dashboard -v 1`
Result: **54/54 passed** in 5.34s.

### System Checks
- `python manage.py check`: 0 issues found.
- `python manage.py makemigrations --check --dry-run`: 0 changes detected.
- `git diff --check`: Clean, no whitespace or formatting issues.
