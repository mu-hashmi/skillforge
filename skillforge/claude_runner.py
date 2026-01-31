"""Claude Code launcher and repository prep."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import ClaudeRunnerError


_SEARCH_DOCS_SKILL = """---
name: search-docs
description: Firecrawl-powered docs search. Use when build failed, test failure, compiler error, CUDA error, import error, linker error, segfault, runtime error, stack trace, or any error output needs targeted documentation lookup.
allowed-tools:
  - Bash
---

# /search-docs

Use this when you have raw stderr/error text or a focused query.

Run:
!python -m skillforge.firecrawl_search "$ARGUMENTS"

The command writes full results to .skillforge/cache/<timestamp>_search.md and prints:
- Top findings
- Cache file path
- Exact search query used
"""


_SAVE_SKILL_SKILL = """---
name: save-skill
description: Persist the current debugging/coding workflow as a reusable Agent Skill under .claude/skills/<name>/SKILL.md
allowed-tools:
  - Bash
---

# /save-skill

Provide a short, hyphenated skill name in $ARGUMENTS (example: cuda-kernel-fixups).

Run:
!python -m skillforge.generate_skill --name "$ARGUMENTS" --task-file .skillforge/TASK.md --out ".claude/skills/$ARGUMENTS"

This creates .claude/skills/<skill-name>/SKILL.md and any supporting files.
Keep SKILL.md under ~500 lines; put large references into separate files.
"""


_DEEP_DIVE_SKILL = """---
name: deep-dive
description: Crawl an entire documentation site when you need comprehensive knowledge about a library/tool. Use when search results are insufficient or you're working extensively with one technology.
allowed-tools:
  - Bash
---

# /deep-dive

Use when you need thorough understanding of a library, not just error fixes.

Run:
!python -m skillforge.firecrawl_crawl "$ARGUMENTS"

Arguments: A documentation URL (e.g., https://docs.fastht.ml)

This will:
1. Crawl up to 50 pages of documentation
2. Save to .skillforge/knowledge/<domain>/
3. Print a summary of what was crawled

The crawled docs persist across sessions and are automatically included in future /save-skill outputs.

Use --limit N to crawl more or fewer pages:
!python -m skillforge.firecrawl_crawl "$ARGUMENTS" --limit 100
"""


_VERIFY_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

LOGFILE=".skillforge/last_run.log"

if [[ $# -lt 2 || "$1" != "--" ]]; then
    echo "Usage: ./scripts/verify.sh -- <command> [args...]"
    exit 1
fi
shift

mkdir -p "$(dirname "$LOGFILE")"

echo "Running: $*" | tee "$LOGFILE"
echo "---" | tee -a "$LOGFILE"
"$@" 2>&1 | tee -a "$LOGFILE"
exit "${PIPESTATUS[0]}"
"""


_TASK_CONTRACT = """# Task
{task}

# Loop contract
1) Implement the task.
2) After each meaningful change, verify with ./scripts/verify.sh -- <cmd> [args...]
3) On failure: run `tail -n 200 .skillforge/last_run.log` then invoke /search-docs with that output.
4) If search results are insufficient, use /deep-dive <docs-url> to crawl documentation.
5) Apply fixes and rerun ./scripts/verify.sh -- <cmd>
6) Repeat until passing.
7) On success: run /save-skill <short-skill-name>.
"""


def build_appended_system_prompt() -> str:
    """Return the system prompt appended to Claude Code."""
    return (
        "Read .skillforge/TASK.md first. "
        "Implement immediately with current knowledge. "
        "After each meaningful change, verify with ./scripts/verify.sh -- <cmd> [args...]. "
        "On failure, run `tail -n 200 .skillforge/last_run.log` and invoke /search-docs with the error output. "
        "If results are insufficient, use /deep-dive <docs-url>. "
        "Apply fixes and rerun verify.sh until passing. "
        "When done, invoke /save-skill <short-skill-name>."
    )


def ensure_core_skills(repo_root: Path) -> None:
    """Install or update the core SkillForge skills in the target repo."""
    skills_root = repo_root / ".claude" / "skills"

    skills = {
        "search-docs": _SEARCH_DOCS_SKILL,
        "save-skill": _SAVE_SKILL_SKILL,
        "deep-dive": _DEEP_DIVE_SKILL,
    }

    for skill_name, content in skills.items():
        skill_path = skills_root / skill_name / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content, encoding="utf-8")


def ensure_verify_script(repo_root: Path) -> None:
    """Install scripts/verify.sh in the target repo."""
    script_path = repo_root / "scripts" / "verify.sh"
    if script_path.exists():
        return
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_VERIFY_SCRIPT, encoding="utf-8")
    script_path.chmod(0o755)


def write_task_file(repo_root: Path, task: str) -> Path:
    """Write .skillforge/TASK.md with the task and loop contract."""
    skillforge_dir = repo_root / ".skillforge"
    skillforge_dir.mkdir(parents=True, exist_ok=True)
    task_path = skillforge_dir / "TASK.md"
    task_path.write_text(_TASK_CONTRACT.format(task=task.strip()), encoding="utf-8")
    return task_path


def launch_claude(task: str, repo_root: Path) -> int:
    """Launch Claude Code in interactive mode with the appended system prompt."""
    if shutil.which("claude") is None:
        raise ClaudeRunnerError("claude not found on PATH")

    appended_prompt = build_appended_system_prompt()
    cmd = ["claude", task, "--append-system-prompt", appended_prompt]
    result = subprocess.run(cmd, cwd=repo_root)
    return result.returncode


def write_registry_entry(repo_root: Path, task: str, skill_name: str) -> Path:
    """Write/update .skillforge/registry.json with minimal metadata."""
    import json

    skillforge_dir = repo_root / ".skillforge"
    skillforge_dir.mkdir(parents=True, exist_ok=True)
    registry_path = skillforge_dir / "registry.json"

    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            registry = {}
    else:
        registry = {}

    entries = registry.get("entries", {})
    entries[task] = {
        "skill": skill_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    registry["entries"] = entries
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return registry_path
