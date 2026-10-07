# Insurance, TPA and ABHA decision record

Status: integration disabled pending hospital compliance, operational-owner and vendor approval.

- Owner: hospital billing/TPA desk; clinical staff cannot alter eligibility outcomes.
- Permitted data: minimum policy/member references, effective dates, verification provenance and consent records. No patient data may be sent to a vendor without documented purpose and consent.
- Access: patients may eventually read their own policies; trained billing staff may submit corrections; only authorized staff may record external outcomes. All changes require audit events.
- Retention/encryption: card/supporting documents must use the existing private document storage controls, malware validation and authenticated streaming. They must never be Base64 database/Room fields or public media URLs. Retention periods require policy approval.
- Verification: `verified` requires an authoritative source, external reference, responsible actor and timestamp. OCR is untrusted transcription only.
- TPA claims: preauthorization and claims will be append-only workflows linked to a policy and invoice; historical outcomes cannot be overwritten.
- ABHA/ABDM: separate consent and link records only. Do not derive an ABHA address from MRN. Production exchange requires official ABDM sandbox certification, credentials, consent-manager workflow and security review.
- Release: patient upload/read APIs, vendor adapters and ABHA UI remain disabled until the above approvals and threat-model review are recorded.

## Sandbox interface plan

Provider adapters will accept opaque policy references and consent context, return a signed/correlated result, and persist raw provider identifiers only server-side. Contract tests must cover timeouts, replay/idempotency, expiry, revocation and cross-patient isolation before any adapter is enabled.
