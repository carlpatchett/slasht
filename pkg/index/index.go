// Package index provides AST shingle fingerprinting and LSH clone indexing.
package index

import (
	"context"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"go.opentelemetry.io/otel/attribute"

	"github.com/carlpatchett/slasht/pkg/minhash"
	"github.com/carlpatchett/slasht/pkg/parser"
	"github.com/carlpatchett/slasht/pkg/structural"
	"github.com/carlpatchett/slasht/pkg/telemetry"
)

var defaultExcludes = map[string]struct{}{
	".git":          {},
	".jj":           {},
	"node_modules":  {},
	".venv":         {},
	"venv":          {},
	"__pycache__":   {},
	"dist":          {},
	"build":         {},
	"target":        {},
	".ruff_cache":   {},
	".pytest_cache": {},
}

// FileMeta contains metadata about an indexed file.
type FileMeta struct {
	Language          string `json:"language"`
	LineCount         int    `json:"line_count"`
	TokenCount        int    `json:"token_count"`
	StructuralSummary string `json:"structural_summary"`
}

// FileRecord represents an indexed file's MinHash and metadata.
type FileRecord struct {
	Key     string
	MinHash *minhash.MinHash
	Meta    FileMeta
}

// CloneIndex manages workspace indexing, MinHash signatures, and clone clustering.
type CloneIndex struct {
	mu           sync.RWMutex
	Root         string
	ShingleK     int
	NumPerm      int
	MaxFileBytes int64
	Excludes     map[string]struct{}
	Tracer       *telemetry.Tracer

	records map[string]*FileRecord
	forest  *minhash.LSHForest
	built   bool
}

// NewCloneIndex creates a new index for a workspace root.
func NewCloneIndex(root string, tracer *telemetry.Tracer) *CloneIndex {
	if root == "" {
		root, _ = os.Getwd()
	}
	absRoot, err := filepath.Abs(root)
	if err == nil {
		root = absRoot
	}
	return &CloneIndex{
		Root:         root,
		ShingleK:     minhash.DefaultK,
		NumPerm:      minhash.DefaultNumPerm,
		MaxFileBytes: 500 * 1024,
		Excludes:     defaultExcludes,
		Tracer:       tracer,
		records:      make(map[string]*FileRecord),
	}
}

// Key converts an absolute or relative path to a repo-relative key.
func (idx *CloneIndex) Key(path string) string {
	rel, err := filepath.Rel(idx.Root, path)
	if err != nil {
		return filepath.ToSlash(path)
	}
	return filepath.ToSlash(rel)
}

// Build traverses the workspace and indexes all supported source files.
func (idx *CloneIndex) Build(ctx context.Context) (map[string]interface{}, error) {
	idx.mu.Lock()
	defer idx.mu.Unlock()

	_, span := idx.Tracer.Start(ctx, "slasht.index.build", attribute.String("root", idx.Root))
	if span != nil {
		defer span.End()
	}
	started := time.Now()
	idx.records = make(map[string]*FileRecord)
	idx.forest = minhash.NewLSHForest(idx.NumPerm, 8)

	var files []string
	var skipped []string
	langCounts := make(map[string]int)

	err := filepath.WalkDir(idx.Root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if _, excluded := idx.Excludes[d.Name()]; excluded {
				return filepath.SkipDir
			}
			return nil
		}

		lang, ok := parser.DetectLanguage(path)
		if !ok {
			return nil
		}

		info, err := d.Info()
		if err != nil || info.Size() > idx.MaxFileBytes {
			skipped = append(skipped, idx.Key(path))
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			skipped = append(skipped, idx.Key(path))
			return nil
		}

		tree, err := parser.ParseSource(lang, data)
		if err != nil || tree == nil {
			skipped = append(skipped, idx.Key(path))
			return nil
		}
		defer tree.Close()

		tokens := structural.ExtractTokens(tree.RootNode())
		types := structural.TokenTypes(tokens)
		if len(types) == 0 {
			skipped = append(skipped, idx.Key(path))
			return nil
		}

		var summaryParts []string
		for _, tok := range types {
			if strings.Contains(tok, "statement") ||
				strings.Contains(tok, "definition") ||
				strings.Contains(tok, "declaration") ||
				strings.Contains(tok, "handler") {
				summaryParts = append(summaryParts, tok)
			}
		}
		summary := strings.Join(summaryParts, " -> ")
		if len(summary) > 120 {
			summary = summary[:120]
		}

		mh := minhash.ComputeSignature(types, idx.ShingleK, idx.NumPerm)
		k := idx.Key(path)
		rec := &FileRecord{
			Key:     k,
			MinHash: mh,
			Meta: FileMeta{
				Language:          string(lang),
				LineCount:         strings.Count(string(data), "\n") + 1,
				TokenCount:        len(types),
				StructuralSummary: summary,
			},
		}

		idx.records[k] = rec
		idx.forest.Add(k, mh)
		files = append(files, k)
		langCounts[string(lang)]++

		return nil
	})

	idx.forest.Index()
	idx.built = true
	durationMs := float64(time.Since(started).Microseconds()) / 1000.0

	sort.Strings(files)
	sort.Strings(skipped)

	return map[string]interface{}{
		"files":       files,
		"skipped":     skipped,
		"languages":   langCounts,
		"duration_ms": durationMs,
	}, err
}

// EnsureBuilt ensures the workspace has been indexed.
func (idx *CloneIndex) EnsureBuilt(ctx context.Context) error {
	idx.mu.RLock()
	built := idx.built
	idx.mu.RUnlock()
	if !built {
		_, err := idx.Build(ctx)
		return err
	}
	return nil
}

// FindClones queries for files structurally similar to target path.
func (idx *CloneIndex) FindClones(ctx context.Context, targetPath string, threshold float64, maxK int) ([]map[string]interface{}, error) {
	if err := idx.EnsureBuilt(ctx); err != nil {
		return nil, err
	}

	idx.mu.RLock()
	defer idx.mu.RUnlock()

	_, span := idx.Tracer.Start(ctx, "find_structural_clones",
		attribute.String("file_path", targetPath),
		attribute.Float64("threshold", threshold),
	)
	if span != nil {
		defer span.End()
	}
	k := idx.Key(targetPath)
	rec, exists := idx.records[k]

	var targetMH *minhash.MinHash
	if exists {
		targetMH = rec.MinHash
	} else {
		// Parse on the fly if not indexed
		absPath := targetPath
		if !filepath.IsAbs(absPath) {
			absPath = filepath.Join(idx.Root, targetPath)
		}
		data, err := os.ReadFile(absPath)
		if err != nil {
			return nil, fmt.Errorf("reading file: %w", err)
		}
		lang, ok := parser.DetectLanguage(absPath)
		if !ok {
			return nil, fmt.Errorf("unsupported language for %s", targetPath)
		}
		tree, err := parser.ParseSource(lang, data)
		if err != nil || tree == nil {
			return nil, fmt.Errorf("parsing file: %w", err)
		}
		defer tree.Close()
		tokens := structural.ExtractTokens(tree.RootNode())
		types := structural.TokenTypes(tokens)
		targetMH = minhash.ComputeSignature(types, idx.ShingleK, idx.NumPerm)
	}

	candidates := idx.forest.Query(targetMH, threshold, maxK)
	matches := make([]map[string]interface{}, 0, len(candidates))
	for _, c := range candidates {
		meta := idx.records[c.Key].Meta
		matches = append(matches, map[string]interface{}{
			"path":               c.Key,
			"similarity":         c.Similarity,
			"language":           meta.Language,
			"token_count":        meta.TokenCount,
			"line_count":         meta.LineCount,
			"structural_summary": meta.StructuralSummary,
		})
	}

	return matches, nil
}

// DuplicateGroup represents a cluster of structurally identical/similar files.
type DuplicateGroup struct {
	Size              int            `json:"size"`
	Files             []string       `json:"files"`
	MeanSimilarity    float64        `json:"mean_similarity"`
	MinSimilarity     float64        `json:"min_similarity"`
	Languages         map[string]int `json:"languages"`
	SampleFile        string         `json:"sample_file"`
	SampleSnippet     string         `json:"sample_snippet"`
	StructuralSummary string         `json:"structural_summary"`
}

// DuplicateGroups finds all connected components of structural clones.
func (idx *CloneIndex) DuplicateGroups(ctx context.Context, threshold float64, maxGroups, maxFilesPerGroup int) ([]DuplicateGroup, error) {
	if err := idx.EnsureBuilt(ctx); err != nil {
		return nil, err
	}

	idx.mu.RLock()
	defer idx.mu.RUnlock()

	_, span := idx.Tracer.Start(ctx, "slasht.index.groups", attribute.Float64("threshold", threshold))
	if span != nil {
		defer span.End()
	}
	if maxGroups <= 0 {
		maxGroups = 25
	}
	if maxFilesPerGroup <= 0 {
		maxFilesPerGroup = 20
	}

	// Connected components via disjoint-set (Union-Find)
	parent := make(map[string]string)
	for k := range idx.records {
		parent[k] = k
	}

	var find func(string) string
	find = func(i string) string {
		if parent[i] == i {
			return i
		}
		parent[i] = find(parent[i])
		return parent[i]
	}
	union := func(i, j string) {
		rootI := find(i)
		rootJ := find(j)
		if rootI != rootJ {
			parent[rootI] = rootJ
		}
	}

	for k, rec := range idx.records {
		matches := idx.forest.Query(rec.MinHash, threshold, 50)
		for _, m := range matches {
			if m.Key != k {
				union(k, m.Key)
			}
		}
	}

	components := make(map[string][]string)
	for k := range idx.records {
		root := find(k)
		components[root] = append(components[root], k)
	}
	groups := make([]DuplicateGroup, 0, len(components))
	for _, members := range components {
		if len(members) < 2 {
			continue
		}
		sort.Strings(members)
		langCount := make(map[string]int)
		for _, m := range members {
			langCount[idx.records[m].Meta.Language]++
		}

		sampleFile := members[0]
		samplePath := filepath.Join(idx.Root, sampleFile)
		sampleSnippet := ""
		if data, err := os.ReadFile(samplePath); err == nil {
			lines := strings.Split(string(data), "\n")
			var codeLines []string
			for _, line := range lines {
				trimmed := strings.TrimSpace(line)
				if trimmed != "" && !strings.HasPrefix(trimmed, "//") && !strings.HasPrefix(trimmed, "#") && !strings.HasPrefix(trimmed, "/*") && !strings.HasPrefix(trimmed, "*") {
					codeLines = append(codeLines, strings.TrimRight(line, "\r\n"))
				}
			}
			if len(codeLines) > 4 {
				codeLines = codeLines[:4]
			}
			sampleSnippet = strings.Join(codeLines, "\n")
			if len(sampleSnippet) > 300 {
				sampleSnippet = sampleSnippet[:300]
			}
		}

		meta := idx.records[sampleFile].Meta
		limitFiles := members
		if len(limitFiles) > maxFilesPerGroup {
			limitFiles = limitFiles[:maxFilesPerGroup]
		}

		groups = append(groups, DuplicateGroup{
			Size:              len(members),
			Files:             limitFiles,
			MeanSimilarity:    1.0, // High-confidence cluster
			MinSimilarity:     threshold,
			Languages:         langCount,
			SampleFile:        sampleFile,
			SampleSnippet:     sampleSnippet,
			StructuralSummary: meta.StructuralSummary,
		})
	}

	sort.Slice(groups, func(i, j int) bool {
		return groups[i].Size > groups[j].Size
	})

	if len(groups) > maxGroups {
		groups = groups[:maxGroups]
	}

	return groups, nil
}
