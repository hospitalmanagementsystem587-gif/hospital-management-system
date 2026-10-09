# Agent Bridge — Hospital Management System & Mobile App

A structured collaboration channel between agents (Antigravity, Claude, Codex) and human developers for coordinating full-stack features between:
- **Django Hospital Management System (HMS)** (`hospital-management-system`)
- **Android Mobile Patient Portal** (`hospital-vedant`)

## Directory Layout
- `to-claude/`: Outgoing messages, reviews, questions, or completion reports for Claude.
- `to-antigravity/`: Tasks, instructions, or reviews directed to Antigravity.
- `archive/`: Processed and resolved messages.
- `001-mobile-app-feature-audit-and-integration-plan.md`: Comprehensive technical roadmap connecting the Android app with the Django backend.
- `to-antigravity/000-workstream-index.md`: Master execution order, dependencies, and shared rules for the complete mobile integration backlog.
- `to-antigravity/002-*.md` through `014-*.md`: Individual implementation tasks covering the API, onboarding, appointments, content, QR, health records, billing, medication reminders, feedback, facilities, analytics, insurance/ABHA, governed health content, and mobile release security.
- `STATUS.md`: Current execution turn and priority indicator.
- `COMPLETION_CONTRACT.md`: Required evidence and guardrails before any Jira
  implementation ticket is considered complete.
