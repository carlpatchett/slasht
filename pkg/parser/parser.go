package parser

import (
	"path/filepath"
	"strings"
	"sync"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
	tree_sitter_c_sharp "github.com/tree-sitter/tree-sitter-c-sharp/bindings/go"
	tree_sitter_go "github.com/tree-sitter/tree-sitter-go/bindings/go"
	tree_sitter_python "github.com/tree-sitter/tree-sitter-python/bindings/go"
)

// LanguageKey identifies supported programming languages.
type LanguageKey string

const (
	LangPython LanguageKey = "python"
	LangGo     LanguageKey = "go"
	LangCSharp LanguageKey = "csharp"
)

var (
	languagesOnce sync.Once
	pyLang        *tree_sitter.Language
	goLang        *tree_sitter.Language
	csLang        *tree_sitter.Language
)

func initLanguages() {
	pyLang = tree_sitter.NewLanguage(tree_sitter_python.Language())
	goLang = tree_sitter.NewLanguage(tree_sitter_go.Language())
	csLang = tree_sitter.NewLanguage(tree_sitter_c_sharp.Language())
}

// GetLanguage returns the tree-sitter Language definition for the given key.
func GetLanguage(lang LanguageKey) *tree_sitter.Language {
	languagesOnce.Do(initLanguages)
	switch lang {
	case LangPython:
		return pyLang
	case LangGo:
		return goLang
	case LangCSharp:
		return csLang
	default:
		return nil
	}
}

// DetectLanguage maps file extension to LanguageKey.
func DetectLanguage(path string) (LanguageKey, bool) {
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".py":
		return LangPython, true
	case ".go":
		return LangGo, true
	case ".cs":
		return LangCSharp, true
	default:
		return "", false
	}
}

// ParseSource parses the source bytes using a new Parser for the target language.
func ParseSource(lang LanguageKey, data []byte) (*tree_sitter.Tree, error) {
	l := GetLanguage(lang)
	if l == nil {
		return nil, nil
	}
	parser := tree_sitter.NewParser()
	defer parser.Close()
	if err := parser.SetLanguage(l); err != nil {
		return nil, err
	}
	tree := parser.Parse(data, nil)
	return tree, nil
}
