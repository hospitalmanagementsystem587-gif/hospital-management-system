# Task 010 — Facilities, Aggregate Bed Availability and Health Packages

**Priority:** P2  
**Depends on:** Tasks 002 and 004

## Goal

Serve accurate facility information, privacy-safe aggregate bed availability, and approved health-package/service offerings to web and mobile.

## Scope

- Reuse Django `Ward`, `Bed`, and `Admission` status as the authority for operational capacity.
- Add a public/patient read API that returns aggregate counts by approved ward category only. Never return bed occupant, patient, admission, room-level sensitive detail, or staff notes.
- Define freshness timestamp, cache policy, maintenance/blocked beds, stale-data behavior, and wording that availability is indicative until admission confirms allocation.
- Update Android facility/bed screens to remove hardcoded totals and show API freshness, unavailable/stale state, and emergency/reception contact.
- Model health packages only if the hospital approves real package names, included services, price snapshots, eligibility, validity, fasting instructions, and active dates. Do not treat a loose list of tests as a billable package without a server model.
- Integrate approved packages with the existing Service/billing catalogue and appointment request flow without bypassing financial rules.

## Acceptance and Tests

- Aggregate availability matches transactional Bed status and excludes occupied/maintenance/blocked inventory correctly.
- Concurrent admission/discharge changes cannot produce impossible counts.
- API payloads contain no occupant or admission identifiers.
- Android does not claim guaranteed availability and handles stale/offline data.
- Package pricing uses decimal values and effective-date snapshots.
- Unpublished/expired packages and facilities are excluded.

Create `agent-bridge/to-claude/010-facilities-beds-packages-completion.md` when complete.
