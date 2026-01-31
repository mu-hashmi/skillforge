# PROJECT STATUS (Hackathon Sync)

## Current Goal
~~Get the end-to-end "Teacher" loop running with a real documentation crawl~~
**ACHIEVED** - Pipeline is demo-ready with auto-discovery mode

## Active Workstreams
- **Worktree A (Teacher):** COMPLETE
- **Worktree B (Core CLI):** COMPLETE
- **Worktree C (Discovery):** COMPLETE

## Completed Tasks
- [x] API Key validation in `config.py`
- [x] Basic Firecrawl client wrapper
- [x] CLAUDE.md expanded with hackathon workflow guidance
- [x] Core CLI wiring (click commands, verbose logging)
- [x] Single retry when marker is missing in teacher.py
- [x] Domain layering (Tier 1/2/3) in discovery.py
- [x] Validation step (step 5) added to CLI
- [x] CLI updated to 6-step orchestration
- [x] dotenv auto-loading in CLI
- [x] End-to-end integration test passed
- [x] Auto-discovery mode verified (no --seed required)
- [x] Complex CUDA task test passed

## Test Results (2026-01-31)

| Task | Sources | Corpus | Attempts | Result |
|------|---------|--------|----------|--------|
| "use the Firecrawl API to crawl a webpage" | 4 T1 | 5,653 tokens | 1 | PASSED |
| "build a fused LayerNorm + GELU kernel optimized for H100" | 3 T1 | 11,661 tokens | 1 | PASSED |

**Key findings:**
- Auto-discovery mode works reliably (no seed needed)
- Teacher completes in 1 attempt when corpus has relevant docs
- Tiering correctly classifies sources as T1 (official docs)
- Generated SKILL.md includes working code, tests, and troubleshooting

## Blockers / Notes
- Seeded mode (`--seed`) has issues: gap searches return no results, only 1 page crawled despite 201 sources found
- **Recommendation:** Use auto-discovery mode for demos (more reliable)
- Corpus limit of 10-15 is sufficient; teacher self-heals via gap search if needed

## Next Steps
- [ ] (Pending user direction)
