// Package telemetry provides OpenTelemetry instrumentation with JSONL span logging.
package telemetry

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
)

// JSONLSpanExporter appends finished spans as JSON lines to a file.
type JSONLSpanExporter struct {
	mu   sync.Mutex
	file *os.File
}

// SpanRecord represents the JSON structure of a recorded span.
type SpanRecord struct {
	Name       string                 `json:"name"`
	TraceID    string                 `json:"trace_id"`
	SpanID     string                 `json:"span_id"`
	StartTime  string                 `json:"start_time"`
	DurationMs float64                `json:"duration_ms"`
	Attributes map[string]interface{} `json:"attributes"`
}

// NewJSONLSpanExporter creates a new JSONL file span exporter.
func NewJSONLSpanExporter(path string) (*JSONLSpanExporter, error) {
	if path == "" {
		return nil, nil
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return nil, err
	}
	return &JSONLSpanExporter{file: f}, nil
}

// ExportSpans serializes completed spans into JSON lines.
func (e *JSONLSpanExporter) ExportSpans(ctx context.Context, spans []sdktrace.ReadOnlySpan) error {
	if e == nil || e.file == nil {
		return nil
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	for _, s := range spans {
		attrs := make(map[string]interface{})
		for _, kv := range s.Attributes() {
			attrs[string(kv.Key)] = kv.Value.AsInterface()
		}
		durationMs := float64(s.EndTime().Sub(s.StartTime()).Microseconds()) / 1000.0
		rec := SpanRecord{
			Name:       s.Name(),
			TraceID:    s.SpanContext().TraceID().String(),
			SpanID:     s.SpanContext().SpanID().String(),
			StartTime:  s.StartTime().Format(time.RFC3339Nano),
			DurationMs: durationMs,
			Attributes: attrs,
		}
		data, err := json.Marshal(rec)
		if err == nil {
			_, _ = e.file.Write(data)
			_, _ = e.file.WriteString("\n")
		}
	}
	return nil
}

// Shutdown closes the underlying span log file.
func (e *JSONLSpanExporter) Shutdown(ctx context.Context) error {
	if e == nil || e.file == nil {
		return nil
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.file.Close()
}

// Tracer provides a wrapper around OpenTelemetry Tracer with JSONL fallback.
type Tracer struct {
	tp     *sdktrace.TracerProvider
	tracer trace.Tracer
}

// InitTracer initializes OpenTelemetry tracing.
func InitTracer(serviceName, tracePath string) (*Tracer, error) {
	var opts []sdktrace.TracerProviderOption

	res, err := resource.New(
		context.Background(),
		resource.WithAttributes(semconv.ServiceNameKey.String(serviceName)),
	)
	if err == nil {
		opts = append(opts, sdktrace.WithResource(res))
	}

	if tracePath != "" {
		exp, err := NewJSONLSpanExporter(tracePath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "failed to initialize jsonl span exporter: %v\n", err)
		} else if exp != nil {
			opts = append(opts, sdktrace.WithSyncer(exp))
		}
	}

	tp := sdktrace.NewTracerProvider(opts...)
	otel.SetTracerProvider(tp)
	tracer := tp.Tracer(serviceName)

	return &Tracer{
		tp:     tp,
		tracer: tracer,
	}, nil
}

// Start begins a new span.
func (t *Tracer) Start(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	if t == nil || t.tracer == nil {
		return ctx, trace.SpanFromContext(ctx)
	}
	return t.tracer.Start(ctx, name, trace.WithAttributes(attrs...))
}

// Shutdown flushes and closes the tracer provider.
func (t *Tracer) Shutdown(ctx context.Context) error {
	if t == nil || t.tp == nil {
		return nil
	}
	return t.tp.Shutdown(ctx)
}
