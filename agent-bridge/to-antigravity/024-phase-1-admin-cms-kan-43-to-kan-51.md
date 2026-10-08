# Antigravity Prompt Queue — Phase 1 Admin CMS (KAN-43–KAN-51)

For every block below, first load `023-ticket-executor-contract-kan-42-to-kan-106.md`.
Execute one block per run. KAN-42 has its dedicated prompt in `022-kan-42-specialty-model.md`.

## KAN-43 — Admin CMS: Doctor Management

Execute only KAN-43 after KAN-42 is Done. Manage existing StaffProfile/User doctor
records through the admin CMS; preserve identity, groups, employee IDs, public
directory and Android consumers. Test admin-only CRUD, validation, activation,
historical references and API compatibility. Do not add specialties or schedules.

## KAN-44 — Admin CMS: Doctor Specialty Relationships

Execute only KAN-44 after KAN-43. Add the Jira-defined doctor↔specialty relation
using existing Doctor/StaffProfile and Specialty sources of truth. Enforce valid,
active relationships, safe updates and public filtering. Test duplicates,
permissions and existing doctor APIs. Do not implement schedules.

## KAN-45 — Admin CMS: Doctor Schedule Management

Execute only KAN-45 after KAN-44. Model/manage availability and scheduling rules
without duplicating appointments. Define timezone, overlap, inactive-doctor and
historical behavior explicitly. Test conflicts, permissions and appointment/API
compatibility. Do not change booking UX beyond required contracts.

## KAN-46 — Admin CMS: Service Management

Execute only KAN-46 after KAN-45. Improve the existing Service master-data CMS,
preserving codes and billing references. Test CRUD, normalization, activation,
ordering and referenced-service behavior. Do not implement price versioning.

## KAN-47 — Admin CMS: Diagnostic Test Management

Execute only KAN-47 after KAN-46. Introduce/reuse the smallest first-class
diagnostic-test domain required by Jira, distinct from generic services without
duplicating them. Test constraints, admin permissions, activation and consumer
compatibility. Do not add diagnostic pricing.

## KAN-48 — Admin CMS: Health Packages

Execute only KAN-48 after KAN-47. Build on existing HealthPackage and Service
relationships, preserving published/effective behavior and Android APIs. Test
package composition, validity, permissions and historical safety. Do not create
the later canonical pricing architecture.

## KAN-49 — Admin CMS: Website Content Management

Execute only KAN-49 after KAN-48. Reuse governed content models and implement the
Jira-defined CMS workflow with server-side admin authorization, sanitization and
safe public consumption. Test draft/public visibility and injection resistance.
Do not implement the publishing workflow reserved for KAN-51.

## KAN-50 — Admin CMS: Facilities and FAQs

Execute only KAN-50 after KAN-49. Reuse HospitalFacility/HospitalFaq and existing
public APIs. Implement authorized management, ordering, activation/public flags
and validation. Test public filtering and Android compatibility. Do not implement
global publication orchestration.

## KAN-51 — Admin CMS: Public Website Publishing Workflow

Execute only KAN-51 after KAN-50. Add the minimal coherent draft/review/publish
workflow across the Jira-specified public content, with auditability, permissions
and safe rollback/version behavior. Test unauthorized publishing and public
visibility. Do not start pricing.

