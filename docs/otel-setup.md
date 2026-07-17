# OpenTelemetry Setup (v0.9.0)

This page describes how to enable and configure OpenTelemetry (OTel)
exporters for memory-core observability. OTel is **optional** and
disabled by default; PostHog remains the default telemetry backend.

## Environment Variables

### `MEMORY_OTEL_ENABLED`

Master switch for the OTel pipeline.

| Value          | Effect                                   |
|----------------|------------------------------------------|
| unset / `0`    | OTel pipeline disabled (default).        |
| `1` / `true`   | OTel pipeline enabled on startup.        |

Example:

    export MEMORY_OTEL_ENABLED=1
    python -m memory_core.tools.memory_hook_gateway ...

When `MEMORY_OTEL_ENABLED` is not set or falsy, the OTel runtime is
never initialized and no OTel SDK calls are made.

### `OTEL_EXPORTER_OTLP_ENDPOINT`

The OTLP (HTTP or gRPC) endpoint that receives spans, metrics, and
logs. Required when OTel is enabled.

Examples:

    # Jaeger (OTLP HTTP)
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

    # Grafana Cloud OTLP
    export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-east-0.grafana.net/otlp

    # Local collector (gRPC)
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

### `OTEL_EXPORTER_OTLP_PROTOCOL`

Protocol used by the OTLP exporter.

| Value   | Meaning                         |
|---------|---------------------------------|
| `http/protobuf` | OTLP over HTTP (default). |
| `grpc`          | OTLP over gRPC.           |

### `OTEL_SERVICE_NAME`

Service name reported to the collector. Defaults to `memory-core`.

    export OTEL_SERVICE_NAME=memory-core-worker

### `OTEL_EXPORTER_OTLP_HEADERS`

Optional comma-separated `key=value` headers sent on every OTLP
request (e.g. authentication tokens for Grafana Cloud / SigNoz).

    export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic xyz,tenant=abc"

## Exporter Configuration

memory-core uses the standard OpenTelemetry Python SDK:

- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-http`
- `opentelemetry-exporter-otlp-proto-grpc` (optional)

Install with the project `otel` extra (once published):

    pip install memory-core[otel]

Or install the SDK directly:

    pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

### Programmatic Setup

The recommended setup mirrors the PostHog pattern in
`memory_core/tools/telemetry_bridge.py`:

    import os
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    def setup_otel() -> None:
        if not os.environ.get("MEMORY_OTEL_ENABLED"):
            return

        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        service = os.environ.get("OTEL_SERVICE_NAME", "memory-core")

        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Resource attributes
        from opentelemetry.sdk.resources import Resource
        resource = Resource.create({"service.name": service})
        provider._resource = resource

Call `setup_otel()` once during process startup (e.g. from the memory
hook entry point). If `MEMORY_OTEL_ENABLED` is unset, the function
returns immediately without touching the OTel SDK.

### Collector Recommendations

| Collector             | Endpoint pattern                                  |
|-----------------------|---------------------------------------------------|
| Grafana Alloy / Agent | `https://otlp-gateway-...grafana.net/otlp`        |
| SigNoz                | `https://ingest.{region}.signoz.cloud:443`        |
| Jaeger (local)        | `http://localhost:4318`                           |
| AWS X-Ray (via ADOT)  | configured via ADOT collector sidecar             |

For local development, run the OTel Collector in Docker:

    docker run --rm -p 4317:4317 -p 4318:4318 \
        otel/opentelemetry-collector:latest

Then point `OTEL_EXPORTER_OTLP_ENDPOINT` at `http://localhost:4318`.

## Troubleshooting

- **No spans arriving:** verify `MEMORY_OTEL_ENABLED=1` is exported in
  the same shell that runs memory-core. Check the collector's UI
  (e.g. Jaeger UI at `http://localhost:16686`).
- **401/403 from cloud endpoint:** set `OTEL_EXPORTER_OTLP_HEADERS`
  with the correct auth header.
- **Timeout / connection refused:** confirm
  `OTEL_EXPORTER_OTLP_ENDPOINT` is reachable from the host; for gRPC
  make sure `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` is set and the port is
  `4317`.

## References

- PostHog observability: `docs/guides/posthog-event-taxonomy.md`,
  `docs/guides/posthog-privacy.md`.
- Code quality metrics: `docs/code-quality-metrics.md`.
