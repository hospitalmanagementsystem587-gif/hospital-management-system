# Task 006 — Patient Health Records, Prescriptions and Documents

**Priority:** P1  
**Depends on:** Tasks 002 and 003

## Goal

Provide authenticated patients read-only mobile access to approved consultations, issued prescriptions, follow-up information, and patient documents while preserving clinical access controls and source authenticity.

## Scope

- Add ownership-scoped APIs for the authenticated patient's released/approved records, issued prescriptions and items, follow-up dates/notes approved for patient display, and permitted documents.
- Define record-release rules. Draft/cancelled prescriptions, internal notes, audit events, other doctors' restricted fields, and pharmacy-only data must not leak.
- Use existing structured `PrescriptionItem` fields. Add structured medication timing only through a reviewed model change; do not parse arbitrary text as authoritative instructions.
- Provide secure document/PDF download with authorization on every request, safe content type/disposition, size limits, malware/file validation, and non-guessable URLs.
- Prefer server-rendered or server-signed prescription PDFs based on canonical records. A mobile-generated PDF must not appear doctor-signed or authoritative.
- Update Android health-record filters, detail views, document download/share, prescription display, offline cache, and clear stale/revoked content behavior.
- Remove patient-side creation/deletion of clinical records from the production path.

## Acceptance and Tests

- A patient sees only their released records and issued prescriptions.
- Cross-patient ID guessing, document URL reuse, and revoked-access cases fail without leaking existence.
- Downloads require current authorization and use approved metadata.
- Android clearly distinguishes cached/offline copies and removes them on logout/account unlink.
- Clinical staff and pharmacy web permissions remain unchanged.
- Payloads and logs do not expose unnecessary diagnosis/clinical fields.

Create `agent-bridge/to-claude/006-health-records-prescriptions-completion.md` when complete.
