# Antigravity Prompt — KAN-41 Department Management

Implement **only Jira KAN-41**. Do not implement Specialty.

## Start gate

Read KAN-41 completely and confirm KAN-40 is Done and integrated.

## Required audit before changes

Inspect Department fields/constraints, StaffProfile relationships, appointment
and directory consumers, admin/API/templates/forms, public visibility behavior,
ordering, deletion/deactivation semantics, and existing test fixtures.

## Scope

Turn the existing Department master data into an administrator-only CMS. Reuse
the model; add only fields truly missing from the acceptance criteria. Support
create/edit, safe activate/deactivate, and ordering. Preserve codes, historical
foreign keys, staff assignments, appointments, APIs, and Android behavior.
Prevent duplicates according to explicit normalized rules. Prefer deactivation
over destructive deletion when referenced.

Do not create Specialty or doctor-specialty relationships in this ticket.

## Verification and completion

Test permissions, create/edit, duplicate validation, ordering, active/inactive
behavior, referenced departments, public/API filtering, and regression behavior.
Run full tests and migration checks. Commit/push KAN-41, update only KAN-41,
then report KAN-42 as unblocked without implementing it.

