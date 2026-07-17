# Observability and Error Tracking

> Overview of memory-core's error tracking and observability capabilities at the code layer.
> For event schema details, see `posthog-event-taxonomy.md`. For privacy and data handling, see `posthog-privacy.md`.

## Overview

memory-core uses **PostHog** as its primary error tracking and observability backend. The implementation is designed to be:

- **Fail-safe**: Telemetry operations never break the host application flow
- **Privacy-aware**: Automatic path sanitization prevents filesystem data leaks
- **Opt-out friendly**: Users can disable telemetry with a single environment variable

The core telemetry infrastructure lives in `memory_core/tools/telemetry_bridge.py` and `memory_core/tools/posthog_client.py`.

## Telemetry Bridge Architecture

The `TelemetryBridge` class provides a centralized, fail-safe channel for reporting events to PostHog. Key design principles:

1. **Singleton pattern**: Global `telemetry` instance ensures consistent state across the application
2. **Project-aware distinct_id**: Uses `project_id` from `project_lifecycle` (not hardcoded values)
3. **Automatic namespace prefixing**: All events are prefixed with `memory.` for clarity
4. **Data sanitization**: Full filesystem paths are replaced with basenames before transmission

### Core Methods

#### `safe_capture(event_name, properties, cwd)`

Captures a single event with automatic sanitization and enrichment.

**Behavior:**
- Adds common properties: `memory_core_version`, `host`, `timestamp`
- Sanitizes all path-like values in `properties` (see Path Sanitization below)
- Resolves `distinct_id` from the working directory's project lifecycle record
- **Never raises exceptions** - failures are logged at debug level

**Example:**
```python
from memory_core.tools.telemetry_bridge import telemetry

telemetry.safe_capture(
    event_name="hook_triggered",
    properties={"hook_type": "session_start", "cwd": "/Users/alice/project"},
    cwd="/Users/alice/project"
)
# Sends: {event: "memory.hook_triggered", properties: {hook_type: "session_start", cwd: "project", ...}}
```

#### `batch_capture(events, cwd)`

Sends multiple events in a single HTTP request to reduce overhead.

**Behavior:**
- Builds a batch payload with all events
- Sends directly to PostHog's `/batch/` endpoint using stdlib `urllib`
- Includes retry logic for transient failures (timeouts, 429, 5xx)
- Returns `True` on success, `False` on failure (never raises)

**Use case:** When multiple events occur in quick succession (e.g., during hook execution), batch them to avoid per-event HTTP overhead.

#### `_sanitize_properties(properties)`

Internal method that replaces path-like values with their basenames.

**Detection logic:**
- Keys containing: `path`, `file`, `cwd`, `dir`, `root`
- Values that look like absolute paths (POSIX `/`, Windows `C:\`, or OS separator)

**Example:**
```python
# Input
{"cwd": "/Users/alice/my-project", "hook_type": "session_start"}

# Output
{"cwd": "my-project", "hook_type": "session_start"}
```

This prevents leaking usernames, project locations, or other sensitive filesystem metadata.

## Error Tracking Flow

When an error occurs in memory-core:

```
1. Exception raised in memory_core code
   ↓
2. telemetry_bridge._capture_error() catches it
   ↓
3. Emits "memory.error" event to PostHog with:
   - error_type: Exception class name (e.g., "ValueError")
   - error_message: Truncated to 500 chars, sanitized
   - failed_event: The event that triggered the error
   - method: The method that failed (e.g., "safe_capture")
   ↓
4. PostHog stores the error event
   ↓
5. Alerting system (external) detects error threshold breaches
```

**Key design:** `_capture_error()` calls the underlying PostHog client directly (not `safe_capture`) to avoid infinite recursion when the original failure is persistent.

## Event Types and Schema

memory-core emits structured events with the `memory.` namespace prefix. Common event types:

- `memory.error` - Error tracking (see Error Tracking Flow above)
- `memory.hook_triggered` - Hook execution events
- `memory.session_start` / `memory.session_end` - Session lifecycle
- `memory.kb_access` - Knowledge base read/write operations

Each event includes automatic properties:
- `memory_core_version` - Library version
- `host` - Host identifier (factory, droid, or hostname fallback)
- `timestamp` - ISO 8601 timestamp
- `distinct_id` - Project-specific identifier (deterministic hash of project directory)

For detailed event schema and property definitions, see [posthog-event-taxonomy.md](posthog-event-taxonomy.md).

## Privacy and Data Handling

memory-core implements several privacy safeguards:

### Path Sanitization

All filesystem paths are replaced with basenames before transmission. This prevents leaking:
- User home directories (`/Users/alice/...`)
- Project locations (`/home/user/work/project-name`)
- Operating system details (Windows vs POSIX paths)

The sanitization logic detects path-like keys (`path`, `file`, `cwd`, `dir`, `root`) and replaces absolute paths with their final component (basename).

### Opt-Out Configuration

Users can disable telemetry entirely by setting:

```bash
export POSTHOG_API_KEY=""
```

When the API key is empty, the PostHog client becomes a no-op and no events are sent.

Alternatively, users can prevent the default key from loading by not installing the `posthog` SDK:

```bash
pip uninstall posthog
```

Without the SDK, telemetry is automatically disabled.

### Data Minimization

- **No source code**: Events contain error types and messages, not code snippets
- **No user input**: User-provided data is not included in telemetry
- **No credentials**: API keys, tokens, and secrets are never transmitted
- **Truncated errors**: Error messages are limited to 500 characters to prevent accidental data leakage

For complete privacy policy and data handling details, see [posthog-privacy.md](posthog-privacy.md).

## OpenTelemetry (Optional)

memory-core also supports **OpenTelemetry** as an optional observability backend. OTel is disabled by default and can be enabled alongside or instead of PostHog.

**Enable OTel:**
```bash
export MEMORY_OTEL_ENABLED=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318
```

OTel provides distributed tracing, metrics, and logs in addition to PostHog's event-based telemetry. For setup details, see [otel-setup.md](otel-setup.md).

## Implementation Files

- `memory_core/tools/telemetry_bridge.py` - Main telemetry bridge (TelemetryBridge class)
- `memory_core/tools/posthog_client.py` - PostHog SDK wrapper (PostHogAnalytics singleton)
- `memory_core/default_posthog_key.txt` - Default PostHog public API key (loaded at runtime)

## References

- [PostHog Event Taxonomy](posthog-event-taxonomy.md) - Detailed event schema and property definitions
- [PostHog Privacy](posthog-privacy.md) - Privacy policy and data handling practices
- [OpenTelemetry Setup](otel-setup.md) - Optional OTel backend configuration
- [PostHog Documentation](https://posthog.com/docs) - Official PostHog docs
