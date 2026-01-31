"""CLI entry point."""

from pathlib import Path

import click

from .claude_runner import ensure_core_skills, ensure_verify_script, write_task_file, launch_claude
from .exceptions import SkillForgeError, ClaudeRunnerError


@click.command()
@click.argument("task")
def main(task: str) -> None:
    """Launch Claude Code with SkillForge core skills and task contract."""
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


if __name__ == "__main__":
    main()
