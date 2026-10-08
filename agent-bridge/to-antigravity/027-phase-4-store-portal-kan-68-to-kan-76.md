# Antigravity Prompt Queue — Phase 4 Store Portal (KAN-68–KAN-76)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-68 — Pharmacy Dashboard

After its Jira predecessors, build a permission-scoped operational dashboard from
existing pharmacy data. Test role denial, accurate aggregates and empty states.

## KAN-69 — Medicine Catalog

Manage the existing Medicine source of truth; enforce code/name validation,
activation and safe references. Preserve prescriptions and Android consumers.

## KAN-70 — Inventory and Batch Management

Expose batch/stock worklists over existing ledgers. Preserve transaction safety,
expiry/quarantine semantics and immutable movement history. Test concurrency.

## KAN-71 — Supplier Management

Implement authorized Supplier CRUD/deactivation with validation and referenced
receipt safety. Do not implement receiving.

## KAN-72 — Stock Receiving

Implement GRN/receipt workflows using existing StockReceipt, batches and stock
movements. Test atomicity, duplicate submissions and audit trails.

## KAN-73 — Dispensing Queue

Implement store-only prescription dispensing queues and transactions. Test
eligibility, partial/full rules, stock locks, duplicate dispensing and permissions.

## KAN-74 — Pharmacy Sales

Implement counter sales over existing sale/line/stock/payment models. Test price
snapshots, inventory atomicity, permissions and receipt behavior.

## KAN-75 — Pharmacy Returns

Implement validated returns against original sales/dispensing as Jira specifies.
Test quantities, refund/stock effects, rejection and auditability.

## KAN-76 — Stock Adjustment and Quarantine

Implement privileged adjustments and quarantine/unquarantine with reasons,
movement ledger integrity and audit trails. Test forbidden and concurrent actions.

