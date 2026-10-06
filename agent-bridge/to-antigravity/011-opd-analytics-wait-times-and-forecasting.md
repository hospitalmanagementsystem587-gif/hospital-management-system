# Task 011 — OPD Analytics, Wait Times and Forecasting

**Priority:** P2  
**Depends on:** Task 002 and sufficient production-quality appointment lifecycle data

## Goal

Replace the Android app's hardcoded crowd chart with transparent historical metrics and, only when justified by data quality, conservative wait-time estimates or forecasts.

## Scope

- Define metrics before implementation: booked volume, check-ins, no-shows, completed visits, check-in-to-start wait, consultation duration, department/doctor capacity, and time bucket boundaries.
- Validate lifecycle timestamp completeness and timezone handling. Produce a data-quality report and minimum sample thresholds.
- Build aggregate Django queries/services and APIs that avoid patient-level data exposure.
- Start with clearly labeled historical patterns. Add current estimated wait only if it uses live queue state and documented assumptions.
- Add forecasting only after back-testing against a baseline, error measurement, sparse-data fallback, and owner approval. Never label fixed sample numbers as real predictions.
- Update Android charts with data source, date range, freshness, sample size, confidence/uncertainty, and safe empty/error states.
- Avoid nudging emergency patients to delay care; emergency guidance must override crowd recommendations.

## Acceptance and Tests

- Metrics match fixture data across day boundaries, timezones, cancellations, no-shows, missing timestamps, and partial days.
- Aggregates cannot expose individual patients or low-volume sensitive slices.
- Department filters actually change the underlying calculation.
- Any forecast includes back-test results, versioning, fallback behavior, and monitoring for drift/error.
- Android removes the static `OpdTrendRepository` from the production path and distinguishes history, live estimate, and forecast.

Create `agent-bridge/to-claude/011-opd-analytics-completion.md` when complete.
