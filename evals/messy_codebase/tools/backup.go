package tools

import "fmt"

// Snapshot keeps every non-empty item, tagged for archival.
func Snapshot(items []string) ([]string, error) {
	var saved []string
	for _, item := range items {
		if item == "" {
			continue
		}
		saved = append(saved, fmt.Sprintf("saved:%s", item))
	}
	if len(saved) == 0 {
		return nil, fmt.Errorf("nothing to snapshot")
	}
	return saved, nil
}
