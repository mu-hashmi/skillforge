# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

This is a hackathon project for **Hack the Stackathon** - a builder-focused hackathon for data, AI, and modern tooling hosted by Firecrawl, Reducto, and Resend. This project is doing the Firecrawl track.

**Judging priorities:**
- Real data ingestion (live inputs, not mock data)
- Working systems over polish
- Thoughtful tradeoffs with clear decisions about scope

**Development philosophy:**
- Scalability is NOT a priority
- Backwards compatibility is unnecessary
- No silent fallbacks or hidden failures
- Errors should crash loudly, not degrade gracefully

## Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run skillforge "task description" --seed https://docs.example.com

# Run with verbose output
uv run skillforge "build CUDA kernels" --seed https://docs.nvidia.com/cuda -v

# Options
--model          # Model to use (default: claude-sonnet-4-20250514)
--max-attempts   # Max teacher retries (default: 5)
--corpus-limit   # Max pages to crawl (default: 50)
```

## Environment Variables

Required:
- `ANTHROPIC_API_KEY` - Claude API key
- `FIRECRAWL_API_KEY` - Firecrawl API key

## Architecture

**Skillforge** generates agent skills from documentation. It crawls docs, runs iterative Claude sessions to complete a task, fills knowledge gaps automatically, and outputs a SKILL.md file.

### Core Flow (5 steps)

1. **Config Validation** (`config.py`) - Checks API keys exist
2. **Source Discovery** (`discovery.py`) - Maps seed URL, filters to docs paths, searches for supplementary content
3. **Corpus Building** (`corpus.py`) - Crawls sources via Firecrawl, saves as markdown with YAML frontmatter
4. **Teacher Session** (`teacher.py`) - Iterative loop where Claude attempts the task. Model responds via tool calls, analyzer checks completeness, and any gaps are searched to enrich corpus before retrying
5. **Skill Generation** (`generator.py`) - Synthesizes successful trace into SKILL.md + tests.json

### Key Design Decisions

**Teacher Protocol**: Model must call exactly one tool:
- `task_complete` with a full solution and summary
- `request_documentation` with a specific search query and reason

If the analyzer cannot confirm completeness or identify a gap, the system raises `AnalysisError` rather than guessing.

**Corpus Storage**:
- `corpus/corpus_<task>_<timestamp>/` contains numbered markdown files
- `manifest.json` tracks metadata and token estimates
- Pages include source URL/title in YAML frontmatter

**Output**:
- `skills/<skill_name>/SKILL.md` - Main skill documentation
- `skills/<skill_name>/tests.json` - Verification test cases
- `skills/<skill_name>/skill_manifest.json` - Metadata

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `cli.py` | Click command, orchestrates 5-step flow |
| `discovery.py` | URL mapping, docs filtering, supplementary search |
| `corpus.py` | Crawl → markdown conversion, manifest management |
| `firecrawl_client.py` | Wraps Firecrawl map/crawl/search APIs |
| `teacher.py` | Retry loop with gap detection and corpus enrichment |
| `generator.py` | SKILL.md synthesis from successful trace |
| `exceptions.py` | Typed exception hierarchy (all inherit `SkillForgeError`) |
