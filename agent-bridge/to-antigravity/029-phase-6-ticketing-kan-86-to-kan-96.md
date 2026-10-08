# Antigravity Prompt Queue — Phase 6 Ticketing / Agent (KAN-86–KAN-96)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-86 — Core Ticket Domain Model

Design the single ticket source of truth with Jira-defined statuses, categories,
requester/context, priority and lifecycle. Add safe constraints/indexes and tests.
Do not add messages or assignments.

## KAN-87 — Ticket Messages

Add ordered, author-attributed messages with visibility rules and immutable audit
semantics. Test patient/internal visibility and cross-ticket access.

## KAN-88 — Ticket Attachments

Add private, scanned, size/type-limited attachments bound to authorized messages
or tickets. Test non-disclosure, malware states and ownership.

## KAN-89 — Assignment Engine

Implement explicit, auditable assignment/reassignment using existing users/roles.
Test eligible assignees, queues, concurrency and unauthorized assignment.

## KAN-90 — SLA Engine

Implement deterministic SLA clocks, pauses, breach state and timezone/business
rules exactly from Jira. Test boundary times and transitions; avoid background
infrastructure not approved by the ticket.

## KAN-91 — Patient Ticket Creation

Add owner-scoped patient creation/view flows over the shared ticket domain. Test
categories, sensitive context, attachments and cross-patient isolation.

## KAN-92 — Agent Queue

Build the authorized agent workspace for triage, assignment and responses. Use
shared components and test queue visibility, actions and direct URL denial.

## KAN-93 — Staff Ticket Integration

Integrate staff workflows with tickets without duplicating the domain. Test role
visibility, context links and sensitive clinical data minimization.

## KAN-94 — Pharmacy Ticket Integration

Integrate pharmacy/store workflows with tickets and restrict inventory/patient
context to authorized pharmacy users. Test cross-role denial.

## KAN-95 — Billing Ticket Integration

Integrate billing workflows while minimizing financial disclosure and preserving
invoice/payment authority. Test permissions and object ownership.

## KAN-96 — Ticket Audit History

Provide immutable, permission-scoped lifecycle history covering messages,
assignments, SLA and integrations. Test tamper resistance and sensitive fields.

