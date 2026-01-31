"""Skill file generation from successful traces."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

from .config import get_anthropic_api_key
from .teacher import TeacherResult
from .exceptions import GenerationError


GENERATION_PROMPT = """Based on the following successful task completion, generate a SKILL.md file that teaches AI models how to complete this task.

TASK: {task}

SUCCESSFUL OUTPUT:
{output}

TEACHER TRACE (attempts and gaps filled):
{trace_summary}

---

Generate a comprehensive SKILL.md with the following structure:

1. YAML frontmatter with: name, version (1.0.0), created date, task description
2. Overview section explaining what this skill does and when to use it
3. Prerequisites section listing required tools, dependencies, or knowledge
4. Core Concepts section with key terminology and foundational knowledge
5. Step-by-Step Process with actual working code and commands
6. Common Patterns section showing reusable approaches
7. Troubleshooting section with potential issues and solutions
8. Verification section describing how to test if the skill was applied correctly

Also generate JSON test cases that can verify the skill works.

Output your response in this exact format:

<SKILL_MD>
[Complete SKILL.md content here, including frontmatter]
</SKILL_MD>

<TESTS_JSON>
{{
  "tests": [
    {{
      "name": "test_name",
      "type": "command|content_check|file_exists",
      "description": "What this test verifies"
    }}
  ]
}}
</TESTS_JSON>

Be thorough but practical. Focus on actionable knowledge that helps complete the task."""


@dataclass
class GeneratedSkill:
    skill_md: str
    tests: dict
    manifest: dict


def _slugify_name(task: str) -> str:
    """Create a skill name from task description."""
    slug = task.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50].strip("-")


def _extract_section(content: str, start_tag: str, end_tag: str) -> str:
    """Extract content between XML-like tags."""
    start = content.find(start_tag)
    end = content.find(end_tag)
    if start >= 0 and end > start:
        return content[start + len(start_tag):end].strip()
    return ""


def _format_trace_summary(result: TeacherResult) -> str:
    """Format trace for inclusion in prompt."""
    lines = [f"Total attempts: {result.attempts}"]
    if result.gaps_filled:
        lines.append(f"Knowledge gaps filled: {', '.join(result.gaps_filled)}")
    for entry in result.trace:
        lines.append(f"\nAttempt {entry['attempt']}:")
        if entry.get("gap_query"):
            lines.append(f"  Gap identified: {entry['gap_query']}")
            if entry.get("gap_sources_added"):
                lines.append(f"  Sources added: {entry['gap_sources_added']}")
    return "\n".join(lines)


def generate_skill(
    task: str,
    result: TeacherResult,
    corpus_path: Path,
    output_dir: Path | None = None,
) -> Path:
    """Generate SKILL.md from successful teacher trace."""
    if not result.success:
        raise GenerationError("Cannot generate skill from unsuccessful teacher session")

    client = Anthropic(api_key=get_anthropic_api_key())

    # Format inputs
    trace_summary = _format_trace_summary(result)

    prompt = GENERATION_PROMPT.format(
        task=task,
        output=result.final_output,
        trace_summary=trace_summary,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    output = response.content[0].text

    # Extract sections
    skill_content = _extract_section(output, "<SKILL_MD>", "</SKILL_MD>")
    tests_content = _extract_section(output, "<TESTS_JSON>", "</TESTS_JSON>")

    if not skill_content:
        raise GenerationError(
            "Failed to generate SKILL.md content - model output did not contain expected format"
        )

    # Parse tests
    try:
        tests = json.loads(tests_content) if tests_content else {"tests": []}
    except json.JSONDecodeError:
        tests = {"tests": []}

    # Create output directory
    skill_name = _slugify_name(task)
    if output_dir is None:
        output_dir = Path.cwd() / "skills" / skill_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md
    skill_path = output_dir / "SKILL.md"
    skill_path.write_text(skill_content, encoding="utf-8")

    # Write tests
    tests_path = output_dir / "tests.json"
    tests_path.write_text(json.dumps(tests, indent=2), encoding="utf-8")

    # Write manifest
    manifest = {
        "name": skill_name,
        "version": "1.0.0",
        "created": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "model": "claude-sonnet-4-20250514",
        "corpus_path": str(corpus_path),
        "attempts": result.attempts,
        "gaps_filled": result.gaps_filled,
        "files": {
            "skill": "SKILL.md",
            "tests": "tests.json",
        },
    }
    manifest_path = output_dir / "skill_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return output_dir
