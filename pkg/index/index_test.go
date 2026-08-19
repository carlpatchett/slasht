package index

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/carlpatchett/clone-catcher/pkg/telemetry"
)

func TestCloneIndexPolyglot(t *testing.T) {
	tmp := t.TempDir()

	// Python clone pair
	py1 := filepath.Join(tmp, "py1.py")
	py2 := filepath.Join(tmp, "py2.py")
	codePy1 := "def auth_user(u, p):\n    if u == 'admin':\n        return True\n    return False\n"
	codePy2 := "def check_login(username, password):\n    if username == 'root':\n        return True\n    return False\n"
	os.WriteFile(py1, []byte(codePy1), 0644)
	os.WriteFile(py2, []byte(codePy2), 0644)

	// Go clone pair
	go1 := filepath.Join(tmp, "go1.go")
	go2 := filepath.Join(tmp, "go2.go")
	codeGo1 := "package auth\nfunc ValidateToken(t string) bool {\n    if t != \"\" {\n        return true\n    }\n    return false\n}\n"
	codeGo2 := "package token\nfunc CheckSession(s string) bool {\n    if s != \"\" {\n        return true\n    }\n    return false\n}\n"
	os.WriteFile(go1, []byte(codeGo1), 0644)
	os.WriteFile(go2, []byte(codeGo2), 0644)

	// C# clone pair
	cs1 := filepath.Join(tmp, "Cs1.cs")
	cs2 := filepath.Join(tmp, "Cs2.cs")
	codeCs1 := "class UserAuth {\n    public bool Check(string x) {\n        if (x != null) { return true; }\n        return false;\n    }\n}\n"
	codeCs2 := "class RoleAuth {\n    public bool Check(string y) {\n        if (y != null) { return true; }\n        return false;\n    }\n}\n"
	os.WriteFile(cs1, []byte(codeCs1), 0644)
	os.WriteFile(cs2, []byte(codeCs2), 0644)

	// Noise file
	noise := filepath.Join(tmp, "noise.go")
	os.WriteFile(noise, []byte("package noise\ntype Config struct { Port int; Host string }\n"), 0644)

	tr, _ := telemetry.InitTracer("test", "")
	idx := NewCloneIndex(tmp, tr)

	ctx := context.Background()
	stats, err := idx.Build(ctx)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}

	files := stats["files"].([]string)
	if len(files) != 7 {
		t.Fatalf("expected 7 indexed files, got %d (%v)", len(files), files)
	}

	groups, err := idx.DuplicateGroups(ctx, 0.9, 25, 20)
	if err != nil {
		t.Fatalf("DuplicateGroups failed: %v", err)
	}

	if len(groups) != 3 {
		t.Fatalf("expected 3 duplicate groups (1 py, 1 go, 1 cs), got %d", len(groups))
	}

	clones, err := idx.FindClones(ctx, "py1.py", 0.9, 10)
	if err != nil {
		t.Fatalf("FindClones failed: %v", err)
	}
	if len(clones) != 2 {
		t.Fatalf("expected 2 clones for py1.py (self + py2.py), got %d", len(clones))
	}
}
