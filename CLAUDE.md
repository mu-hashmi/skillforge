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

1. **Core Skills Install** (`claude_runner.py`) - Writes `.claude/skills/{search-docs,save-skill,deep-dive}/SKILL.md`
2. **Verify Script Bootstrap** (`claude_runner.py`) - Writes `scripts/verify.sh`
3. **Task Contract** (`claude_runner.py`) - Writes `.skillforge/TASK.md`
4. **Claude Code Launch** (`claude_runner.py`) - Runs `claude "<task>" --append-system-prompt "<rules>"`
5. **Retrieval** (`firecrawl_search.py`) - `/search-docs` executes Firecrawl queries and caches results
6. **Deep Crawl** (`firecrawl_crawl.py`) - `/deep-dive` crawls entire doc sites into `.skillforge/knowledge/`
7. **Skill Generation** (`generate_skill.py`) - `/save-skill` generates `.claude/skills/<name>/SKILL.md` with embedded knowledge

### Key Design Decisions

**Claude Code as Coder**: No in-process model loop. The CLI only prepares the repo and launches the interactive `claude` session.

**Verify Script**: `scripts/verify.sh` wraps any test/build command, streams output to terminal AND logs to `.skillforge/last_run.log`. Preserves exit codes via `PIPESTATUS[0]`. Claude writes its chosen verify command to `.skillforge/verify_command.txt` at the start of each task.

**Skill Storage**:
- All skills (core and generated) live in `.claude/skills/<skill-name>/SKILL.md`

**Retrieval Cache**:
- `.skillforge/cache/<timestamp>_search.md` stores Firecrawl search results
- `.skillforge/knowledge/<domain>/` stores crawled documentation

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `cli.py` | Click command, prepares repo and launches Claude Code |
| `claude_runner.py` | Core skills + verify.sh + task contract + launcher |
| `firecrawl_client.py` | Wraps Firecrawl map/crawl/search APIs |
| `firecrawl_search.py` | CLI for Firecrawl queries and cache writes |
| `firecrawl_crawl.py` | CLI for deep doc crawls into knowledge base |
| `generate_skill.py` | Creates skill directory from task + cached knowledge |
| `exceptions.py` | Typed exception hierarchy (all inherit `SkillForgeError`) |
