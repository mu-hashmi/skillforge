"""CLI entry point."""

import sys
from pathlib import Path

import click

from .claude_runner import ensure_core_skills, ensure_verify_script, write_task_file, launch_claude
from .exceptions import SkillForgeError, ClaudeRunnerError, FirecrawlSearchError, GenerationError


class DefaultGroup(click.Group):
    """A click Group that treats unknown commands as arguments to the default command."""

    def __init__(self, *args, default_cmd: str = "run", **kwargs):
        super().__init__(*args, **kwargs)
        self.default_cmd = default_cmd

    def parse_args(self, ctx, args):
        # If first arg doesn't look like a known command, treat it as 'run <task>'
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = [self.default_cmd] + list(args)
        return super().parse_args(ctx, args)


@click.group(cls=DefaultGroup)
def main() -> None:
    """SkillForge - Launch Claude Code with Firecrawl-powered retrieval."""
    pass


@main.command("run")
@click.argument("task")
def run_cmd(task: str) -> None:
    """Launch Claude Code with a task and SkillForge skills."""
    try:
        repo_root = Path.cwd()
        ensure_core_skills(repo_root)
        ensure_verify_script(repo_root)
        write_task_file(repo_root, task)
        exit_code = launch_claude(task, repo_root)
        raise SystemExit(exit_code)
    except SkillForgeError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    except ClaudeRunnerError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    except KeyboardInterrupt:
        click.echo("Interrupted", err=True)
        raise SystemExit(130)


@main.command("search")
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", default=10, help="Number of results to fetch")
@click.option("--github", is_flag=True, help="Search GitHub issues/discussions only")
def search_cmd(query: tuple[str, ...], limit: int, github: bool) -> None:
    """Search documentation using Firecrawl."""
    from .firecrawl_search import run

    query_str = " ".join(query).strip()
    try:
        run(query_str, limit=limit, github=github)
    except (ValueError, FirecrawlSearchError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@main.command("crawl")
@click.argument("url")
@click.option("--limit", default=50, help="Maximum pages to crawl")
def crawl_cmd(url: str, limit: int) -> None:
    """Crawl a documentation site into the knowledge base."""
    from .firecrawl_crawl import run

    try:
        run(url, limit=limit)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@main.command("save-skill")
@click.argument("name")
@click.option("--task-file", default=".skillforge/TASK.md", help="Path to task file")
@click.option("--out", default=None, help="Output directory (default: .claude/skills/<name>)")
def save_skill_cmd(name: str, task_file: str, out: str | None) -> None:
    """Save current workflow as a reusable skill."""
    from .generate_skill import generate_skill

    task_path = Path(task_file)
    out_path = Path(out) if out else Path(".claude/skills") / name

    try:
        result = generate_skill(name, task_path, out_path, trace_file=None)
        click.echo(f"Skill saved to {result}")
    except GenerationError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
