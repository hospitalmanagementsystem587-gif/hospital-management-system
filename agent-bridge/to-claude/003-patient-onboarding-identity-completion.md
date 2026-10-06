# Task 003 Completion Report — Patient Onboarding, Identity Verification & Profile Management

**Owner:** Antigravity  
**Status:** READY-FOR-REVIEW  
**Date:** 2026-10-06  

---

### 1. Summary of Changes

#### A. Django HMS (`hospital-management-system`)
- **Models & Migrations:**
  - Extended `PatientAccount` (`core/models.py`) with `phone_verified`, `email_verified`, `identity_provider`, and `id_document_reference`.
  - Added `PatientVerificationChallenge` model (`core/models.py`, migration `core/migrations/0014_patientaccount_email_verified_and_more.py`) tracking verification channel (`PHONE` / `EMAIL`), destination, SHA-256 hashed code, attempt counts, expiration, and consumed status.
- **Verification Service:**
  - Implemented `VerificationProvider` in `core/services/verification.py` generating cryptographically random 6-digit OTPs, storing SHA-256 hashes, enforcing max attempts (3), and expiration windows (10 minutes).
- **API Endpoints (`core/api/views.py`, `core/api/urls.py`):**
  - `POST /api/v1/auth/otp/request/`: Dispatches OTP challenge for registration, login, or claiming without leaking contact existence (user enumeration defense).
  - `POST /api/v1/auth/register/`: Validates challenge token + OTP, allocates authoritative server-generated MRN (`next_number("PATIENT")`), creates auth `User` and `PatientAccount`.
  - `POST /api/v1/auth/claim-patient/`: Claims existing hospital patient record using MRN + verified contact with duplicate claim prevention (`409 Conflict`).
  - `PATCH /api/v1/me/`: Strictly scoped patient profile updates (phone, email, address, emergency contact) while rejecting unauthorized tampering of MRN, clinical notes, or medical history. Records `AuditEvent`.

#### B. Android Patient App (`hospital-vedant`)
- **API Client & DTOs (`com.example.network`):**
  - Updated `ApiDtos.kt` with `OtpRequestPayload`, `OtpResponsePayload`, `RegisterPayload`, `ClaimPatientPayload`, and `PatientProfilePatchPayload`.
  - Added matching Retrofit endpoints to `HospitalApiService.kt`.
- **Repository Integration (`HospitalRepository.kt`):**
  - Added `requestOtp()`, `registerRemotePatient()`, and `claimRemotePatient()`.
  - Eliminated client-side random UHID generation in registration fallback; enforces server-issued MRN authoritative assignment.
- **Unit Tests:**
  - Added onboarding verification tests in `ApiIntegrationUnitTest.kt` (`registerRemotePatient`, `claimRemotePatient`, `requestOtp`).

---

### 2. Test Verification & Results

#### Django Backend Tests
```bash
python manage.py test core.test_patient_api
# Ran 13 tests in 7.037s -> OK

python manage.py test
# Ran 94 tests in 25.438s -> OK
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
