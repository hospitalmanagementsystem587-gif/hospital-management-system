# Antigravity Prompt Queue — Phase 3 Staff Portal (KAN-60–KAN-67)

Load the shared executor contract before each ticket. Execute exactly one block per run.

## KAN-60 — Staff Dashboard

After KAN-59, build only the permission-scoped staff dashboard using shared design
components and existing queries. Test each role, empty states and privacy. Do not
build appointment workspace features.

## KAN-61 — Appointment Workspace

After KAN-60, implement the staff appointment workflow over existing lifecycle
services. Test role actions, transitions, conflicts, direct URLs and concurrency.
Do not expand patient or consultation workspaces.

## KAN-62 — Patient Workspace

After KAN-61, create permission-scoped patient lookup/detail workflows using the
existing Patient source of truth. Test sensitive-field visibility, archived data
and cross-role access. Do not implement consultations.

## KAN-63 — Doctor Consultation Workspace

After KAN-62, implement consultation authoring/review with existing clinical
models, lifecycle and doctor ownership. Test draft/release rules, unauthorized
access and audit behavior. Do not redesign prescriptions.

## KAN-64 — Prescription Workspace

After KAN-63, implement staff prescription workflows using existing Prescription
models and medicine catalog. Test authoring permissions, clinical ownership,
status changes and print/API regression. Dispensing stays in Store Portal.

## KAN-65 — Clinical Document Workspace

After KAN-64, implement secure upload/review/release/download using existing
private storage and scan states. Test malicious files, unreleased/revoked records,
non-disclosure and cross-patient access. Do not build patient document UI.

## KAN-66 — IPD Workspace

After KAN-65, implement staff admission/bed/deposit/discharge workflows without
duplicating IPD models. Test permissions, bed integrity, active-admission rules,
transactions and historical records.

## KAN-67 — Staff Ticket Workspace

After KAN-66, follow Jira's dependency on ticketing foundations. If KAN-86–KAN-93
are not yet available, mark this ticket blocked rather than inventing a ticket
domain. Implement only the staff-facing integration defined by Jira.

