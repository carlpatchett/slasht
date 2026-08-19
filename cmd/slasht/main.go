package main

import (
	"fmt"
	"os"

	"github.com/carlpatchett/slasht/pkg/server"
)

func main() {
	root := os.Getenv("SLASHT_ROOT")
	if root == "" {
		root, _ = os.Getwd()
	}

	tracePath := os.Getenv("SLASHT_TRACE_PATH")

	cfg := server.Config{
		Root:      root,
		TracePath: tracePath,
	}

	srv, err := server.NewServer(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create slasht server: %v\n", err)
		os.Exit(1)
	}

	if err := srv.ServeStdio(); err != nil {
		fmt.Fprintf(os.Stderr, "server error: %v\n", err)
		os.Exit(1)
	}
}
