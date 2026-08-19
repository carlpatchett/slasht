package minhash

import (
	"encoding/binary"
	"sort"
	"sync"
)

// LSHForest implements an LSH Forest index for sub-linear similarity search.
type LSHForest struct {
	NumPerm int
	L       int // Number of prefix trees / bands
	K       int // Max prefix length (NumPerm / L)

	mu       sync.RWMutex
	keys     []string
	keyIndex map[string]int
	minhashes []*MinHash
	hashtables [][]map[string][]int
	indexed  bool
}

// NewLSHForest creates a new LSHForest index.
func NewLSHForest(numPerm, l int) *LSHForest {
	if numPerm <= 0 {
		numPerm = DefaultNumPerm
	}
	if l <= 0 {
		l = 8
	}
	k := numPerm / l
	if k <= 0 {
		k = 1
	}

	hashtables := make([][]map[string][]int, l)
	for i := range l {
		hashtables[i] = make([]map[string][]int, k)
		for j := range k {
			hashtables[i][j] = make(map[string][]int)
		}
	}

	return &LSHForest{
		NumPerm:    numPerm,
		L:          l,
		K:          k,
		keyIndex:   make(map[string]int),
		hashtables: hashtables,
	}
}

func hashKey(vals []uint64) string {
	buf := make([]byte, len(vals)*8)
	for i, v := range vals {
		binary.LittleEndian.PutUint64(buf[i*8:], v)
	}
	return string(buf)
}

// Add adds a key and its MinHash signature to the forest.
func (f *LSHForest) Add(key string, m *MinHash) {
	f.mu.Lock()
	defer f.mu.Unlock()

	idx := len(f.keys)
	f.keys = append(f.keys, key)
	f.keyIndex[key] = idx
	f.minhashes = append(f.minhashes, m)
	f.indexed = false

	for band := range f.L {
		start := band * f.K
		for prefixLen := 1; prefixLen <= f.K; prefixLen++ {
			end := start + prefixLen
			if end > len(m.Values) {
				end = len(m.Values)
			}
			h := hashKey(m.Values[start:end])
			f.hashtables[band][prefixLen-1][h] = append(f.hashtables[band][prefixLen-1][h], idx)
		}
	}
}

// Index finalizes the forest index.
func (f *LSHForest) Index() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.indexed = true
}

// Candidate represents a potential match with exact Jaccard similarity.
type Candidate struct {
	Key        string  `json:"key"`
	Similarity float64 `json:"similarity"`
}

// Query returns keys from the index that meet or exceed the similarity threshold.
func (f *LSHForest) Query(m *MinHash, threshold float64, maxK int) []Candidate {
	f.mu.RLock()
	defer f.mu.RUnlock()

	if len(f.keys) == 0 {
		return nil
	}
	if maxK <= 0 {
		maxK = 50
	}

	seen := make(map[int]struct{})
	var candidates []int

	// Search prefix trees from deepest (exact match) to shallower
	for prefixLen := f.K; prefixLen >= 1; prefixLen-- {
		for band := range f.L {
			start := band * f.K
			end := start + prefixLen
			if end > len(m.Values) {
				end = len(m.Values)
			}
			h := hashKey(m.Values[start:end])
			if matches, ok := f.hashtables[band][prefixLen-1][h]; ok {
				for _, idx := range matches {
					if _, already := seen[idx]; !already {
						seen[idx] = struct{}{}
						candidates = append(candidates, idx)
					}
				}
			}
		}
		if len(candidates) >= maxK {
			break
		}
	}

	var results []Candidate
	for _, idx := range candidates {
		sim := m.Jaccard(f.minhashes[idx])
		if sim >= threshold {
			results = append(results, Candidate{
				Key:        f.keys[idx],
				Similarity: sim,
			})
		}
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].Similarity > results[j].Similarity
	})

	return results
}
