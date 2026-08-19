package parser

import (
	"testing"
)

func TestDetectLanguage(t *testing.T) {
	cases := []struct {
		path string
		want LanguageKey
		ok   bool
	}{
		{"foo/bar.py", LangPython, true},
		{"main.go", LangGo, true},
		{"Service.cs", LangCSharp, true},
		{"script.js", "", false},
		{"README.md", "", false},
	}

	for _, c := range cases {
		got, ok := DetectLanguage(c.path)
		if ok != c.ok || got != c.want {
			t.Errorf("DetectLanguage(%q) = (%v, %v); want (%v, %v)", c.path, got, ok, c.want, c.ok)
		}
	}
}

func TestParseSourceAllLanguages(t *testing.T) {
	pyTree, err := ParseSource(LangPython, []byte("def hello(): return 42\n"))
	if err != nil || pyTree == nil {
		t.Fatalf("ParseSource Python failed: %v", err)
	}
	defer pyTree.Close()
	if pyTree.RootNode().Kind() != "module" {
		t.Errorf("expected module, got %s", pyTree.RootNode().Kind())
	}

	goTree, err := ParseSource(LangGo, []byte("package main\nfunc main() {}\n"))
	if err != nil || goTree == nil {
		t.Fatalf("ParseSource Go failed: %v", err)
	}
	defer goTree.Close()
	if goTree.RootNode().Kind() != "source_file" {
		t.Errorf("expected source_file, got %s", goTree.RootNode().Kind())
	}

	csTree, err := ParseSource(LangCSharp, []byte("class Program { static void Main() {} }\n"))
	if err != nil || csTree == nil {
		t.Fatalf("ParseSource C# failed: %v", err)
	}
	defer csTree.Close()
	if csTree.RootNode().Kind() != "compilation_unit" {
		t.Errorf("expected compilation_unit, got %s", csTree.RootNode().Kind())
	}
}
