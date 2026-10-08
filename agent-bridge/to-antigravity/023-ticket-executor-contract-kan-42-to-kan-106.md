# Antigravity Ticket Executor Contract — KAN-42 to KAN-106

Every ticket prompt in the phase queues incorporates this contract.

## Invocation

When dispatched a ticket, execute **only that Jira key**. Read the issue's full
description, acceptance criteria, comments, links, parent, and dependencies from
Jira at execution time. Jira is the live scope authority; the phase queue adds
guards but never replaces the issue.

## Hard dependency gate

Confirm every declared predecessor is Done and its accepted commit is integrated
into a clean base. If not, report the ticket as blocked and stop. Never implement
a predecessor, successor, or adjacent cleanup ticket in the same run.

## Required workflow

1. Inspect repository status and preserve unrelated work.
2. Create/use a clean ticket-specific branch; never build from the dirty shared `main` worktree.
3. Audit relevant models, migrations, services, views, APIs, authorization, templates, tests, docs, admin, and agent-bridge history before editing.
4. Record compatibility constraints and reuse existing domain models/business logic.
5. Implement the smallest production-ready change satisfying only the current ticket.
6. Enforce authorization server-side and ownership/object access where applicable.
7. Add focused positive, negative, validation, and regression tests.
8. Run Django checks, migration-drift checks, focused tests, and the relevant full suite. Run frontend/build/browser checks when UI changes.
9. Review the final diff for scope creep, secrets, unsafe migrations, data leakage, and unrelated files.
10. Commit and push the ticket branch.
11. Update only the active Jira issue with summary, files, migrations, API impact, tests/results, security, risks, and commit/PR.
12. Mark Done only when every acceptance criterion is proven. Name the next unblocked ticket but do not start it.

## Architecture constraints

- One Django monolith and one PostgreSQL/Supabase database remain authoritative.
- Keep Django auth/sessions/groups/permissions; never introduce Supabase Auth.
- Preserve Android `/api/v1/` behavior unless the active ticket explicitly changes a versioned contract.
- Do not duplicate patient, clinical, billing, pharmacy, CMS, pricing, or ticketing models per portal.
- Prefer additive, reversible migrations; preserve historical records and foreign keys.
- Never treat hidden navigation as authorization.
- Never expose patient/clinical/document/billing data across owners or roles.
- Do not redesign unrelated CMS or portal surfaces.

## Completion artifact

Write `agent-bridge/to-claude/<ticket-key-lower>-completion.md` and update Jira.
The report must be evidence-based and include exact commands and pass/fail counts.

