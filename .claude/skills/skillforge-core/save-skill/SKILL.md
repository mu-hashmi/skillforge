---
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
