# SkillForge

SkillForge launches Claude Code as the coder, installs core skills into the target repo, and provides Firecrawl-powered retrieval plus a simple skill generator.

## Quick start

1) Ensure `claude` is on your PATH.
2) Set `FIRECRAWL_API_KEY` in your environment.
3) Run:

```bash
skillforge "Optimize this CUDA kernel; run pytest -q until it passes"
```

## Hackathon demo flow

Example:

```bash
skillforge "Optimize this CUDA kernel; run pytest -q until it passes"
```

Claude Code workflow:

1) Implement immediately.
2) Run `pytest -q`.
3) On error: `/search-docs "<paste stderr>"` → apply fixes → rerun.
4) On success: `/save-skill cuda-kernel-fixups`.

## What it does

- Ensures `.claude/skills/` exists in the current repo.
- Installs/updates core skills into `.claude/skills/skillforge-core/`.
- Writes `.skillforge/TASK.md` with the task and loop contract.
- Launches Claude Code in interactive mode using:
  `claude "<task>" --append-system-prompt "<rules>"`

## Core skills

### /search-docs

Firecrawl-powered retrieval for error-driven debugging. It runs:

```bash
python -m skillforge.firecrawl_search "<query or stderr>"
```

This writes `.skillforge/cache/<timestamp>_search.md` and prints:
`Top findings`, cache file path, and the exact search query used.

### /save-skill

Persist the workflow as a reusable skill:

```bash
python -m skillforge.generate_skill --name "<skill-name>" --task-file .skillforge/TASK.md --out .claude/skills/<skill-name>
```

The generator will also read `.skillforge/trace_summary.md` if present and update `.skillforge/registry.json`.
