# Portal engineering workflow (KAN-102)

Jira HMS/KAN tracks engineering implementation. Patient and hospital support
requests belong to the HMS `Ticket` domain and must never be copied into Jira as
operational records.

## Ticket lifecycle

1. Read the complete Jira ticket, its acceptance criteria, links, and dependency.
2. Confirm the predecessor is merged or explicitly available as the selected base.
3. Inspect the repository and run the relevant baseline tests.
4. Create one isolated branch/worktree for the ticket or ordered batch.
5. Implement only the current ticket; do not pre-build downstream models.
6. Run focused tests, regressions, system checks, and migration-drift checks.
7. Commit with the Jira key, push, and open a reviewable PR referencing that key.
8. Complete the agent completion contract and update Jira with exact evidence.
9. Mark Done only after every acceptance criterion is evidenced and the change is
   merged or the project owner explicitly accepts the delivery state.

Each ticket prompt must contain the objective, acceptance criteria, dependency,
architectural guardrails, verification commands, completion report requirements,
and the next ticket (which is guidance only, not permission to implement it).

## Safety and authority

Agents receive repository access only. Production credentials and deployments are
never embedded in prompts, files, commits, logs, or completion reports. Production
database/security mutations require explicit human authorization at execution
time and independent post-change verification.

The architectural invariants are: one Django backend and database; Django auth and
authorization remain authoritative; no Supabase Auth; no duplicate patient,
pharmacy, pricing, billing, or ticketing domain; Android API compatibility remains
a release gate.

Traceability is `KAN-NNN` in branch name, commit subject, PR title/body, tests, and
the Jira completion comment. The completion contract is defined in
`agent-bridge/COMPLETION_CONTRACT.md`.
