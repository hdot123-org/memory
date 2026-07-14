# PostHog Error Insights

> How to query PostHog for error trends and insights from memory-core telemetry.

## Prerequisites

- PostHog project with memory-core events flowing (POSTHOG_API_KEY configured)
- Access to PostHog dashboard at https://us.posthog.com (or self-hosted)

## Key Queries

### Error Rate Over Time

Create a Trend insight:
1. Event: `memory.error`
2. Group by: `error_type`
3. Time range: Last 30 days

### Top Error Types

```sql
-- HogQL: Top error types by frequency
SELECT
  properties.error_type,
  count() as occurrences
FROM events
WHERE event = 'memory.error'
  AND timestamp > now() - INTERVAL 7 DAY
GROUP BY properties.error_type
ORDER BY occurrences DESC
LIMIT 10
```

### Errors by Failed Event

Filter by which event failed:
1. Event: `memory.error`
2. Breakdown: `properties.failed_event`
3. This shows which telemetry operations fail most frequently.

### Errors by Method

```sql
SELECT
  properties.method,
  count() as failures
FROM events
WHERE event = 'memory.error'
  AND timestamp > now() - INTERVAL 30 DAY
GROUP BY properties.method
ORDER BY failures DESC
```

## Dashboard Setup

Recommended dashboard panels:
1. **Error count trend** (daily, last 30 days)
2. **Error type distribution** (bar chart, grouped by error_type)
3. **Error rate** (memory.error / total events ratio)
4. **Top failing methods** (table)
