package structural

import (
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

var skipExact = map[string]struct{}{
	"identifier":       {},
	"comment":          {},
	"docstring":        {},
	"string":           {},
	"string_content":   {},
	"escape_sequence":  {},
	"interpolation":    {},
	"format_spec":      {},
	"type_conversion":  {},
	"number":           {},
	"integer":          {},
	"float":            {},
	"imaginary":        {},
	"rune":             {},
	"none":             {},
	"true":             {},
	"false":            {},
	"null":             {},
	"nil":              {},
	"boolean":          {},
}

var skipSuffixes = []string{
	"_identifier",
	"_literal",
	"_comment",
}

var punctuation = map[string]struct{}{
	"(": {}, ")": {}, "[": {}, "]": {}, "{": {}, "}": {},
	",": {}, ":": {}, ";": {}, ".": {}, "...": {}, "@": {},
	"\\": {}, "`": {}, "$": {},
}

// StructToken represents a single structural AST token with line bounds (1-based).
type StructToken struct {
	Type      string `json:"type"`
	StartLine int    `json:"start_line"`
	EndLine   int    `json:"end_line"`
}

func isPruned(kind string) bool {
	if _, ok := skipExact[kind]; ok {
		return true
	}
	for _, suffix := range skipSuffixes {
		if strings.HasSuffix(kind, suffix) {
			return true
		}
	}
	return false
}

// ExtractTokens performs zero-allocation cursor traversal over the AST root node,
// extracting language-agnostic structural tokens while ignoring names and literal values.
func ExtractTokens(root *tree_sitter.Node) []StructToken {
	if root == nil {
		return nil
	}
	cursor := root.Walk()
	defer cursor.Close()

	var tokens []StructToken

	if !cursor.GotoFirstChild() {
		return tokens
	}

	for {
		node := cursor.Node()
		kind := node.Kind()
		isNamed := node.IsNamed()
		startRow := int(node.StartPosition().Row) + 1
		endRow := int(node.EndPosition().Row) + 1

		pruned := false
		if !isNamed {
			if _, isPunct := punctuation[kind]; !isPunct {
				tokens = append(tokens, StructToken{
					Type:      kind,
					StartLine: startRow,
					EndLine:   endRow,
				})
			}
		} else if isPruned(kind) {
			pruned = true
		} else {
			tokens = append(tokens, StructToken{
				Type:      kind,
				StartLine: startRow,
				EndLine:   endRow,
			})
		}

		if !pruned && cursor.GotoFirstChild() {
			continue
		}

		if cursor.GotoNextSibling() {
			continue
		}

		backtracked := false
		for cursor.GotoParent() {
			parentNode := cursor.Node()
			if parentNode.Equals(*root) {
				backtracked = true
				break
			}
			if cursor.GotoNextSibling() {
				backtracked = true
				break
			}
		}

		if (backtracked && cursor.Node().Equals(*root)) || !backtracked {
			break
		}
	}

	return tokens
}

// TokenTypes extracts the string types from a slice of StructToken.
func TokenTypes(tokens []StructToken) []string {
	res := make([]string, len(tokens))
	for i, t := range tokens {
		res[i] = t.Type
	}
	return res
}
