# Antigravity Prompt — KAN-38 Shared Design System

Implement **only Jira KAN-38**. Do not begin KAN-39 or redesign business workflows.

## Start gate

Read KAN-38 completely and confirm KAN-37 is Done and integrated. Authorization
must remain server-side; this ticket must not compensate for missing security by
hiding links.

## Required audit before changes

Inventory all templates, base layouts, static CSS/JS, forms, tables, navigation,
alerts/messages, responsive breakpoints, accessibility behavior, and any current
design tokens/components. Identify reusable patterns and current regressions.

## Scope

Build one reusable HMS design system for admin, staff, store, patient, and agent
portals: tokens, typography, spacing, layout primitives, navigation, forms,
tables, cards, alerts, dialogs, status indicators, pagination, and empty/loading/
error states. Preserve existing business logic, URLs, forms, APIs, and workflows.
Prefer incremental components and template includes over a whole-CMS rewrite.

Meet accessibility basics: semantic structure, labels, focus visibility,
keyboard operation, contrast, reduced-motion respect, and responsive layouts.
Do not implement the KAN-39 dashboard or later portal pages.

## Verification and completion

Add focused template/component tests and run all existing checks. Manually
inspect representative pages at desktop and mobile widths. Commit/push KAN-38,
update only its Jira issue with exact evidence and screenshots only if useful,
then identify KAN-39 without implementing it.

