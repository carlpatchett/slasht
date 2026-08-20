package minhash

import (
	"math"
	"math/rand/v2"
	"strings"
	"sync"

	"github.com/cespare/xxhash/v2"
)

// MinHash configuration defaults.
const (
	DefaultNumPerm = 128
	DefaultK       = 4
	mersennePrime  = uint64((1 << 61) - 1)
)

var (
	permOnce sync.Once
	permA    []uint64
	permB    []uint64
)

func initPermutations(numPerm int) {
	// Deterministic PCG PRNG using math/rand/v2
	r := rand.New(rand.NewPCG(1, 2))
	permA = make([]uint64, numPerm)
	permB = make([]uint64, numPerm)
	for i := range numPerm {
		a := r.Uint64()
		if a == 0 {
			a = 1
		}
		b := r.Uint64()
		permA[i] = a
		permB[i] = b
	}
}

// MinHash represents a fixed-size MinHash signature.
type MinHash struct {
	NumPerm int
	Values  []uint64
}

// New creates a new MinHash signature with specified permutation size.
func New(numPerm int) *MinHash {
	if numPerm <= 0 {
		numPerm = DefaultNumPerm
	}
	permOnce.Do(func() {
		initPermutations(DefaultNumPerm)
	})
	vals := make([]uint64, numPerm)
	for i := range vals {
		vals[i] = math.MaxUint64
	}
	return &MinHash{
		NumPerm: numPerm,
		Values:  vals,
	}
}

// Update updates the signature with a shingle byte slice.
func (m *MinHash) Update(b []byte) {
	h := xxhash.Sum64(b)
	for i := range m.NumPerm {
		val := (permA[i]*h + permB[i]) % mersennePrime
		if val < m.Values[i] {
			m.Values[i] = val
		}
	}
}

// UpdateString updates the signature with a string shingle.
func (m *MinHash) UpdateString(s string) {
	m.Update([]byte(s))
}

// Jaccard computes the estimated Jaccard similarity between two signatures.
func (m *MinHash) Jaccard(other *MinHash) float64 {
	if m.NumPerm != other.NumPerm || m.NumPerm == 0 {
		return 0.0
	}
	equal := 0
	for i := range m.NumPerm {
		if m.Values[i] == other.Values[i] && m.Values[i] != math.MaxUint64 {
			equal++
		}
	}
	return float64(equal) / float64(m.NumPerm)
}

// Shingles generates k-shingles over token types.
func Shingles(types []string, k int) []string {
	if k <= 0 {
		k = DefaultK
	}
	if len(types) < k {
		if len(types) == 0 {
			return nil
		}
		var sb strings.Builder
		for i, t := range types {
			if i > 0 {
				sb.WriteByte(0x1F)
			}
			sb.WriteString(t)
		}
		return []string{sb.String()}
	}
	res := make([]string, 0, len(types)-k+1)
	for i := 0; i <= len(types)-k; i++ {
		var sb strings.Builder
		for j := range k {
			if j > 0 {
				sb.WriteByte(0x1F)
			}
			sb.WriteString(types[i+j])
		}
		res = append(res, sb.String())
	}
	return res
}

// ComputeSignature generates a MinHash for a token sequence.
func ComputeSignature(types []string, k, numPerm int) *MinHash {
	mh := New(numPerm)
	for _, shingle := range Shingles(types, k) {
		mh.UpdateString(shingle)
	}
	return mh
}
