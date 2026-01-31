---
name: search-docs
description: Firecrawl-powered docs search. Use when build failed, test failure, compiler error, CUDA error, import error, linker error, segfault, runtime error, stack trace, or any error output needs targeted documentation lookup.
allowed-tools:
  - Bash: 'python -m skillforge.firecrawl_search "$ARGUMENTS"'
---

# /search-docs

Use this when you have raw stderr/error text or a focused query.

Run:
!python -m skillforge.firecrawl_search "$ARGUMENTS"

The command writes full results to .skillforge/cache/<timestamp>_search.md and prints:
- Top findings
- Cache file path
- Exact search query used
