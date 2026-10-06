# Task 013 — Governed Health Content and Optional AI Assistance

**Priority:** P3  
**Depends on:** Task 004 and explicit clinical-governance approval

## Goal

Provide useful patient education without exposing an API key in the Android app, fabricating doctor endorsements, or publishing unreviewed generated medical advice.

## Scope

- Build a Django-managed health-content model with author/reviewer, clinical approval, version, effective/expiry dates, audience, language, references, publication status, and emergency disclaimer.
- Serve only published, in-date content to Android with cache metadata and offline fallback.
- Migrate only content that has been reviewed and approved. Remove fabricated statistics, doctor attribution, accreditations, and promotional claims.
- If AI assistance is approved, run it server-side for draft creation only. Store prompt/model/version/provenance as appropriate, require human clinical review, and prohibit automatic publication.
- Never send patient clinical data to an AI provider in this task.
- Keep provider keys server-side and out of URLs, mobile BuildConfig, logs, error messages, and source control.
- Update Android daily-tip UI to show source, review date, non-emergency disclaimer, and safe error/offline behavior.

## Acceptance and Tests

- Unapproved, expired, or superseded content cannot be returned by the patient API.
- Publication requires the designated permission and records reviewer/version metadata.
- Android cannot call the generation provider directly and contains no provider secret.
- Generated drafts cannot appear publicly without clinical approval.
- Emergency symptoms are directed to emergency services rather than personalized advice.

Create `agent-bridge/to-claude/013-health-content-ai-governance-completion.md` when complete.
