package server

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
)

func TestMCPEndpointsStdioProtocol(t *testing.T) {
	tmp := t.TempDir()

	// Create test files
	f1 := filepath.Join(tmp, "orders_v1.go")
	f2 := filepath.Join(tmp, "orders_v2.go") // Clone of v1
	f3 := filepath.Join(tmp, "health.go")

	code1 := "package orders\nfunc ProcessOrder(id string, amount float64) bool {\n    if amount > 0 {\n        return record(id, amount)\n    }\n    return false\n}\n"
	code2 := "package orders\nfunc HandleOrder(key string, value float64) bool {\n    if value > 0 {\n        return record(key, value)\n    }\n    return false\n}\n"
	code3 := "package health\nfunc Ping() string { return \"pong\" }\n"

	os.WriteFile(f1, []byte(code1), 0644)
	os.WriteFile(f2, []byte(code2), 0644)
	os.WriteFile(f3, []byte(code3), 0644)

	srv, err := NewServer(Config{Root: tmp})
	if err != nil {
		t.Fatalf("NewServer failed: %v", err)
	}

	ctx := context.Background()

	// 1. Test handleFindDuplicateGroups
	req := mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "find_duplicate_groups",
			Arguments: map[string]interface{}{
				"threshold": 0.85,
			},
		},
	}
	res, err := srv.handleFindDuplicateGroups(ctx, req)
	if err != nil || res.IsError {
		t.Fatalf("handleFindDuplicateGroups error: %v", res)
	}

	rawText := res.Content[0].(mcp.TextContent).Text
	var groupData map[string]interface{}
	if err := json.Unmarshal([]byte(rawText), &groupData); err != nil {
		t.Fatalf("unmarshal error: %v", err)
	}

	if int(groupData["group_count"].(float64)) != 1 {
		t.Errorf("expected 1 duplicate group, got %v", groupData["group_count"])
	}

	// 2. Test handleFindStructuralClones
	cloneReq := mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "find_structural_clones",
			Arguments: map[string]interface{}{
				"file_path": "orders_v1.go",
				"threshold": 0.85,
			},
		},
	}
	cloneRes, err := srv.handleFindStructuralClones(ctx, cloneReq)
	if err != nil || cloneRes.IsError {
		t.Fatalf("handleFindStructuralClones error: %v", cloneRes)
	}

	// 3. Test handleGetDiffSummary
	diffReq := mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "get_diff_summary",
			Arguments: map[string]interface{}{
				"file_a": f1,
				"file_b": f2,
			},
		},
	}
	diffRes, err := srv.handleGetDiffSummary(ctx, diffReq)
	if err != nil || diffRes.IsError {
		t.Fatalf("handleGetDiffSummary error: %v", diffRes)
	}

	var diffData map[string]interface{}
	json.Unmarshal([]byte(diffRes.Content[0].(mcp.TextContent).Text), &diffData)
	if !diffData["identical_structure"].(bool) {
		t.Errorf("expected identical_structure true for clone pair")
	}
}
