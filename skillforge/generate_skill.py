"""Generate a reusable Claude Code skill from a task + trace summary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import GenerationError


def _slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:64]


def _read_task(task_file: Path) -> str:
    content = task_file.read_text(encoding="utf-8").strip()
    if not content:
        raise GenerationError(f"Task file is empty: {task_file}")

    lines = content.splitlines()
    task_lines: list[str] = []
    in_task = False
    for line in lines:
        if line.strip().lower() == "# task":
            in_task = True
            continue
        if in_task and line.startswith("#"):
            break
        if in_task:
            task_lines.append(line.rstrip())

    task = "\n".join(task_lines).strip() if task_lines else content
    if not task:
        raise GenerationError(f"Failed to parse task from {task_file}")
    return task


def _load_trace(trace_file: Path | None) -> str | None:
    if trace_file and trace_file.exists():
        return trace_file.read_text(encoding="utf-8").strip()
    return None


def _yaml_escape(value: str) -> str:
    if any(ch in value for ch in [":", "#", '"', "'"]):
        return json.dumps(value)
    return value


def _write_registry(repo_root: Path, task: str, skill_name: str, out_dir: Path, trace_file: Path | None) -> None:
    registry_path = repo_root / ".skillforge" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

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
        "out_dir": str(out_dir),
        "trace_file": str(trace_file) if trace_file else None,
    }
    registry["entries"] = entries
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _write_skill(skill_dir: Path, skill_name: str, task: str, trace_text: str | None) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)

    description = f"Reusable workflow for: {task.replace('\n', ' ').strip()}"
    frontmatter = [
        "---",
        f"name: {skill_name}",
        f"description: {_yaml_escape(description)}",
        "---",
        "",
    ]

    body = [
        "# Overview",
        "",
        task.strip(),
        "",
        "# Workflow",
        "",
        "1) Attempt implementation immediately.",
        "2) Run the required tests/build/bench commands.",
        "3) If failures occur, capture exact stderr/error text and run /search-docs.",
        "4) Apply fixes and rerun until passing.",
        "",
        "# Verification",
        "",
        "- Run the validation commands from the task.",
        "",
        "# Troubleshooting",
        "",
        "- Use /search-docs with the exact error output.",
    ]

    if trace_text:
        references_dir = skill_dir / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        trace_path = references_dir / "trace_summary.md"
        trace_path.write_text(trace_text.strip() + "\n", encoding="utf-8")
        body.extend(
            [
                "",
                "# Trace Summary",
                "",
                "See references/trace_summary.md",
            ]
        )

    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text("\n".join(frontmatter + body).strip() + "\n", encoding="utf-8")


def generate_skill(name: str, task_file: Path, out_dir: Path, trace_file: Path | None) -> Path:
    if not task_file.exists():
        raise GenerationError(f"Task file not found: {task_file}")

    task = _read_task(task_file)
    skill_name = _slugify(name)
    if not skill_name:
        raise GenerationError("Skill name is empty after slugify. Provide a valid name.")

    trace_text = _load_trace(trace_file)
    if out_dir.name != skill_name:
        out_dir = out_dir.parent / skill_name

    _write_skill(out_dir, skill_name, task, trace_text)
    _write_registry(task_file.parent.parent, task, skill_name, out_dir, trace_file)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Claude Code skill from a task + trace.")
    parser.add_argument("--name", required=True, help="Skill name (slug)")
    parser.add_argument("--task-file", required=True, help="Path to .skillforge/TASK.md")
    parser.add_argument("--out", required=True, help="Output directory for the skill")
    parser.add_argument(
        "--trace-file",
        default=None,
        help="Optional trace summary file (defaults to .skillforge/trace_summary.md if present)",
    )
    args = parser.parse_args()

    task_file = Path(args.task_file)
    out_dir = Path(args.out)
    trace_file = Path(args.trace_file) if args.trace_file else None

    if trace_file is None:
        default_trace = task_file.parent / "trace_summary.md"
        trace_file = default_trace if default_trace.exists() else None

    try:
        generate_skill(args.name, task_file, out_dir, trace_file)
    except GenerationError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
