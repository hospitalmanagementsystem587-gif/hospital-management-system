# KAN-36 Completion Report — Shared Authentication & Session Layer

**Date:** 2026-10-08
**Ticket:** KAN-36 (Portal Foundation — Shared Authentication & Session Layer)
**Branch:** `codex/kan-36-shared-auth-session`
**Base Commit (KAN-35):** `09d0f26195012befb393233e33001ea726e4efd3`
**KAN-36 implementation commit:** `2806cff4891152a51a8080f3e69f8c44b971ca60`
**Status:** Done

---

## 1. Executive Summary

Implemented the shared Django authentication and session layer required by KAN-36 across all five portal hosts (`admin.{domain}`, `staff.{domain}`, `store.{domain}`, `patient.{domain}`, `agent.{domain}`). Django authentication remains the single application authority. No Supabase Auth, parallel identity service, duplicate users, or portal-specific databases were introduced. The Android `/api/v1/` JWT authentication and lifecycle remain 100% intact and unchanged.

---

## 2. Files Changed

- `config/settings.py`:
  - Added `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_SAMESITE = "Lax"`.
  - Added configurable `SESSION_COOKIE_DOMAIN = os.getenv("DJANGO_SESSION_COOKIE_DOMAIN", None) or None`.
  - Added configurable `CSRF_COOKIE_DOMAIN = os.getenv("DJANGO_CSRF_COOKIE_DOMAIN", None) or None`.
- `config/portal_urls.py`:
  - Included `django.contrib.auth.urls` under `accounts/` across portal URLconfs.
  - Added `home` route alias to `portal_home` for seamless template reverse resolution.
- `core/views.py`:
  - Enhanced `HospitalLoginView.get_success_url()` to safely validate the `next` redirect target using Django's built-in `url_has_allowed_host_and_scheme`.
- `core/context_processors.py`:
  - Added `portal` to `hospital_context` so templates can read the active portal context (`request.portal`).
- `.env.example`:
  - Documented `DJANGO_SESSION_COOKIE_DOMAIN` and `DJANGO_CSRF_COOKIE_DOMAIN`.
- `docs/portal-architecture.md`:
  - Added the Shared Authentication & Session Layer specification and security decisions.
- `core/test_shared_auth_session.py`:
  - New focused test suite validating login/logout, safe redirects, inactive user rejection, session cookie policy, cross-subdomain cookie sharing, and template context.

---

## 3. Database & Migrations

- **Database migrations added:** 0
- **Migration drift:** Verified clean (`python manage.py makemigrations --check --dry-run` reports "No changes detected").

---

## 4. Security Decisions

1. **Identity Authority:** Django built-in auth (`django.contrib.auth`) remains authoritative. No duplicate credentials or secondary tables.
2. **Session & Cookie Security:**
   - Enforced `HttpOnly` and `SameSite=Lax` for sessions.
   - `Secure` cookies enforced when `DEBUG=False`.
   - Domain is strict host-only by default (`None`), with optional opt-in to `.domain` via `DJANGO_SESSION_COOKIE_DOMAIN` for cross-subdomain single sign-on across portal hosts.
3. **Throttling & Abuse Prevention:**
   - Retained and verified the 5-attempt failed-login throttle keyed by client IP + username per 10 minutes.
4. **Open Redirect Defense:**
   - Validated `next` redirect target to prevent open redirect attacks to untrusted domains.
5. **Inactive User Handling:**
   - Inactive users are rejected on login and have active session access revoked immediately.

---

## 5. Verification & Test Evidence

- **Django system checks:** `python manage.py check` → 0 issues.
- **Migration drift check:** `python manage.py makemigrations --check --dry-run` → No changes detected.
- **Focused KAN-36 test suite:** `python manage.py test core.test_shared_auth_session` → 6/6 tests passed.
- **KAN-35 Portal architecture tests:** `python manage.py test core.test_portal_architecture` → 7/7 tests passed.
- **Android JWT API tests:** `python manage.py test core.test_patient_api.PatientApiTests.test_token_refresh_and_blacklisting_revocation core.test_patient_api.PatientApiTests.test_logout_all_devices core.test_patient_api.PatientApiTests.test_auth_throttling_rejects_excessive_attempts` → 3/3 tests passed.
- **Auth/JWT targeted regression:** the three named Android JWT tests plus `AuthenticationLifecycleTests` and `RolePermissionTests` → 14/14 tests passed during independent verification.
- **Full Django suite:** `python manage.py test -v 1` → 137/137 tests passed during independent verification.
- **Whitespace / diff check:** Clean after the independent-review documentation cleanup commit.

---

## 6. Next Ticket

**KAN-37 — Portal-Aware Authorization & Role Mapping Matrix**
(Ready to begin from this verified KAN-36 commit `2806cff4891152a51a8080f3e69f8c44b971ca60`).
