"""OpenTelemetry tracing with a zero-dependency JSONL span exporter.

Every tool call and index operation gets a span. Spans land in a JSONL file
(always) and optionally in an OTLP/HTTP collector when
``OTEL_EXPORTER_OTLP_ENDPOINT`` is set and the ``[otlp]`` extra is installed.

The provider is deliberately *not* registered as the OTel global: instances
are cheap, reload-safe (tests), and stdout stays untouched — on a stdio MCP
server, stdout is the wire.

API per https://opentelemetry.io/docs/languages/python/instrumentation/
"""

from __future__ import annotations

import atexit
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import format_span_id, format_trace_id


class JSONLSpanExporter(SpanExporter):
    """Append finished spans as JSON lines to a file."""

    def __init__(self, path: Path):
        self._path = path

    def export(self, spans) -> SpanExportResult:
        try:
            records = []
            for span in spans:
                attributes = {
                    key: list(value) if isinstance(value, tuple) else value
                    for key, value in span.attributes.items()
                }
                records.append(
                    json.dumps(
                        {
                            "name": span.name,
                            "trace_id": format_trace_id(
                                span.get_span_context().trace_id
                            ),
                            "span_id": format_span_id(
                                span.get_span_context().span_id
                            ),
                            "start_ns": span.start_time,
                            "end_ns": span.end_time,
                            "duration_ms": round(
                                (span.end_time - span.start_time) / 1e6, 3
                            ),
                            "attributes": attributes,
                        },
                        default=str,
                    )
                )
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(records) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:  # pragma: no cover - exporter must never crash the server
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def shutdown(self) -> SpanExportResult:
        return SpanExportResult.SUCCESS


class Telemetry:
    """Owns a private TracerProvider; hands out spans via ``span()``."""

    def __init__(
        self,
        service_name: str = "clone-catcher",
        trace_path: str | Path = "clone_catcher_trace.jsonl",
        otlp_endpoint: str | None = None,
    ):
        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name})
        )
        provider.add_span_processor(
            SimpleSpanProcessor(JSONLSpanExporter(Path(trace_path)))
        )

        endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            except ImportError:
                print(
                    "clone-catcher: OTEL_EXPORTER_OTLP_ENDPOINT is set but the "
                    "[otlp] extra is not installed; spans go to JSONL only",
                    file=sys.stderr,
                )

        self._provider = provider
        self._tracer = provider.get_tracer("clone_catcher")
        atexit.register(self.shutdown)

    @contextmanager
    def span(self, name: str, **attributes):
        with self._tracer.start_as_current_span(name) as otel_span:
            for key, value in attributes.items():
                otel_span.set_attribute(f"clone_catcher.{key}", value)
            yield otel_span

    def shutdown(self) -> None:
        try:
            self._provider.shutdown()
        except Exception:  # pragma: no cover - best effort on exit
            pass


class NullTelemetry:
    """No-op stand-in so core modules can run uninstrumented."""

    @contextmanager
    def span(self, name: str, **attributes):
        yield None


def setup(settings) -> Telemetry:
    return Telemetry(trace_path=settings.trace_path)
