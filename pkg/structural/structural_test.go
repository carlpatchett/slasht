package structural

import (
	"testing"

	"github.com/carlpatchett/slasht/pkg/parser"
)

func TestExtractTokens(t *testing.T) {
	code := `
def calculate_price(quantity, unit_price):
    if quantity > 10:
        discount = 0.1
        return quantity * unit_price * (1 - discount)
    return quantity * unit_price
`
	tree, err := parser.ParseSource(parser.LangPython, []byte(code))
	if err != nil || tree == nil {
		t.Fatalf("ParseSource failed: %v", err)
	}
	defer tree.Close()

	tokens := ExtractTokens(tree.RootNode())
	types := TokenTypes(tokens)

	if len(tokens) == 0 {
		t.Fatalf("expected structural tokens, got 0")
	}

	// Structural tokens should exclude identifier names (calculate_price, quantity, discount)
	for _, tok := range types {
		if tok == "identifier" || tok == "comment" || tok == "number" {
			t.Errorf("found pruned token type in stream: %s", tok)
		}
	}

	t.Logf("Extracted %d structural tokens: %v", len(tokens), types)
}
