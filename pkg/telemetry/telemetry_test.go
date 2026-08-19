package telemetry

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"go.opentelemetry.io/otel/attribute"
)

func TestTelemetryJSONLExport(t *testing.T) {
	tmp := t.TempDir()
	traceFile := filepath.Join(tmp, "trace.jsonl")

	tracer, err := InitTracer("test-service", traceFile)
	if err != nil {
		t.Fatalf("InitTracer failed: %v", err)
	}

	ctx := context.Background()
	_, span := tracer.Start(ctx, "test_operation",
		attribute.String("test.key", "value"),
		attribute.Int("test.count", 42),
	)
	time.Sleep(10 * time.Millisecond)
	span.End()

	if err := tracer.Shutdown(ctx); err != nil {
		t.Fatalf("Shutdown failed: %v", err)
	}

	data, err := os.ReadFile(traceFile)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}

	if len(data) == 0 {
		t.Fatalf("expected span data in %s, got 0 bytes", traceFile)
	}

	t.Logf("Exported JSONL span: %s", string(data))
}
