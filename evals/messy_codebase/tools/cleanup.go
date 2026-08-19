package tools

import "fmt"

// Prune drops every blank entry, tagging what survives.
func Prune(entries []string) ([]string, error) {
	var kept []string
	for _, entry := range entries {
		if entry == "" {
			continue
		}
		kept = append(kept, fmt.Sprintf("kept:%s", entry))
	}
	if len(kept) == 0 {
		return nil, fmt.Errorf("nothing survived pruning")
	}
	return kept, nil
}
