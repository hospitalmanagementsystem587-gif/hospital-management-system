# Jules suggestions: HMS review and implementation

Source: the 21 recommendations shown in Jules for
`hospitalmanagementsystem587-gif/hospital-management-system` on 2026-10-10.
They reference old commit `efcb794`; inspect the current branch before changing code.

Work on this branch only. Complete the groups sequentially with one commit per
verified, independent change. Add a regression test for each behavior change and
measure query reductions where relevant. Run focused tests after each commit and
the full Django suite, `python manage.py check`,
`python manage.py makemigrations --check --dry-run`, `ruff check .`, and
`ruff format --check .` before opening one PR. Preserve Django permissions,
patient isolation, the shared PostgreSQL/Supabase backend, and the Android API.
Do not merge or deploy.

## Performance (4 recommendations)

- [ ] `pharmacy_sale_detail`: aggregate returned quantity once rather than
  querying inside the sale-line loop; test totals and bounded query count.
- [ ] `invoice_detail`: compute pending pharmacy-return refund totals without
  an aggregate query per return; test totals and bounded query count.
- [ ] `invoice_list`: compute invoice balances without three aggregate queries
  per invoice; test payment/refund cases and bounded query count.
- [ ] `pharmacy_prescriptions`: check nested dispensing-line, batch, and
  return-line queries; improve only after measuring a reproducible N+1 pattern.

## Authorization (3 recommendations)

- [ ] `patient_update`: verify the suggested missing decorator. Current `main`
  already has `@permission_required("core.change_patient", raise_exception=True)`;
  record as stale if the branch still has it. Do not add a duplicate decorator.
- [ ] `patient_create`: verify the suggested missing decorator. Current `main`
  already has `@permission_required("core.add_patient", raise_exception=True)`;
  record as stale if the branch still has it.
- [ ] `invoice_detail`: check whether its manual Reception/Administrator and
  StaffProfile gate also needs `core.view_invoice` permission. Add the decorator
  only if a failing authorization test demonstrates a gap; preserve intended
  access for existing roles.

## Test coverage (5 recommendations)

- [ ] `appointment_slot_conflicts` form validation: add meaningful boundary
  and conflicting-slot cases if not already covered.
- [ ] `PatientForm.clean_date_of_birth`: add invalid, future, and boundary
  cases that reflect current business rules.
- [ ] `next_number`: add deterministic sequence/error cases without relying on
  production database state.
- [ ] `invoice_adjustment`: add rejected-input and authorization error cases.
- [ ] `configure_role_permissions`: test idempotence and actual permission
  mapping rather than simply calling it during fixture setup.

## Code health (9 recommendations, likely fewer distinct fixes)

- [ ] Seven “Code Duplication: Permission Check” suggestions point to old
  `core/views.py` lines 822, 778, 704, 644, 332, 304, and 248. Treat the first
  five as one possible duplication cluster and the last two as another. Review
  current code and tests. Refactor only where a shared helper preserves role,
  StaffProfile, object-level, and exception semantics; otherwise document why
  no change is safe. Do not create seven near-identical fixes.
- [ ] `dispense_prescription`: review complexity and split only a cohesive
  unit with tests that protect stock and invoice atomicity.
- [ ] `pharmacy_return_create`: review complexity and split only a cohesive
  unit with tests that protect return, refund, and stock transitions.

For every checkbox, record `implemented`, `already fixed`, `duplicate`, or
`not reproducible`, with the current evidence. The goal is to resolve all 21
recommendations, not to force 21 code changes.
