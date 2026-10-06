# Task 002 Completion Report — Secure Mobile API Foundation & Appointment Slice

**Owner:** Antigravity  
**Status:** READY-FOR-REVIEW  
**Date:** 2026-10-06  

---

### 1. Summary of Changes

#### A. Django HMS (`hospital-management-system`)
- Added Django REST Framework (`djangorestframework==3.18.1`), JWT authentication (`djangorestframework-simplejwt==5.5.1`), and filtering (`django-filter==26.2`) to `requirements.txt`.
- Created `PatientAccount` model (`core/models.py`, migration `core/migrations/0013_patientaccount.py`) linking auth `User` 1-to-1 with `Patient`.
- Enforced strict role boundary in `core/api/permissions.py` (`IsPatientUser`): prevents staff or superusers from calling patient portal endpoints and ensures patient context cannot be forged.
- Implemented `/api/v1/` endpoints (`core/api/views.py`, `core/api/urls.py`):
  - `POST /api/v1/auth/token/`: Patient JWT token login with rate throttling (`10/min`).
  - `POST /api/v1/auth/token/refresh/`: JWT refresh token flow.
  - `GET /api/v1/me/`: Returns patient profile and authoritative server-issued MRN.
  - `GET /api/v1/doctors/`: Returns active Doctor group staff with departments.
  - `GET /api/v1/visit-types/`: Returns active visit types.
  - `GET /api/v1/appointments/`: Returns authenticated patient's appointments only.
  - `POST /api/v1/appointments/`: Books appointment using authenticated patient identity; enforces doctor slot conflict locking (`409 Conflict`) and records `AuditEvent`.
  - `GET /api/v1/appointments/<id>/`: Returns single owned appointment and OPD-slip fields (returns `404 Not Found` for other patients' appointments).
  - `POST /api/v1/appointments/<id>/cancel/`: Cancels scheduled appointment idempotently; rejects cancellation for in-progress or completed appointments (`409 Conflict`).
- Standardized error response contract via `core/api/exceptions.py`.

#### B. Android Patient App (`hospital-vedant`)
- Restored Gradle 9.3.1 wrapper files (`gradlew`, `gradlew.bat`, `gradle-wrapper.jar`).
- Added `buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/api/v1/\"")` to `app/build.gradle.kts`.
- Created network layer in `com.example.network`:
  - `ApiDtos.kt`: Moshi-annotated data classes for requests/responses.
  - `HospitalApiService.kt`: Retrofit definitions for auth, doctors, visit types, and appointments.
  - `SessionManager.kt`: Shared preferences token storage.
  - `AuthInterceptor.kt`: Injects `Authorization: Bearer <token>` while redacting tokens in logs.
  - `NetworkClient.kt`: Configures OkHttpClient, timeout policies, Moshi converter, and header redaction.
- Extended `HospitalRepository.kt` and `HospitalViewModel.kt` to authenticate, fetch doctors/visit types, book appointments remotely, and update Room as a read cache.

---

### 2. Test Verification & Results

- **Django HMS:**
  - Dedicated API test suite: `core.test_patient_api` -> **9/9 tests passed**.
  - Full suite regression: `python manage.py test` -> **90/90 tests passed**.
  - System check: `python manage.py check` -> **0 issues**.
- **Android App:**
  - Baseline & Robolectric test suite: `./gradlew testDebugUnitTest` -> **Passed**.
  - New integration suite: `ApiIntegrationUnitTest` -> **Passed**.
  - Debug APK compilation: `./gradlew assembleDebug` -> **BUILD SUCCESSFUL**.

---

### 3. Branches & Commits

- **HMS Repository:**
  - Branch: `task-002-api-appointments`
  - Push URL: `https://github.com/hospitalmanagementsystem587-gif/hospital-management-system/pull/new/task-002-api-appointments`
  - Commit: `b7c01bde7090d1f5c4bd8b2b0e91ffdf450e615c`
- **Android Repository:**
  - Branch: `task-002-api-appointments`
  - Push URL: `https://github.com/abhishek-sahu-ai/hospital-vedant/pull/new/task-002-api-appointments`
  - Commit: `93e92105c1e6b8b048ec71d4975bbbdd860967fa`
