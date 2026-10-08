# Antigravity Prompt — KAN-36 Shared Authentication & Session Layer

Implement **only Jira KAN-36**. Do not begin KAN-37 or any later ticket.

## Start gate

- Read KAN-36 completely in Jira, including current comments and links.
- Confirm KAN-35 is Done and its accepted commit is present in your clean base.
- The prepared KAN-35 commit is `09d0f26195012befb393233e33001ea726e4efd3` on `codex/kan-35-portal-architecture`; verify whether it has been merged before branching.
- If KAN-35 is absent, stop and report the integration blocker. Do not recreate or broaden KAN-35.

## Required audit before changes

Inspect `config/settings.py`, every portal URLconf, portal middleware, Django auth URLs/views/templates, User/PatientAccount/StaffProfile, groups and permissions, login throttling, session and cookie settings, CSRF/trusted origins, JWT/SimpleJWT configuration, Android API auth tests, deployment docs, and existing tests. Record current behavior before editing.

## Scope

Implement the shared Django authentication/session foundation for admin, staff,
store, patient, and agent hosts. Keep Django as the identity authority. Define
secure, explicit login, logout, session expiry, cookie-domain, CSRF, redirect,
and portal-context behavior. Preserve existing server-rendered authentication
and Android JWT behavior.

Do not implement KAN-37's full authorization matrix. Do not add Supabase Auth,
a parallel identity service, duplicate users, portal-specific databases, social
login, passwordless flows, or UI redesign.

## Required tests

Cover anonymous access, login success/failure, safe `next` handling, logout,
session expiry, inactive users, cross-host session behavior according to the
documented policy, CSRF/cookie security settings, portal context preservation,
and unchanged JWT token/refresh/logout behavior. Run the full Django suite and
migration-drift check.

## Completion contract

Commit and push a KAN-36 branch. Update only KAN-36 with summary, files,
migrations, auth/API impact, exact tests/results, security decisions, risks, and
commit/PR. Mark Done only if every acceptance criterion passes. State that
KAN-37 is next, but do not implement it.

