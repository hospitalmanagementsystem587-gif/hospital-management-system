# Task 004 — Doctor Directory, Hospital Content, Emergency Contacts and FAQ

**Priority:** P1  
**Depends on:** Task 002

## Goal

Replace Android hardcoded doctors, facilities, contact details, claims, packages, and FAQs with reviewed content served by Django and shared consistently by web and mobile.

## Scope

- Extend the Django content model only as needed for doctor public profiles, qualifications, languages, consultation location, approved biography, public visibility, schedules, and contact/content sections.
- Return doctors from active Doctor-group staff and active departments. Do not expose usernames, permissions, employee internals, or inactive staff.
- Build read-only APIs for doctor directory/profile, hospital contact information, emergency/ambulance/reception numbers, address/maps metadata, departments, facilities, and searchable FAQ content.
- Provide controlled staff administration for published content, ordering, activation, and effective dates.
- Update Android doctor search/filter/profile, hospital information, emergency dialer, maps, and FAQ screens to use API content with a safe cached fallback.
- Update Django templates to use the same configured emergency/contact values instead of duplicated static numbers.

## Content Integrity Rules

- Remove or quarantine unverified claims such as accreditations, capabilities, doctor qualifications, review counts, availability, prices, and response times until an authorized owner approves them.
- Do not generate doctor ratings from static formulas.
- Emergency calling must still work when the API is unavailable by using a signed/release-configured fallback that is reviewed before release.
- Clearly separate medical emergency actions from general reception/appointment contact actions.

## Acceptance and Tests

- Published content is consistent across Django and Android.
- Inactive/unpublished records do not appear in patient APIs.
- API payloads expose only approved public fields and cache metadata.
- Search/filtering handles empty states and stale/offline cache.
- Emergency dial actions use the configured number and have accessibility labels.
- Content changes are permission-controlled and audited.

Create `agent-bridge/to-claude/004-doctor-content-emergency-completion.md` when complete.
