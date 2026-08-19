package main

import (
	"fmt"
	"os"

	"github.com/carlpatchett/clone-catcher/pkg/server"
)

func main() {
	root := os.Getenv("CLONE_CATCHER_ROOT")
	if root == "" {
		root, _ = os.Getwd()
	}

	tracePath := os.Getenv("CLONE_CATCHER_TRACE_PATH")

	cfg := server.Config{
		Root:      root,
		TracePath: tracePath,
	}

	srv, err := server.NewServer(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create clone-catcher server: %v\n", err)
		os.Exit(1)
	}

	if err := srv.ServeStdio(); err != nil {
		fmt.Fprintf(os.Stderr, "server error: %v\n", err)
		os.Exit(1)
	}
}
