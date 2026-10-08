# KAN-51 Completion Report: Public Website Publishing Workflow

## 1. Overview
Implemented controlled publishing and auditing workflows for public hospital CMS content as specified in Jira ticket **KAN-51**.
The implementation reinforces explicit draft vs published states across `HealthContent`, `HealthPackage`, `HospitalFacility`, and `HospitalFaq`, enforces clinical and administrative role governance, guarantees that public APIs only expose published/active records, and records structured `AuditEvent` entries upon publication and status transitions.

## 2. Changes
- **`core/forms.py`**:
  - Enhanced `HealthPackageForm` to allow optional service bundles during initial authoring (`self.fields["included_services"].required = False`).
- **`core/admin.py`**:
  - Updated `HealthContentAdmin.save_model` to log `AuditEvent` (`content.created`, `content.published`, `content.unpublished`, or `content.status_changed`) capturing author, reviewer, slug, and status changes. Preserved strict clinical approval permission check (`core.publish_healthcontent`).
  - Updated `HealthPackageAdmin.save_model` to log `AuditEvent` (`healthpackage.created`, `healthpackage.published`, `healthpackage.unpublished`).
  - Updated `HospitalFacilityAdmin.save_model` to log `AuditEvent` (`facility.created`, `facility.activated`, `facility.deactivated`).
  - Updated `HospitalFaqAdmin.save_model` to log `AuditEvent` (`faq.created`, `faq.activated`, `faq.deactivated`).
- **`core/test_public_publishing_workflow.py`**:
  - Created 4 comprehensive test scenarios covering clinical reviewer publishing flow, audit trail logging, public API boundary verification (draft exclusion), package publishing lifecycle, facility activation audit logging, and rejection of unauthorized publishing attempts.

## 3. Verification
- `manage.py check`: Passed (0 issues).
- `manage.py makemigrations --check --dry-run`: Passed (no migration drift).
- `manage.py test core.test_public_publishing_workflow -v 2`: 4 passed.
- Regression suite (`core.test_public_publishing_workflow`, `core.test_facilities_faqs_cms`, `core.test_website_content_cms`, `core.test_health_package_cms`): 30 passed.
