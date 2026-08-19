package minhash

import (
	"testing"
)

func TestMinHashIdenticalAndDisjoint(t *testing.T) {
	seqA := []string{"func", "ident", "params", "block", "return"}
	seqB := []string{"func", "ident", "params", "block", "return"}
	seqC := []string{"struct", "field", "type", "tag"}

	mhA := ComputeSignature(seqA, 2, 128)
	mhB := ComputeSignature(seqB, 2, 128)
	mhC := ComputeSignature(seqC, 2, 128)

	simAB := mhA.Jaccard(mhB)
	if simAB != 1.0 {
		t.Errorf("expected Jaccard(A, B) = 1.0, got %f", simAB)
	}

	simAC := mhA.Jaccard(mhC)
	if simAC > 0.1 {
		t.Errorf("expected Jaccard(A, C) <= 0.1, got %f", simAC)
	}
}

func TestLSHForestQuery(t *testing.T) {
	forest := NewLSHForest(128, 8)

	seq1 := []string{"a", "b", "c", "d", "e", "f", "g", "h"}
	seq2 := []string{"a", "b", "c", "d", "e", "f", "g", "h"} // Identical
	seq3 := []string{"a", "b", "c", "d", "x", "y", "z", "w"} // Partial
	seq4 := []string{"1", "2", "3", "4", "5", "6", "7", "8"} // Disjoint

	mh1 := ComputeSignature(seq1, 3, 128)
	mh2 := ComputeSignature(seq2, 3, 128)
	mh3 := ComputeSignature(seq3, 3, 128)
	mh4 := ComputeSignature(seq4, 3, 128)

	forest.Add("file1.go", mh1)
	forest.Add("file2.go", mh2)
	forest.Add("file3.go", mh3)
	forest.Add("file4.go", mh4)
	forest.Index()

	results := forest.Query(mh1, 0.9, 10)
	if len(results) < 2 {
		t.Fatalf("expected at least 2 results >= 0.9, got %d", len(results))
	}
	if results[0].Key != "file1.go" && results[0].Key != "file2.go" {
		t.Errorf("top match should be file1 or file2, got %s", results[0].Key)
	}
	if results[0].Similarity != 1.0 {
		t.Errorf("similarity should be 1.0, got %f", results[0].Similarity)
	}
}
