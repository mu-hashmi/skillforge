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
uv run skillforge "task description"
```

## Environment Variables

Required:
- `FIRECRAWL_API_KEY` - Firecrawl API key

## Architecture

**Skillforge** launches Claude Code as the coder, installs core skills in the target repo, and provides Firecrawl retrieval + a simple skill generator.

### Core Flow

1. **Core Skills Install** (`claude_runner.py`) - Writes `.claude/skills/skillforge-core/*/SKILL.md`
2. **Task Contract** (`claude_runner.py`) - Writes `.skillforge/TASK.md`
3. **Claude Code Launch** (`claude_runner.py`) - Runs `claude "<task>" --append-system-prompt "<rules>"`
4. **Retrieval** (`firecrawl_search.py`) - `/search-docs` executes Firecrawl queries and caches results
5. **Skill Generation** (`generate_skill.py`) - `/save-skill` generates `.claude/skills/<name>/SKILL.md` and updates `.skillforge/registry.json`

### Key Design Decisions

**Claude Code as Coder**: No in-process model loop. The CLI only prepares the repo and launches the interactive `claude` session.

**Skill Storage**:
- Core skills live in `.claude/skills/skillforge-core/`
- Generated skills live in `.claude/skills/<skill-name>/SKILL.md`

**Retrieval Cache**:
- `.skillforge/cache/<timestamp>_search.md` stores Firecrawl results.

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `cli.py` | Click command, prepares repo and launches Claude Code |
| `claude_runner.py` | Core skills + task contract + launcher |
| `firecrawl_client.py` | Wraps Firecrawl map/crawl/search APIs |
| `firecrawl_search.py` | CLI for Firecrawl queries and cache writes |
| `generate_skill.py` | Creates skill directory from task + trace |
| `exceptions.py` | Typed exception hierarchy (all inherit `SkillForgeError`) |
