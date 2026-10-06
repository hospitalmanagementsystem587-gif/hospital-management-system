# Task 008 — Medication Schedules, Reminders and Adherence

**Priority:** P1  
**Depends on:** Task 006

## Assignment

Assigned to Antigravity second in the queue, after Task 007. Start from the latest merged `main` in isolated HMS and Android worktrees on `task-008-medication-reminders`. Push PRs for review; do not merge. Preserve Task 006 prescription authority and never derive authoritative schedules from unstructured text.

## Goal

Turn issued prescriptions into clinically reviewed medication schedules that can drive reliable Android reminders and optional patient-reported adherence without changing the prescription itself.

## Scope

- Define a structured schedule model linked to an issued `PrescriptionItem`: dose amount/unit, local times or recurrence, meal relation, start/end dates, timezone, active state, and who confirmed it.
- Require doctor/pharmacist confirmation for structured timings. Do not infer an authoritative schedule from free-text frequency or instructions.
- Add patient-owned APIs for active schedules and optional dose-event sync.
- Keep the prescription immutable; schedule corrections must be versioned/audited and must not rewrite clinical history.
- Implement Android scheduling with WorkManager/AlarmManager as appropriate, reboot/timezone/time-change recovery, permission handling, snooze/skip/taken actions, and clear expired/discontinued behavior.
- Store device reminders locally for reliability. Sync adherence only with explicit policy/consent and make clear that it is patient-reported, not proof of ingestion.
- Remove the prototype's immediate "dose confirmed" notification as a substitute for an actual scheduled reminder.

## Safety Requirements

- Never create or change a dose schedule solely from AI, string parsing, or patient edits.
- Avoid medical claims based on adherence percentages.
- Do not expose one patient's medication names on another account, notifications, logs, or lock-screen text beyond the approved privacy setting.
- Define behavior for prescription cancellation, medicine substitution, schedule revision, logout, device replacement, and missed sync.

## Acceptance and Tests

- Only active, confirmed schedules generate reminders.
- Duplicate sync does not create duplicate alarms or dose events.
- Reboot, timezone change, daylight/clock change, permission denial, logout, and prescription cancellation are tested.
- Cross-patient schedule access is rejected.
- Android and Django agree on schedule version and dose-event idempotency.

Create `agent-bridge/to-claude/008-medication-reminders-adherence-completion.md` when complete.
