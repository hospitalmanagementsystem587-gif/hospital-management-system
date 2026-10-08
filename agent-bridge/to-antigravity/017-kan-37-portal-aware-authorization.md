# Antigravity Prompt — KAN-37 Portal-Aware Authorization

Implement **only Jira KAN-37**. Do not begin KAN-38 or later work.

## Start gate

Read KAN-37 completely and confirm KAN-36 is Done and integrated into a clean
base. If authentication/session behavior is unfinished or inconsistent, report
the blocker instead of absorbing KAN-36 into this ticket.

## Required audit before changes

Inspect portal middleware/URLconfs, Django User, groups, permissions,
StaffProfile, PatientAccount, decorators/mixins, `core/authorization.py`, admin
authorization, every sensitive HTML view, DRF permission classes, queryset
ownership filters, object download endpoints, and existing positive/negative
security tests. Build a route/resource/role matrix before changing code.

## Scope

Create a reusable server-side portal-aware authorization layer for admin,
staff, store, patient, and agent contexts. Reuse existing permissions and domain
ownership relationships. Enforce both route-level and object-level access for
patient, clinical, pharmacy, billing, document, and support data. Direct URLs
and API calls must fail safely; navigation hiding is never authorization.

Do not redesign UI, create ticketing features, change pricing, duplicate domain
models, or break the Android API. Agent access must fail closed wherever a
dedicated role/domain rule does not yet exist.

## Required tests

Include anonymous, ordinary user, each staff group, administrator, pure patient,
dual-role, inactive/unverified/archived patient, cross-patient access, cross-role
access, direct URL, document/download, and API ownership cases. Assert both
allowed and denied behavior without leaking object existence. Run the full
Django suite and migration-drift check.

## Completion contract

Commit/push a KAN-37 branch and update only KAN-37 with evidence. Mark Done only
after all criteria pass. Identify KAN-38 as next; do not implement it.

