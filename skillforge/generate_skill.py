"""Generate a reusable Claude Code skill from a task + trace summary."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from .exceptions import GenerationError

SUMMARIZE_SECTION_PROMPT = """\
Extract the key technical information from this documentation that's relevant to the task.
Focus on: code examples, API patterns, configuration, known issues/gotchas, error solutions.
Be concise but preserve important details. Output markdown.

Task: {task}

Documentation:
{section}"""

SYNTHESIZE_PROMPT = """\
Combine these documentation summaries into a concise technical reference.
Structure it with clear headers. Prioritize: code examples, patterns, known issues.
This will be embedded in a skill file that Claude Code loads, so it should contain
everything needed to complete the task without additional searches.

Task: {task}

Summaries:
{summaries}"""


def _summarize_knowledge(knowledge: str, task: str) -> str:
    """Summarize raw knowledge into a concise reference using Claude."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise GenerationError("ANTHROPIC_API_KEY environment variable required for summarization")

    client = anthropic.Anthropic(api_key=api_key)
    model = "claude-3-5-haiku-latest"

    # Split by search result sections
    sections = re.split(r"(?=## From search:|## From https?://)", knowledge)
    sections = [s.strip() for s in sections if s.strip() and len(s) > 500]

    if not sections:
        return ""

    summaries = []
    for section in sections:
        # Truncate very long sections to stay within context
        truncated = section[:50000] if len(section) > 50000 else section
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": SUMMARIZE_SECTION_PROMPT.format(task=task, section=truncated),
                }],
            )
            summaries.append(resp.content[0].text)
        except anthropic.APIError as e:
            print(f"Warning: Failed to summarize section: {e}", file=sys.stderr)
            continue

    if not summaries:
        return ""

    # Synthesize into final reference
    combined = "\n\n---\n\n".join(summaries)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": SYNTHESIZE_PROMPT.format(task=task, summaries=combined),
            }],
        )
        return resp.content[0].text
    except anthropic.APIError as e:
        print(f"Warning: Failed to synthesize summaries: {e}", file=sys.stderr)
        return combined  # Fall back to concatenated summaries


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


def _collect_knowledge(repo_root: Path, max_search_files: int = 5, max_pages_per_domain: int = 10, max_chars_per_page: int = 2000) -> str:
    """Collect cached searches and crawled knowledge."""
    sections = []

    # Include recent search cache files
    cache_dir = repo_root / ".skillforge" / "cache"
    if cache_dir.exists():
        search_files = sorted(cache_dir.glob("*_search.md"))[-max_search_files:]
        for cache_file in search_files:
            content = cache_file.read_text(encoding="utf-8").strip()
            # Extract query from the file
            query_line = next((l for l in content.splitlines() if l.startswith("Query: ")), None)
            query = query_line[7:] if query_line else "unknown"
            sections.append(f"## From search: \"{query}\"\n\n{content}")

    # Include crawled knowledge
    knowledge_dir = repo_root / ".skillforge" / "knowledge"
    if knowledge_dir.exists():
        for domain_dir in knowledge_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            manifest_path = domain_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_url = manifest.get("source_url", domain_dir.name)

            domain_content = []
            for page_info in manifest.get("pages", [])[:max_pages_per_domain]:
                page_path = domain_dir / page_info["file"]
                if not page_path.exists():
                    continue
                page_content = page_path.read_text(encoding="utf-8")
                # Truncate long pages
                if len(page_content) > max_chars_per_page:
                    page_content = page_content[:max_chars_per_page] + "\n\n[truncated]"
                title = page_info.get("title") or "Untitled"
                domain_content.append(f"### {title}\n\n{page_content}")

            if domain_content:
                sections.append(f"## From {source_url}\n\n" + "\n\n---\n\n".join(domain_content))

    return "\n\n---\n\n".join(sections) if sections else ""


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


def _write_skill(
    skill_dir: Path,
    skill_name: str,
    task: str,
    trace_text: str | None,
    knowledge_summary: str | None,
    raw_knowledge: str | None,
) -> None:
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
        "1) Attempt implementation immediately using the Key Documentation below.",
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

    # Add summarized knowledge inline
    if knowledge_summary:
        body.extend(
            [
                "",
                "# Key Documentation",
                "",
                knowledge_summary.strip(),
            ]
        )

    # Optionally save raw knowledge for reference
    if raw_knowledge:
        references_dir = skill_dir / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        knowledge_path = references_dir / "raw_knowledge.md"
        knowledge_path.write_text(raw_knowledge.strip() + "\n", encoding="utf-8")

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
    repo_root = task_file.parent.parent
    raw_knowledge = _collect_knowledge(repo_root)

    # Summarize knowledge for inline embedding
    knowledge_summary = None
    if raw_knowledge:
        print("Summarizing knowledge...", file=sys.stderr)
        knowledge_summary = _summarize_knowledge(raw_knowledge, task)
        if knowledge_summary:
            print(f"Generated {len(knowledge_summary)} char summary", file=sys.stderr)

    if out_dir.name != skill_name:
        out_dir = out_dir.parent / skill_name

    _write_skill(out_dir, skill_name, task, trace_text, knowledge_summary, raw_knowledge)
    _write_registry(repo_root, task, skill_name, out_dir, trace_file)
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
