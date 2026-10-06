# Task 011 Completion — OPD Historical Analytics

## Delivered

- Public `GET /api/v1/opd/historical-metrics/` aggregates the prior 28 complete days by weekday and hour.
- Metrics include booked volume, check-ins, completed visits, no-shows, check-in-to-start wait, and consultation duration.
- Department-code filtering changes the underlying query.
- Buckets with fewer than five appointments are suppressed and no patient identifiers are returned.
- Data-quality metadata reports record counts and complete wait samples.
- Forecasting remains explicitly disabled until lifecycle data is sufficient, back-tested, monitored, and hospital-approved.
- Android now consumes this endpoint instead of `OpdTrendRepository`; it labels data as historical, shows safe empty/error states, and prioritizes emergency guidance.

## Verification

- Focused Django aggregate/filter/privacy test passes.
- Android `testDebugUnitTest` passes.

## Branching

This branch is stacked on Task 010 in both repositories.
