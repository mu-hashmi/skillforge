# SkillForge

SkillForge launches Claude Code as the coder, installs core skills into the target repo, and provides Firecrawl-powered retrieval plus a skill generator that embeds learned knowledge.

## Quick start

1. Ensure `claude` is on your PATH.
2. Set `FIRECRAWL_API_KEY` in your environment.
3. Run in your target repo:

```bash
skillforge run "Build a CUDA kernel for diffusers. Verify with: ./scripts/verify.sh -- python -m pytest -q"
```

## What it does

1. Installs core skills into `.claude/skills/{search-docs,save-skill,deep-dive}/`
2. Bootstraps `scripts/verify.sh` (logging wrapper for test/build commands)
3. Writes `.skillforge/TASK.md` with the task and loop contract
4. Launches Claude Code with appended system prompt

## The Loop

Claude Code follows this contract:

1. **Determine verify command** and write to `.skillforge/verify_command.txt`
2. **Implement** the task
3. **Verify** with `./scripts/verify.sh -- bash -lc "$(cat .skillforge/verify_command.txt)"`
4. **On failure**: `tail -n 200 .skillforge/last_run.log` → `/search-docs` → optionally `/deep-dive`
5. **Retry** until passing
6. **On success**: `/save-skill <name>` to persist the workflow

## Core skills

### /search-docs

Firecrawl-powered search for error-driven debugging.

```bash
skillforge search "<query or stderr>"
```

Writes to `.skillforge/cache/<timestamp>_search.md`.

### /deep-dive

Crawl an entire documentation site when you need comprehensive knowledge.

```bash
skillforge crawl "https://docs.example.com" --limit 50
```

Writes to `.skillforge/knowledge/<domain>/`.

### /save-skill

Persist the workflow as a reusable skill with embedded knowledge.

```bash
skillforge save-skill "<skill-name>"
```

Collects cached searches and crawled docs into `references/knowledge.md`.

## verify.sh

The bootstrapped `scripts/verify.sh` wraps any command:

```bash
./scripts/verify.sh -- pytest -q
./scripts/verify.sh -- npm test
./scripts/verify.sh -- bash -c 'python build.py && python test.py'
```

- Streams output to terminal
- Logs to `.skillforge/last_run.log`
- Preserves exit code via `PIPESTATUS[0]`

## File structure

```
.claude/skills/
├── search-docs/SKILL.md
├── save-skill/SKILL.md
├── deep-dive/SKILL.md
└── <generated-skill>/
    ├── SKILL.md
    └── references/knowledge.md

.skillforge/
├── TASK.md
├── verify_command.txt
├── last_run.log
├── registry.json
├── cache/<timestamp>_search.md
└── knowledge/<domain>/
    ├── manifest.json
    └── *.md

scripts/
└── verify.sh
```
