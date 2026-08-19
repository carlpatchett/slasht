package difftool

import (
	"fmt"
	"os"
	"strings"

	"github.com/carlpatchett/slasht/pkg/minhash"
	"github.com/carlpatchett/slasht/pkg/parser"
	"github.com/carlpatchett/slasht/pkg/structural"
)

// ChangeRegion describes an AST difference between two files.
type ChangeRegion struct {
	Type     string `json:"type"` // "renamed-only" | "structural"
	Opcode   string `json:"opcode"` // "replace" | "delete" | "insert"
	LinesA   [2]int `json:"lines_a"`
	LinesB   [2]int `json:"lines_b"`
	TokensA  []string `json:"tokens_a,omitempty"`
	TokensB  []string `json:"tokens_b,omitempty"`
}

// DiffSummary contains the high-level structural comparison results.
type DiffSummary struct {
	FileA                string         `json:"file_a"`
	FileB                string         `json:"file_b"`
	StructuralSimilarity float64        `json:"structural_similarity"`
	IdenticalStructure   bool           `json:"identical_structure"`
	Differences          []ChangeRegion `json:"differences,omitempty"`
}

// DiffFiles computes the structural diff between two source files.
func DiffFiles(fileA, fileB string, k, numPerm int) (*DiffSummary, error) {
	bytesA, err := os.ReadFile(fileA)
	if err != nil {
		return nil, fmt.Errorf("reading file_a: %w", err)
	}
	bytesB, err := os.ReadFile(fileB)
	if err != nil {
		return nil, fmt.Errorf("reading file_b: %w", err)
	}

	langA, okA := parser.DetectLanguage(fileA)
	langB, okB := parser.DetectLanguage(fileB)
	if !okA || !okB {
		return nil, fmt.Errorf("unsupported language for files: %s, %s", fileA, fileB)
	}

	treeA, err := parser.ParseSource(langA, bytesA)
	if err != nil || treeA == nil {
		return nil, fmt.Errorf("parsing file_a: %w", err)
	}
	defer treeA.Close()

	treeB, err := parser.ParseSource(langB, bytesB)
	if err != nil || treeB == nil {
		return nil, fmt.Errorf("parsing file_b: %w", err)
	}
	defer treeB.Close()

	tokensA := structural.ExtractTokens(treeA.RootNode())
	tokensB := structural.ExtractTokens(treeB.RootNode())

	typesA := structural.TokenTypes(tokensA)
	typesB := structural.TokenTypes(tokensB)

	mhA := minhash.ComputeSignature(typesA, k, numPerm)
	mhB := minhash.ComputeSignature(typesB, k, numPerm)
	sim := mhA.Jaccard(mhB)

	identicalStructure := false
	if len(typesA) == len(typesB) {
		identicalStructure = true
		for i := range typesA {
			if typesA[i] != typesB[i] {
				identicalStructure = false
				break
			}
		}
	}

	summary := &DiffSummary{
		FileA:                fileA,
		FileB:                fileB,
		StructuralSimilarity: sim,
		IdenticalStructure:   identicalStructure,
	}

	if identicalStructure {
		if string(bytesA) != string(bytesB) {
			summary.Differences = []ChangeRegion{
				{
					Type:   "renamed-only",
					Opcode: "equal",
					LinesA: [2]int{1, strings.Count(string(bytesA), "\n") + 1},
					LinesB: [2]int{1, strings.Count(string(bytesB), "\n") + 1},
				},
			}
		}
		return summary, nil
	}

	// Simple Myers diff or token subsequence diff
	diffs := computeTokenDiffs(tokensA, tokensB)
	summary.Differences = diffs
	return summary, nil
}

// computeTokenDiffs calculates coarse AST token difference regions.
func computeTokenDiffs(tokensA, tokensB []structural.StructToken) []ChangeRegion {
	var changes []ChangeRegion
	lenA := len(tokensA)
	lenB := len(tokensB)

	i, j := 0, 0
	for i < lenA && j < lenB {
		if tokensA[i].Type == tokensB[j].Type {
			i++
			j++
			continue
		}

		startA := i
		startB := j
		for i < lenA && j < lenB && tokensA[i].Type != tokensB[j].Type {
			i++
			j++
		}

		lineAStart := tokensA[startA].StartLine
		lineAEnd := tokensA[i-1].EndLine
		lineBStart := tokensB[startB].StartLine
		lineBEnd := tokensB[j-1].EndLine

		var subA, subB []string
		for idx := startA; idx < i; idx++ {
			subA = append(subA, tokensA[idx].Type)
		}
		for idx := startB; idx < j; idx++ {
			subB = append(subB, tokensB[idx].Type)
		}

		changes = append(changes, ChangeRegion{
			Type:     "structural",
			Opcode:   "replace",
			LinesA:   [2]int{lineAStart, lineAEnd},
			LinesB:   [2]int{lineBStart, lineBEnd},
			TokensA:  subA,
			TokensB:  subB,
		})
	}

	if i < lenA {
		changes = append(changes, ChangeRegion{
			Type:    "structural",
			Opcode:  "delete",
			LinesA:  [2]int{tokensA[i].StartLine, tokensA[lenA-1].EndLine},
			LinesB:  [2]int{0, 0},
			TokensA: structural.TokenTypes(tokensA[i:]),
		})
	}
	if j < lenB {
		changes = append(changes, ChangeRegion{
			Type:    "structural",
			Opcode:  "insert",
			LinesA:  [2]int{0, 0},
			LinesB:  [2]int{tokensB[j].StartLine, tokensB[lenB-1].EndLine},
			TokensB: structural.TokenTypes(tokensB[j:]),
		})
	}

	return changes
}
