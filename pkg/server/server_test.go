package server

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
)

func TestServerEndpoints(t *testing.T) {
	tmp := t.TempDir()
	file1 := filepath.Join(tmp, "service1.py")
	file2 := filepath.Join(tmp, "service2.py")
	file3 := filepath.Join(tmp, "other.py")

	code1 := "def handle_event(event):\n    if event.valid:\n        return process(event)\n    return False\n"
	code2 := "def handle_message(msg):\n    if msg.valid:\n        return process(msg)\n    return False\n" // Clone
	code3 := "def compute_sum(a, b):\n    return a + b\n" // Unrelated

	os.WriteFile(file1, []byte(code1), 0644)
	os.WriteFile(file2, []byte(code2), 0644)
	os.WriteFile(file3, []byte(code3), 0644)

	srv, err := NewServer(Config{Root: tmp})
	if err != nil {
		t.Fatalf("NewServer failed: %v", err)
	}

	ctx := context.Background()

	// 1. Test reindex_workspace
	reindexRes, err := srv.handleReindexWorkspace(ctx, mcp.CallToolRequest{})
	if err != nil || reindexRes.IsError {
		t.Fatalf("reindex_workspace failed: %v", reindexRes)
	}

	// 2. Test find_duplicate_groups
	groupsRes, err := srv.handleFindDuplicateGroups(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Arguments: map[string]interface{}{
				"threshold": 0.9,
			},
		},
	})
	if err != nil || groupsRes.IsError {
		t.Fatalf("find_duplicate_groups failed: %v", groupsRes)
	}

	// 3. Test find_structural_clones
	clonesRes, err := srv.handleFindStructuralClones(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Arguments: map[string]interface{}{
				"file_path": "service1.py",
				"threshold": 0.9,
			},
		},
	})
	if err != nil || clonesRes.IsError {
		t.Fatalf("find_structural_clones failed: %v", clonesRes)
	}

	// 4. Test get_diff_summary
	diffRes, err := srv.handleGetDiffSummary(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Arguments: map[string]interface{}{
				"file_a": file1,
				"file_b": file2,
			},
		},
	})
	if err != nil || diffRes.IsError {
		t.Fatalf("get_diff_summary failed: %v", diffRes)
	}
}
