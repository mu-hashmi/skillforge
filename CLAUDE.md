# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

This is a hackathon project for **Hack the Stackathon** - a builder-focused hackathon for data, AI, and modern tooling hosted by Firecrawl, Reducto, and Resend.

**Judging priorities (optimize for these first):**
- Real data ingestion (live inputs, not mock data)
- Working systems over polish
- Thoughtful tradeoffs with clear decisions about scope

**Development philosophy (intentional constraints):**
- Scalability is NOT a priority
- Backwards compatibility is unnecessary
- No silent fallbacks or hidden failures
- Errors should crash loudly, not degrade gracefully

**Demo readiness (minimum bar):**
- Demonstrate a run that crawls real URLs and produces a real skill output folder.
- Show logs that make the pipeline steps obvious to a judge.
- Prefer a smaller, reliable seed over a huge docs site.

## Source Authority & Weighting (for ingestion quality)
When using Firecrawl, we must prioritize sources using **Domain Layering**:
- **Tier 1 (Critical):** Official documentation (e.g., `docs.*`, `*.nvidia.com`).
- **Tier 2 (Supporting):** Known technical hubs (GitHub READMEs, Arxiv).
- **Tier 3 (Context):** Blog posts and Stack Overflow (use `maxAge: 2days` to avoid stale hacks).

**Decision rule:** If Tier 1 contradicts Tier 3, the Teacher must ignore Tier 3 regardless of recency.

## Commands (copy/paste)

```bash
# Install dependencies
uv sync

# Run WITHOUT seed URL (auto-discovers docs via Firecrawl search)
uv run skillforge "use the Firecrawl API" -v

# Run WITH explicit seed URL (safer for a live demo)
uv run skillforge "build CUDA kernels" --seed https://docs.nvidia.com/cuda -v

# Options
--seed           # Seed documentation URL (optional - auto-discovers if omitted)
--model          # Model to use (default: claude-sonnet-4-20250514)
--max-attempts   # Max teacher retries (default: 5)
--corpus-limit   # Max pages to crawl (default: 50)
```

### Auto-Discovery Mode (no --seed)
When `--seed` is omitted, Skillforge automatically:
1. Searches Firecrawl for `"<task> official documentation"`, `"<task> documentation"`, etc.
2. Filters results to docs-like URLs (prefers Tier 1 sources)
3. Uses top 3 results as seeds for deeper crawling
4. Merges and deduplicates all sources with proper tiering

This enables the core use case: **Claude fails a task → Skillforge auto-discovers docs → generates a skill → future Claude sessions succeed.**

## Environment Variables (must be set)

Required:
- `ANTHROPIC_API_KEY` - Claude API key
- `FIRECRAWL_API_KEY` - Firecrawl API key

## Architecture (what happens end-to-end)

**Skillforge** generates agent skills from documentation. It crawls docs, runs iterative Claude sessions to complete a task, fills knowledge gaps automatically, and outputs a SKILL.md file.

### Core Flow (6 steps)

1. **Config Validation** (`config.py`) - Checks API keys exist
2. **Source Discovery** (`discovery.py`) - Auto-discovers docs via Firecrawl search OR maps explicit seed URL, filters to docs paths, classifies into tiers
3. **Corpus Building** (`corpus.py`) - Crawls sources via Firecrawl, saves as markdown with YAML frontmatter
4. **Teacher Session** (`teacher.py`) - Iterative loop where Claude attempts the task. On failure, extracts `KNOWLEDGE_GAP:` queries, searches for missing info, enriches corpus, retries
5. **Validation** - After the teacher detects success, run a validation script inside the sandbox.
6. **Skill Generation** (`generator.py`) - Synthesizes successful trace into SKILL.md + tests.json

### Key Design Decisions (and why)

**Teacher Protocol**: Model must respond with either:
- `TASK_COMPLETE: <summary>` on success
- `KNOWLEDGE_GAP: <search query>` when docs are insufficient

If neither marker is present, the system raises `GapDetectionError` immediately rather than guessing. This keeps failures loud and explicit.

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
| `cli.py` | Click command, orchestrates 6-step flow |
| `discovery.py` | Auto-discovery (no seed), URL mapping, docs filtering, tier classification |
| `corpus.py` | Crawl → markdown conversion, manifest management |
| `firecrawl_client.py` | Wraps Firecrawl map/crawl/search APIs |
| `teacher.py` | Retry loop with gap detection and corpus enrichment |
| `generator.py` | SKILL.md synthesis from successful trace |
| `exceptions.py` | Typed exception hierarchy (all inherit `SkillForgeError`) |

## Parallel Development (Git Worktrees)
To accelerate development, we use isolated Git Worktrees:
- **Worktree A:** Teacher research + crawling.
- **Worktree B:** Core CLI.
- **Worktree C:** Frontend (if applicable).

**Sync rule:** All worktrees must reference `CLAUDE.md` and a shared `STATUS.md` in the repo root to prevent context drift between parallel Claude sessions.

## Dangerous Mode & Sandbox Safety
When running with `--dangerously-skip-permissions`, the following rules are non-negotiable:
- **Isolation:** All code execution tests MUST run in a Docker container or isolated sandbox (e.g., E2B).
- **Loud failure:** Any attempt by an LLM to run `sudo` or `rm` outside the sandbox must trigger `SecurityViolationError` and immediately kill the process.
- **Verification:** A task is not COMPLETE until it passes a validation script inside the sandbox.

## Model Strategy (cost vs. quality)
- Use a stronger model (via OpenRouter or direct) to **generate** the skill and resolve gaps.
- After a skill exists, allow a cheaper model to **re-run** the task for cost efficiency, but validate outputs the same way.

## Demo Checklist (12-hour hackathon friendly)
1. Set env vars (`ANTHROPIC_API_KEY`, `FIRECRAWL_API_KEY`) and confirm `uv sync` works.
2. Pick a tiny, reliable doc seed (10–20 pages) for the live demo.
3. Run with `-v` so logs show each pipeline stage.
4. Verify output in `skills/<skill_name>/` exists and contains `SKILL.md` + `tests.json`.
5. Be ready to explain tradeoffs: "We optimized for correctness and clarity over resiliency."

## Failure Modes to Expect (and how to talk about them)
- **Missing API keys**: Config validation fails immediately.
- **Model output missing markers**: `GapDetectionError` on teacher step.
- **Large/complex docs**: Crawl timeouts or noisy results → lower-quality skill.

## How to Make This Better (plain language, for a junior engineer)
Think of the system like a 6-step conveyor belt. If any step stops, everything stops. We want
to keep the belt moving and make it obvious when it breaks.

Start with reliability before scale:
1. **Make the happy path rock-solid.** Use a tiny doc site for demos so the crawl always succeeds.
2. **Add simple guardrails.** For example, if the model forgets the marker, retry once with a
   clearer system prompt before failing. Keep the failure loud, but give it one chance.
3. **Surface evidence.** Always print which URLs were crawled and where output files were written.
4. **Keep tradeoffs explicit.** If you skip features (like retries or caching), say so and explain
   it was a time-box decision.

If you only have time for one improvement: add a single retry in the teacher step when the
marker is missing. That keeps failures loud but reduces demo risk.

## Available Skills

- `/prd` - Create product requirements documents
- `/ralph` - Autonomous iterative development mode (RALPH: Rapid Autonomous Loop for Helpful Programming)
