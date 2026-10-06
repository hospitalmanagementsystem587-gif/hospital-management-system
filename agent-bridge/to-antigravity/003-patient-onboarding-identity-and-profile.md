# Task 003 — Production Patient Onboarding, Identity and Profile

**Priority:** P0  
**Depends on:** Task 002  
**Repositories:** Django HMS and Android patient app

## Goal

Replace development-only patient account provisioning with a production-ready onboarding, identity-verification, account-recovery, and limited profile workflow. A mobile account must be linked safely to exactly one canonical Django `Patient` record.

## Scope

- Define and document the approved onboarding route: existing-patient claim, new-patient pre-registration, or both.
- Implement verified phone/email ownership using a real provider abstraction. Keep provider credentials server-side. If no provider is selected, implement interfaces and test fakes but do not claim production verification.
- Prevent duplicate account-to-patient links. Use controlled matching and staff review for ambiguous matches; never auto-merge patients.
- Add resend limits, expiry, attempt limits, lockout/throttling, recovery, logout-all-devices, and session revocation.
- Expose minimal authenticated profile data through `/api/v1/me/` and an approved limited update endpoint for contact/demographic corrections.
- Treat changes as requests or audited corrections according to existing patient-record policy. Do not allow MRN, safety notes, clinical data, verification state, or archived state to be edited by the patient.
- Update Android onboarding, verification, recovery, profile, error, and pending-review states.
- Remove random local UHID creation from the production path. Django `NumberSequence` remains the only patient-ID issuer.

## Security and Privacy Requirements

- Do not reveal whether a phone/email/MRN exists through different public responses.
- Never use date of birth, phone, or MRN alone as authentication.
- Store verification challenges hashed where appropriate; never log codes.
- Add consent/notice text and record the version accepted, without claiming legal compliance that has not been reviewed.
- Protect against enumeration, replay, brute force, duplicate submission, and link hijacking.

## Acceptance and Tests

- Verified existing-patient linking succeeds only with the approved factors.
- Ambiguous/no-match flows remain pending or require staff resolution.
- One user cannot claim another patient, and one patient cannot acquire conflicting active accounts.
- OTP/challenge expiry, replay, throttling, recovery, and revocation are tested.
- Patient-editable fields are explicitly allow-listed and audited.
- Android survives process restart and token expiry without losing a valid onboarding state.
- Existing staff authentication and patient registration workflows remain unaffected.

Create `agent-bridge/to-claude/003-patient-onboarding-identity-completion.md` when complete.
