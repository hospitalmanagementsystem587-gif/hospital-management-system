# Task 003 Completion Report — Patient Onboarding, Identity Verification & Profile Management

**Owner:** Antigravity  
**Status:** READY-FOR-REVIEW  
**Date:** 2026-10-06  

---

### 1. Summary of Changes

#### A. Django HMS (`hospital-management-system`)
- **Models & Migrations:**
  - Extended `PatientAccount` (`core/models.py`) with `phone_verified`, `email_verified`, `identity_provider`, and `id_document_reference` (migrations `0014` and `0015`).
  - Added `PatientVerificationChallenge` model (`core/models.py`) tracking verification contact, purpose, per-challenge cryptographic `salt`, PBKDF2 HMAC-SHA256 hashed code, attempt counts (max 3), expiration (10 min), and consumed status.
- **Verification Service:**
  - Implemented `VerificationProvider` in `core/services/verification.py` generating cryptographically random 6-digit OTPs, storing PBKDF2 HMAC-SHA256 salted hashes, strictly enforcing max attempts (3), and expiration windows (10 minutes).
- **API Endpoints (`core/api/views.py`, `core/api/urls.py`):**
  - `POST /api/v1/auth/otp/request/`: Dispatches OTP challenge for registration, login, or claiming without leaking contact existence (user enumeration defense).
  - `POST /api/v1/auth/register/`: Validates challenge token + OTP, allocates authoritative server-generated MRN (`next_number("PATIENT")`), creates auth `User` and `PatientAccount`.
  - `POST /api/v1/auth/claim-patient/`: Claims existing hospital patient record using MRN + verified contact with uniform 404 response for nonexistent MRN or contact mismatch (prevents MRN enumeration) and duplicate claim prevention (`409 Conflict`).
  - `PATCH /api/v1/me/`: Strictly scoped patient profile updates (phone, email, address, emergency contact) while rejecting unauthorized tampering of MRN, clinical notes, or medical history. Records `AuditEvent`.

#### B. Android Patient App (`hospital-vedant`)
- **API Client & DTOs (`com.example.network`):**
  - Updated `ApiDtos.kt` with `RequestOtpRequest`, `RequestOtpResponse`, `RegisterPatientRequest`, `ClaimPatientRequest`, and `PatientProfileUpdateDto`.
  - Added matching Retrofit endpoints to `HospitalApiService.kt`.
- **Repository & ViewModel Integration:**
  - Connected `HospitalViewModel` and `PatientRegistrationScreen` directly to `repository.registerRemotePatient()`, `repository.claimRemotePatient()`, and `repository.requestOtp()`.
  - Added full user-facing OTP dispatch, password entry, and Claim Existing Reception File UI sections.
  - Eliminated client-side random UHID generation in registration path; enforces server-issued MRN authoritative assignment.
- **Unit Tests:**
  - Added onboarding verification tests in `ApiIntegrationUnitTest.kt` (`registerRemotePatient`, `claimRemotePatient`, `requestOtp`).

---

### 2. Test Verification & Results

#### Django Backend Tests
```bash
python manage.py test core.test_patient_api
# Ran 18 tests in 11.412s -> OK

python manage.py test
# Ran 99 tests in 26.417s -> OK
```

#### Android Patient App Tests
```bash
./gradlew testDebugUnitTest assembleDebug
# BUILD SUCCESSFUL in 1m 58s (all 24 tests passed)
```

---

### 3. Branches & Git References
- **Django HMS Branch:** `task-003-patient-onboarding`
  - Push status: Up to date on `origin/task-003-patient-onboarding`
  - PR URL: `https://github.com/hospitalmanagementsystem587-gif/hospital-management-system/pull/new/task-003-patient-onboarding`
- **Android App Branch:** `task-003-patient-onboarding`
  - Push status: Up to date on `origin/task-003-patient-onboarding`
  - PR URL: `https://github.com/abhishek-sahu-ai/hospital-vedant/pull/new/task-003-patient-onboarding`
