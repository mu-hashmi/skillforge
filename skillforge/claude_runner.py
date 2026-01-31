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
"""


_SAVE_SKILL_SKILL = """---
name: save-skill
description: Persist the current debugging/coding workflow as a reusable Agent Skill under .claude/skills/<name>/SKILL.md
disable-model-invocation: true
allowed-tools:
  - Bash: 'python -m skillforge.generate_skill --name "$ARGUMENTS" --task-file .skillforge/TASK.md --out ".claude/skills/$ARGUMENTS"'
---

# /save-skill

Provide a short, hyphenated skill name in $ARGUMENTS (example: cuda-kernel-fixups).

Run:
!python -m skillforge.generate_skill --name "$ARGUMENTS" --task-file .skillforge/TASK.md --out ".claude/skills/$ARGUMENTS"

This creates .claude/skills/<skill-name>/SKILL.md and any supporting files.
Keep SKILL.md under ~500 lines; put large references into separate files.
"""


_TASK_CONTRACT = """# Task
{task}

# Loop contract
1) Attempt implementation immediately (do not stall on docs).
2) Run required tests/build/bench commands.
3) On failure: use /search-docs with the exact stderr/error text, apply fixes, and rerun.
4) Repeat until passing.
5) On success: run /save-skill <short-skill-name>.
"""


def build_appended_system_prompt() -> str:
    """Return the system prompt appended to Claude Code."""
    return (
        "Read .skillforge/TASK.md first and follow it. "
        "Implement immediately with current knowledge (no docs-first stalling). "
        "Run the required tests/build/bench. "
        "If anything fails, invoke /search-docs with the exact stderr/error text, "
        "apply fixes, and rerun until passing. "
        "When done, invoke /save-skill <short-skill-name>."
    )


def ensure_core_skills(repo_root: Path) -> None:
    """Install or update the core SkillForge skills in the target repo."""
    skills_root = repo_root / ".claude" / "skills" / "skillforge-core"
    search_docs_path = skills_root / "search-docs" / "SKILL.md"
    save_skill_path = skills_root / "save-skill" / "SKILL.md"

    search_docs_path.parent.mkdir(parents=True, exist_ok=True)
    save_skill_path.parent.mkdir(parents=True, exist_ok=True)

    search_docs_path.write_text(_SEARCH_DOCS_SKILL, encoding="utf-8")
    save_skill_path.write_text(_SAVE_SKILL_SKILL, encoding="utf-8")


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
