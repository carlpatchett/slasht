package server

import (
	"context"
	"fmt"
	"os"

	"github.com/carlpatchett/slasht/pkg/difftool"
	"github.com/carlpatchett/slasht/pkg/index"
	"github.com/carlpatchett/slasht/pkg/telemetry"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
)

// Server encapsulates the CloneCatcher MCP server instance.
type Server struct {
	mcpServer *server.MCPServer
	idx       *index.CloneIndex
	tracer    *telemetry.Tracer
}

// Config holds runtime configuration options for the server.
type Config struct {
	Root      string
	TracePath string
}

// NewServer initializes the MCP server and registers all 4 tool endpoints.
func NewServer(cfg Config) (*Server, error) {
	tr, err := telemetry.InitTracer("slasht", cfg.TracePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "telemetry init error: %v\n", err)
	}

	idx := index.NewCloneIndex(cfg.Root, tr)

	s := server.NewMCPServer(
		"slasht",
		"1.0.0",
		server.WithToolCapabilities(true),
	)

	srv := &Server{
		mcpServer: s,
		idx:       idx,
		tracer:    tr,
	}

	srv.registerTools()
	return srv, nil
}

func (s *Server) registerTools() {
	// 1. find_duplicate_groups
	findGroupsTool := mcp.NewTool("find_duplicate_groups",
		mcp.WithDescription("INSTANT REPO-WIDE CLONE MAP. Call this FIRST before reading files. Returns all groups of structurally duplicated files (renames and literal changes ignored), largest group first, with similarity stats, sample code snippets, and structural summaries."),
		mcp.WithNumber("threshold",
			mcp.Description("Minimum structural similarity (0.0 to 1.0, default 0.9)"),
			mcp.DefaultNumber(0.9),
		),
		mcp.WithNumber("max_groups",
			mcp.Description("Maximum duplicate groups to return (default 25)"),
			mcp.DefaultNumber(25),
		),
		mcp.WithNumber("max_files_per_group",
			mcp.Description("Maximum files listed per group (default 20)"),
			mcp.DefaultNumber(20),
		),
	)
	s.mcpServer.AddTool(findGroupsTool, s.handleFindDuplicateGroups)

	// 2. find_structural_clones
	findClonesTool := mcp.NewTool("find_structural_clones",
		mcp.WithDescription("Find files structurally similar to file_path across the workspace (renames and literal changes ignored). Returns matches with similarity >= threshold, ranked most similar first."),
		mcp.WithString("file_path",
			mcp.Required(),
			mcp.Description("Relative or absolute path to the target file"),
		),
		mcp.WithNumber("threshold",
			mcp.Description("Minimum structural similarity (0.0 to 1.0, default 0.9)"),
			mcp.DefaultNumber(0.9),
		),
	)
	s.mcpServer.AddTool(findClonesTool, s.handleFindStructuralClones)

	// 3. get_diff_summary
	diffSummaryTool := mcp.NewTool("get_diff_summary",
		mcp.WithDescription("Summarize AST-level differences between two files. Reports whether two files have identical structure (differing only in naming/literals) and exact differing node types with line ranges."),
		mcp.WithString("file_a",
			mcp.Required(),
			mcp.Description("Path to the first file"),
		),
		mcp.WithString("file_b",
			mcp.Required(),
			mcp.Description("Path to the second file"),
		),
	)
	s.mcpServer.AddTool(diffSummaryTool, s.handleGetDiffSummary)

	// 4. reindex_workspace
	reindexTool := mcp.NewTool("reindex_workspace",
		mcp.WithDescription("Rebuild the structural clone index from disk. Call after adding, deleting, or editing files so clone queries reflect latest code."),
	)
	s.mcpServer.AddTool(reindexTool, s.handleReindexWorkspace)
}

func (s *Server) handleFindDuplicateGroups(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	threshold := request.GetFloat("threshold", 0.9)
	maxGroups := request.GetInt("max_groups", 25)
	maxFiles := request.GetInt("max_files_per_group", 20)

	groups, err := s.idx.DuplicateGroups(ctx, threshold, maxGroups, maxFiles)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("finding duplicate groups: %v", err)), nil
	}

	totalClones := 0
	for _, g := range groups {
		totalClones += g.Size
	}

	res := map[string]interface{}{
		"groups":                 groups,
		"group_count":            len(groups),
		"total_clones":           totalClones,
		"threshold":              threshold,
		"indexed_workspace_root": s.idx.Root,
	}

	return mcp.NewToolResultJSON(res)
}

func (s *Server) handleFindStructuralClones(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	filePath, err := request.RequireString("file_path")
	if err != nil || filePath == "" {
		return mcp.NewToolResultError("file_path is required"), nil
	}

	threshold := request.GetFloat("threshold", 0.9)

	clones, err := s.idx.FindClones(ctx, filePath, threshold, 50)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("finding clones for %s: %v", filePath, err)), nil
	}

	res := map[string]interface{}{
		"file_path": filePath,
		"threshold": threshold,
		"matches":   clones,
		"count":     len(clones),
	}

	return mcp.NewToolResultJSON(res)
}

func (s *Server) handleGetDiffSummary(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	fileA, errA := request.RequireString("file_a")
	fileB, errB := request.RequireString("file_b")
	if errA != nil || errB != nil || fileA == "" || fileB == "" {
		return mcp.NewToolResultError("file_a and file_b are required"), nil
	}

	diff, err := difftool.DiffFiles(fileA, fileB, s.idx.ShingleK, s.idx.NumPerm)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("diffing %s and %s: %v", fileA, fileB, err)), nil
	}

	return mcp.NewToolResultJSON(diff)
}

func (s *Server) handleReindexWorkspace(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	stats, err := s.idx.Build(ctx)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("reindexing workspace: %v", err)), nil
	}
	return mcp.NewToolResultJSON(stats)
}

// ServeStdio starts the MCP server over standard input and output streams.
func (s *Server) ServeStdio() error {
	return server.ServeStdio(s.mcpServer)
}
