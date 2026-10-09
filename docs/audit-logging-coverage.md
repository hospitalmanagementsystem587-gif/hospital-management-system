# Audit logging coverage (KAN-101)

`AuditEvent` is the shared append-only application audit record. Ticket history
uses the narrower append-only `TicketAuditEvent`. Neither log stores passwords,
tokens, database credentials, document contents, or full clinical narratives.

| Domain | Critical audited actions | Evidence |
| --- | --- | --- |
| Administration/content | publish, activate/deactivate, profile changes | `core/admin.py`, publishing tests |
| Clinical | patient changes, appointment lifecycle, consultation/document access | `core/views.py`, clinical workspace tests |
| Pharmacy | catalog/supplier changes, receiving, dispensing, sales, returns, adjustments | pharmacy workspace tests |
| Billing/pricing | approval, discount, payment, refund, adjustment, invoice snapshot | pricing and financial tests |
| Support | assignment, status, SLA, message/attachment changes | immutable `TicketAuditEvent` and ticket tests |
| Security | permission/RLS review evidence | deployment records and security tests |

Every event records an actor when an authenticated staff actor exists, an action,
the target type/id, a timestamp, and a deliberately bounded JSON context. Before
and after values are recorded only where operationally necessary. Audit rows are
not registered for ordinary Django admin mutation, and model-level update/delete
operations are rejected.

Database operators retain emergency access for backup, recovery, and legally
approved retention operations. Such access must be handled through the production
change-management process rather than application code.
