# Antigravity Prompt — KAN-40 Hospital Profile CMS

Implement **only Jira KAN-40**. Do not begin Department Management.

## Start gate

Read KAN-40 completely and confirm KAN-39 is Done and integrated.

## Required audit before changes

Inspect `HospitalSettings`, its singleton enforcement, admin/CMS behavior,
validation, context processor, public templates and APIs, Android consumers,
audit behavior, and current emergency/contact/address/map fields.

## Scope

Provide a business-friendly, administrator-only CMS workflow over the existing
HospitalSettings source of truth. Preserve singleton semantics and existing
public/API contracts. Support the ticket's emergency, ambulance, reception,
contact, address, city, landmark, and map requirements with the smallest safe
schema change. Do not split contacts into a new model unless the current schema
cannot meet the criteria; document that decision.

Do not redesign the website, implement departments/specialties, or change public
publishing rules beyond what KAN-40 requires.

## Verification and completion

Test permission denial, singleton behavior, validation, persistence, existing
public consumers, and API compatibility. Run full tests and migration drift.
Commit/push KAN-40, update only KAN-40 with evidence, and identify KAN-41 only.

