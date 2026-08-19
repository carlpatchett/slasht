---
description: "Use structural clone detection before crawling files for duplicate code or refactoring"
condition: "\\b(duplicate|duplication|clones?|copy-pasted?|boilerplate|redundant.*code|similar.*files)\\b"
scope: "text"
---

## Structural Code Search — Use clone-catcher Before Manual Crawling

When searching for duplicated logic, repeated boilerplate, or candidate files for refactoring across Python, Go, or C#:
- NEVER crawl or read files sequentially with `read`, `grep`, or custom scripts to find duplicate structures.
- ALWAYS call `find_duplicate_groups` first (or `find_structural_clones` for a specific file). It clusters identical code skeletons across the workspace in ~100ms and returns the file groups with preview snippets.
