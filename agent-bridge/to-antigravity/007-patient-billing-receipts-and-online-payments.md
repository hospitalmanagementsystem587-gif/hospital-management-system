# Task 007 — Patient Billing, Receipts and Online-Payment Readiness

**Priority:** P1  
**Depends on:** Tasks 002 and 003

## Assignment

Assigned to Antigravity after Task 004 review fixes. Start from the latest merged `main` in isolated HMS and Android worktrees on `task-007-patient-billing-payments`. Push PRs for review; do not merge. Do not begin Task 008 until Task 007 is complete and handed off.

## Goal

Expose the authoritative Django billing ledger safely to patients and prepare a real, auditable online-payment workflow without reusing the Android app's simulated settlement logic.

## Scope

- Add patient-owned read APIs for issued invoices, line-item snapshots, adjustments relevant to the patient, payments, refunds, outstanding balance, and official receipts.
- Preserve Django decimal values and historical snapshots. Serialize money as decimal strings with currency, never floating-point values.
- Add secure receipt/PDF download if approved, with ownership checks on every request.
- Update Android billing list/detail/status/receipt screens to use Django data and meaningful empty/offline states.
- Remove local `markInvoiceAsPaid`, random transaction IDs, and immediate success messages from the production path.
- Design payment initiation, idempotency key, provider order/reference, webhook verification, reconciliation, failure/pending/expiry, refund, and retry behavior.
- Implement real online payment only after the owner selects a gateway and provides sandbox credentials and approved settlement/refund policy. Until then, ship read-only billing and a clearly disabled payment action.

## Financial Safety Rules

- The mobile client never decides that an invoice is paid.
- Payment success occurs only after a verified server/provider event and transactional ledger update.
- Duplicate client requests or webhooks cannot create duplicate payments.
- Never expose gateway secrets, webhook secrets, internal approval fields, or other patients' financial data.
- Preserve the existing reception/administrator permissions and audit trail.

## Acceptance and Tests

- Patients can see only their own issued invoices and authoritative balances.
- Decimal/currency values match the Django ledger exactly.
- Tampered invoice IDs and receipt URLs fail without revealing existence.
- If a gateway is implemented, signature verification, duplicate webhook, out-of-order event, partial payment, failed payment, refund, and reconciliation tests pass.
- Android never displays paid status based solely on client state.

Create `agent-bridge/to-claude/007-patient-billing-payments-completion.md` when complete.
