# Task 009 — Verified Feedback, Ratings and Satisfaction Reporting

**Priority:** P2  
**Depends on:** Tasks 002 and 003

## Goal

Replace static reviews and calculated satisfaction graphics with verified, moderated feedback tied to real completed care events.

## Scope

- Add a feedback model linked to the patient and a completed appointment/encounter, with category, rating, optional comment, submitted time, moderation/publication status, and audit metadata.
- Enforce one active response per eligible appointment, with a documented edit/withdrawal window.
- Add patient endpoints for eligibility, submission, viewing the patient's own submission, and withdrawal where permitted.
- Add staff moderation/reporting with minimum necessary access, reasoned moderation actions, and protection against retaliation or inappropriate clinical disclosure.
- Update Android feedback form, eligibility states, success/error states, and the patient's own history.
- Public doctor ratings, if approved, must be computed from published eligible feedback with minimum sample thresholds and clear counts. Do not use the Android hardcoded doctor ratings or formula-generated sub-scores.

## Privacy and Abuse Controls

- Avoid publishing patient identity by default.
- Detect/rate-limit spam and prohibit HTML/script injection.
- Do not allow feedback to expose clinical details publicly without review.
- Define retention, moderation visibility, appeals/withdrawal, and staff access before launch.

## Acceptance and Tests

- Only the patient who completed the appointment can submit feedback.
- Ineligible, duplicate, cross-patient, and non-completed submissions are rejected.
- Moderation and publication permissions are tested and audited.
- Aggregate ratings exclude unpublished/withdrawn feedback and respect minimum sample rules.
- Android no longer presents seeded reviews as genuine patient feedback.

Create `agent-bridge/to-claude/009-feedback-ratings-completion.md` when complete.
