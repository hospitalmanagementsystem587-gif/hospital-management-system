# Antigravity Prompt — KAN-39 Admin Management Dashboard

Implement **only Jira KAN-39**. Do not begin the hospital profile CMS.

## Start gate

Read KAN-39 completely and confirm KAN-38 is Done and integrated. Use the shared
design system; do not create a dashboard-only visual framework.

## Required audit before changes

Inspect the admin portal boundary, existing admin authorization, models and
status enums for patients, appointments, billing, pharmacy, IPD, and any current
support data. Audit existing query helpers and indexes before adding aggregates.

## Scope

Create an authorized management dashboard using live, existing HMS data. Show
only meaningful aggregate operational summaries supported by current models.
Keep queries efficient and privacy-minimizing; do not expose unnecessary patient
details or create duplicate reporting tables/business logic. Handle loading,
empty, error, and responsive states with KAN-38 components.

Do not implement profile editing, departments, specialties, pricing, ticketing,
or unrelated CMS screens.

## Verification and completion

Test unauthorized access, representative aggregates, empty data, query behavior,
and permission-scoped sensitive content. Run the full relevant suite and
migration check. Commit/push KAN-39, update only KAN-39, and identify KAN-40
without starting it.

