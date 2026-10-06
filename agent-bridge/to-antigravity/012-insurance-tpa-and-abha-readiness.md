# Task 012 — Insurance/TPA and ABHA Readiness

**Priority:** P3  
**Depends on:** Tasks 003, 006 and 007; Task 014 baseline security controls; explicit policy/compliance/vendor approval. Re-run the final Task 014 release gate afterward.

## Goal

Replace the prototype's simulated insurance and ABHA states with a secure, auditable domain model and an approval-gated integration plan. Do not claim live verification until an authorized external response exists.

## Scope

- First produce a decision record covering operational owner, permitted data, consent, retention, encryption, access roles, verification source, TPA workflow, document storage, and official ABDM integration requirements.
- Model insurance as separate entities such as policy/coverage, member, provider/TPA, verification attempt/result, pre-authorization/claim, and supporting documents. Do not place one provider/policy directly on `Patient`.
- Support multiple policies, effective dates, status history, audit trail, and controlled correction without overwriting historical claims.
- Add staff workflows and patient read/upload APIs only after authorization rules are approved.
- Use secure file storage; never store insurance-card images as Base64 blobs in Room or ordinary database text.
- Implement OCR only as an untrusted extraction aid requiring user/staff confirmation.
- Treat ABHA identifiers, linking, consent artefacts, and health-information exchange as a distinct official ABDM integration. Do not derive an ABHA address from the hospital MRN.
- Remove `ABHA Active`, automatic `VERIFIED`, fake policy numbers, fake eligibility, and simulated check-in from production Android UI.

## Acceptance and Tests

- No verification/eligibility status is possible without a recorded authoritative source and actor.
- Multiple-policy, expiry, revocation, document access, cross-patient isolation, and audit tests pass.
- Sensitive files are encrypted/access-controlled and removed from device cache on logout/revocation.
- If official integration credentials/approval are unavailable, deliver the model, decision record, interfaces, sandbox plan, and disabled UI state—not a fake integration.

Create `agent-bridge/to-claude/012-insurance-abha-readiness-completion.md` when complete.
