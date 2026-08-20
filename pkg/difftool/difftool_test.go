package difftool

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDiffFiles(t *testing.T) {
	tmp := t.TempDir()
	fileA := filepath.Join(tmp, "a.py")
	fileB := filepath.Join(tmp, "b.py")
	fileC := filepath.Join(tmp, "c.py")

	codeA := "def calculate_tax(amount):\n    rate = 0.2\n    return amount * rate\n"
	codeB := "def compute_fee(total):\n    multiplier = 0.2\n    return total * multiplier\n" // Clone (renamed)
	codeC := "def log_message(msg):\n    print(msg)\n    return True\n"                       // Different structure

	os.WriteFile(fileA, []byte(codeA), 0644)
	os.WriteFile(fileB, []byte(codeB), 0644)
	os.WriteFile(fileC, []byte(codeC), 0644)

	diffAB, err := DiffFiles(fileA, fileB, 4, 128)
	if err != nil {
		t.Fatalf("DiffFiles(A, B) failed: %v", err)
	}
	if !diffAB.IdenticalStructure {
		t.Errorf("expected A and B to have identical structure")
	}
	if diffAB.StructuralSimilarity != 1.0 {
		t.Errorf("expected similarity 1.0, got %f", diffAB.StructuralSimilarity)
	}

	diffAC, err := DiffFiles(fileA, fileC, 4, 128)
	if err != nil {
		t.Fatalf("DiffFiles(A, C) failed: %v", err)
	}
	if diffAC.IdenticalStructure {
		t.Errorf("expected A and C to NOT have identical structure")
	}
}
