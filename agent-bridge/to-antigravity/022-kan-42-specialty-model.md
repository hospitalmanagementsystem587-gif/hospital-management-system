# Antigravity Prompt — KAN-42 Specialty Model

Implement **only Jira KAN-42**. Do not begin Doctor Management or KAN-43.

## Hard start gate

Read KAN-42 completely. Confirm KAN-36, KAN-37, KAN-38, KAN-39, KAN-40, and
KAN-41 are all Done and their accepted commits are integrated into the clean
working base. Jira declares KAN-41 as KAN-42's direct predecessor. If KAN-41 is
not complete, stop and report KAN-42 as blocked—do not implement around it.

## Required audit before changes

Inspect Department, StaffProfile, doctor directory serializers/views/templates,
public visibility conventions, code/name normalization, display ordering,
admin/CMS patterns established by KAN-40/41, database constraints/indexes,
migration numbering, fixtures, and Android API contracts.

## Scope

Introduce a first-class Specialty domain model because Department and Specialty
represent different concepts. Include code, name, description, display order,
active state, and public state as required by Jira. Enforce normalized
uniqueness and validation at appropriate application/database layers. Add useful
ordering/indexes without speculative complexity. Preserve every Department row
and relationship.

Expose Specialty through the administrator CMS and only the minimal API/public
surface explicitly required by KAN-42. Design the model so KAN-44 can later add
doctor-specialty relationships, but do **not** add that relationship now. Do not
modify doctor management, scheduling, pricing, or public directory UI beyond the
current ticket.

## Required tests

Cover migration creation/application, model constraints and normalization,
ordering, active/public flags, admin authorization, unauthorized direct access,
Department non-regression, and unchanged existing Android/API behavior. Run:

- Django system checks;
- `makemigrations --check --dry-run` after committing the intended migration;
- focused Specialty tests;
- the full Django suite.

## Completion contract

Commit and push a KAN-42-specific branch. Update only KAN-42 with implementation
summary, every changed file, migration name/behavior, API impact, exact tests and
results, security controls, limitations, and commit/PR. Mark Done only if every
acceptance criterion passes. Identify KAN-43 as next, but do not implement it.

