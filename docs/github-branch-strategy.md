# GitHub branch strategy (KAN-103)

## Branches and pull requests

- Default branch: `main`; keep it releasable and never rewrite its history.
- One ticket: `codex/kan-<number>-<short-scope>` (or the executing agent's agreed
  prefix).
- Ordered batch: `codex/batch-kan-<first>-to-kan-<last>`, with exactly one
  independently reviewable commit per completed ticket.
- PR title: `KAN-<number>: <ticket summary>` or
  `KAN-<first>–KAN-<last>: <ordered batch summary>`.
- PR body lists each Jira key, acceptance evidence, migrations, tests, security
  impact, risks, and follow-ups.

Domain labels such as portal-foundation, admin-cms, pricing-engine, staff-portal,
store-portal, patient-portal, and ticketing belong in the short scope or PR labels;
they do not permit bypassing Jira dependency order.

## Review and merge

Use a normal merge or fast-forward that preserves ticket commits for ordered
batches. Require green focused/regression tests, `manage.py check`, migration-drift
check, and review of authorization/data isolation changes. Never force-push a
reviewed shared branch or rewrite merged history.

## Shared models and migrations

Only one active ticket owns a shared model or migration chain at a time. Before
creating a migration, fetch the latest base and inspect leaf migrations. If two
branches create siblings, stop and rebase/merge the predecessor, regenerate the
later migration, and rerun the full migration/test suite. Do not hand-edit
dependency numbers to hide conflicts. Cross-domain changes must identify every
consumer and include regression tests.

Parallel work is allowed only for genuinely independent documentation, review, or
test analysis that does not mutate the same code/schema path. Dependencies remain
the source of truth.
