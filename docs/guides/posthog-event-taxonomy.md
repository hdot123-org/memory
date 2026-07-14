# PostHog Event Taxonomy

> memory-core v0.9.0

## Event Naming Convention

All events use the `memory.*` prefix, auto-applied by `TelemetryBridge.safe_capture()`.

## Event Categories

### Hook Lifecycle Events

These events originate from the hook gateway (`memory_hook_gateway.py`). Local metrics records are replayed to PostHog via `telemetry.batch_capture()` during `session-start`, with the `memory.` prefix auto-applied by `TelemetryBridge.safe_capture()`.

| Event | Trigger | Key Properties |
|-------|---------|---------------|
| `memory.session-start` | Hook session begins | host, memory_core_version |
| `memory.session-end` | Hook session ends | host, duration_seconds |
| `memory.prompt-submit` | User submits prompt | host |
| `memory.hook_error` | Gateway error during hook processing | host |

### Error Events
| Event | Trigger | Key Properties |
|-------|---------|---------------|
| `memory.error` | Telemetry capture failure | error_type, error_message, failed_event, method |

## memory.error Event Schema

```json
{
  "event": "memory.error",
  "properties": {
    "error_type": "RuntimeError",
    "error_message": "connection refused (truncated to 500 chars)",
    "failed_event": "memory.session-start",
    "method": "safe_capture",
    "memory_core_version": "0.9.0",
    "host": "factory",
    "timestamp": "2026-07-14T12:00:00+08:00"
  }
}
```

## Property Sanitization

All properties pass through `_sanitize_properties()` before transmission:
- Path-like keys (path, file, cwd, dir, root) have values reduced to basename
- No PII, passwords, tokens, or API keys are transmitted
