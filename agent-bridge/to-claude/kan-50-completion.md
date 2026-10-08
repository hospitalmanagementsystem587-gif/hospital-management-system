# KAN-50 Completion Report: Facilities and FAQs CMS

## 1. Overview
Delivered clean Admin CMS workflows for Hospital Facilities and FAQs as specified in Jira ticket **KAN-50**.
Reused the existing `HospitalFacility` and `HospitalFaq` models (`core.0017_hospitalfacility_hospitalfaq_...`) with structured admin form controls, validation, deterministic ordering, and server-side role authorization.

## 2. Changes
- **`core/forms.py`**:
  - Implemented `HospitalFacilityForm` with case-insensitive unique `title` validation and non-negative `display_order` check.
  - Implemented `HospitalFaqForm` with case-insensitive unique `question` validation and non-negative `display_order` check.
  - Configured input widgets for titles, textareas, tags, and orders.
- **`core/admin.py`**:
  - Enhanced `HospitalFacilityAdmin` with `form = HospitalFacilityForm`, fieldsets (`Facility Identity & Placement`, `Overview & Accreditations`), `list_editable = ("display_order", "is_active")`, search, and filter.
  - Enhanced `HospitalFaqAdmin` with `form = HospitalFaqForm`, fieldsets (`FAQ Classification & Visibility`, `Question & Clinical/Administrative Answer`), `list_editable = ("display_order", "is_active")`, search, and filter.
- **`core/roles.py`**:
  - Granted `core.view_hospitalfacility`, `core.add_hospitalfacility`, `core.change_hospitalfacility`, `core.delete_hospitalfacility`, `core.view_hospitalfaq`, `core.add_hospitalfaq`, `core.change_hospitalfaq`, and `core.delete_hospitalfaq` permissions to the `Administrator` role.
- **`core/test_facilities_faqs_cms.py`**:
  - Created 10 test cases verifying admin list view, unauthorized staff rejection (403), creation flows, case-insensitive uniqueness validation, non-negative display order validation, and public API deterministic sorting/active filtering.

## 3. Verification
- `manage.py check`: Passed (0 issues).
- `manage.py makemigrations --check --dry-run`: Passed (no migration drift).
- `manage.py test core.test_facilities_faqs_cms -v 2`: 10 passed.
- Regression suite (`core.test_facilities_faqs_cms`, `core.test_website_content_cms`, `core.test_health_package_cms`): 26 passed.
