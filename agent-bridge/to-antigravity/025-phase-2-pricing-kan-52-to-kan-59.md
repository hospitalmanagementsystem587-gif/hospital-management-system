# Antigravity Prompt Queue — Phase 2 Pricing (KAN-52–KAN-59)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-52 — Canonical Pricing Architecture

After KAN-51, define the single pricing source of truth by auditing every current
charge and invoice path. Establish domain boundaries and migration strategy;
avoid premature UI and do not implement later price types. Prove existing billing
and Android behavior remains compatible.

## KAN-53 — Price Versions and Effective Dates

After KAN-52, implement immutable/effective-dated versions with deterministic
selection, non-overlap rules, timezone policy and auditability. Test boundary
dates, future versions, gaps and concurrency. Do not assign all domain prices yet.

## KAN-54 — Consultation Pricing

After KAN-53, connect doctor/visit consultation charges to canonical pricing.
Preserve historical appointments/invoices and test effective-date resolution,
permissions and fallbacks. Do not implement generic service pricing.

## KAN-55 — Service Pricing

After KAN-54, connect existing Service records to canonical versions. Test active
services, dates, authorization and historical consumers. Do not include diagnostics.

## KAN-56 — Diagnostic Test Pricing

After KAN-55, connect the KAN-47 diagnostic domain to canonical pricing. Test
effective values, inactive tests and historical safety. Do not implement IPD rates.

## KAN-57 — IPD/Ward Pricing

After KAN-56, model Jira-required ward/bed/IPD rates without rewriting admission
or deposit ledgers. Test stay/date calculations, inactive resources and historical
records. Do not implement approvals.

## KAN-58 — Price Approval and Audit

After KAN-57, add server-side approval permissions, state transitions and durable
audit history for prices. Test self-approval restrictions if Jira requires them,
invalid transitions and immutable approved history. Do not alter invoice snapshots.

## KAN-59 — Invoice Price Snapshots

After KAN-58, ensure invoices persist authoritative point-in-time prices and never
recalculate historical charges from current catalogs. Test all priced domains,
adjustments and regression paths. Do not start Staff Portal work.

