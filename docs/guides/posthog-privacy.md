# PostHog Privacy Compliance

> What data memory-core collects, how it's sanitized, and how users opt out.

## Data Collected

| Field | Example | Purpose |
|-------|---------|---------|
| event | `memory.init`, `memory.error` | Which feature was used |
| distinct_id | `my-project-a1b2c3d4e5f6` | Anonymous project identifier (SHA256 hash of directory name) |
| memory_core_version | `0.9.0` | Version tracking |
| host | `factory` | Platform identifier |
| timestamp | `2026-07-14T12:00:00+08:00` | Event time |
| error_type | `RuntimeError` | Error classification (memory.error events only) |
| error_message | (truncated 500 chars) | Error detail (sanitized) |

## What is NOT Collected

- No user names, emails, or personal identifiers
- No passwords, API keys, tokens, or secrets
- No absolute file paths (reduced to basename via SanitizingFilter)
- No private IP addresses (redacted in logs)
- No source code or file contents

## Sanitization Mechanisms

### Log Sanitization (SanitizingFilter)
`log_utils.py` redacts from all log output:
- Bearer tokens
- Passwords (password, passwd, pwd)
- API keys and secrets (token, api_key, secret, authorization)
- Private IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x)

### Telemetry Sanitization (_sanitize_properties)
`telemetry_bridge.py` reduces path-like property values:
- Keys containing: path, file, cwd, dir, root
- Values that look like absolute paths are replaced with basename only

## Opt-Out Methods

### Disable PostHog Telemetry
Set `POSTHOG_API_KEY=` (empty string) in environment. The analytics client becomes a no-op.

### Disable Metrics Pipeline
Set `MEMORY_HOOK_METRICS_DISABLED=1` in environment. Stops JSONL metrics collection.

### Disable All Telemetry
Set both variables above to disable all data collection.
