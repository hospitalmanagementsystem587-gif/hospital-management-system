# HMS implementation-agent completion contract (KAN-104)

An implementation ticket is complete only when the agent reports all sections
below with verifiable evidence. Unknown or unperformed items must say so explicitly.

1. **Scope and acceptance criteria** — implemented ticket, dependency/base, and an
   acceptance-criterion mapping. Record scope creep as follow-up work; do not
   silently implement another ticket.
2. **Changed files** — every production, test, documentation, configuration, and
   generated file with its purpose.
3. **Data and migrations** — migration names, SQL, rollback/operational steps, or
   `none`; include migration-drift result.
4. **API/compatibility** — routes, payloads, status codes, compatibility impact,
   and Android patient API result, or `none`.
5. **Tests and results** — exact commands, counts, failures/skips, system check,
   and relevant regressions. Never describe an unrun test as passing.
6. **Security and privacy** — authentication, authorization, object isolation,
   CSRF/session, audit, secrets, RLS, and sensitive-data considerations.
7. **Limitations and risks** — remaining blockers, assumptions, manual validation,
   production rollout/rollback needs, and required follow-up Jira tickets.
8. **Delivery** — branch, full commit SHA, PR URL/status, merge status, and clean
   working-tree confirmation.
9. **Next ticket** — identify the next unblocked Jira ticket without implementing it.

## Non-negotiable guardrails

- Use the existing Django backend, database, authentication, authorization, and
  business models.
- Do not introduce Supabase Auth, another patient database, another pharmacy
  backend, duplicate ledgers, or authorization bypasses.
- Do not expose secrets or grant an agent autonomous production access.
- Keep hospital operational support tickets in the HMS ticketing domain; Jira is
  for engineering work.
- Do not break the Android patient API.
- Do not mark Jira Done when evidence or an acceptance criterion is missing.

Copy this contract into every task prompt and completion report by reference.
