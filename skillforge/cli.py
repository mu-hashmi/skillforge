"""CLI entry point."""

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Load .env before any config access
load_dotenv()

from .config import validate_config
from .discovery import discover_sources, discover_sources_from_task
from .corpus import build_corpus
from .teacher import run_teacher_session
from .validation import validate_or_raise
from .generator import generate_skill
from .exceptions import SkillForgeError

console = Console()


def _print_step(step: int, total: int, message: str) -> None:
    console.print(f"[bold blue][{step}/{total}][/] {message}")


def _print_success(message: str) -> None:
    console.print(f"  [green]✓[/] {message}")


def _print_warning(message: str) -> None:
    console.print(f"  [yellow]![/] {message}")


def _print_error(message: str) -> None:
    console.print(f"  [red]✗[/] {message}")


@click.command()
@click.argument("task")
@click.option("--seed", required=False, help="Seed documentation URL (optional - auto-discovers if omitted)")
@click.option(
    "--model",
    default="claude-sonnet-4-20250514",
    help="Model to use for teacher session",
)
@click.option("--max-attempts", default=5, help="Maximum teacher session attempts")
@click.option("--corpus-limit", default=50, help="Maximum pages to crawl")
@click.option("--stealth", is_flag=True, help="Use stealth proxies for anti-bot protected sites (9x cost)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(
    task: str,
    seed: str | None,
    model: str,
    max_attempts: int,
    corpus_limit: int,
    stealth: bool,
    verbose: bool,
) -> None:
    """
    Generate a SKILL.md file from task description and documentation.

    TASK: Description of the task to learn (e.g., "build CUDA kernels")

    If --seed is omitted, Skillforge will automatically search for relevant
    documentation using Firecrawl. This enables autonomous skill generation
    when Claude fails a task - it searches for docs to fill the knowledge gap.
    """
    try:
        # Step 1: Validate config
        _print_step(1, 6, "Validating configuration...")
        validate_config()
        _print_success("Configuration valid")

        # Step 2: Discover sources
        if seed:
            _print_step(2, 6, f"Discovering sources from seed: {seed}")
            sources = discover_sources(task, seed)
        else:
            _print_step(2, 6, "Auto-discovering documentation sources...")
            sources = discover_sources_from_task(task)
        _print_success(f"Found {len(sources)} sources")
        if verbose:
            # Show tier breakdown
            tier_1 = sum(1 for s in sources if s.tier.value == 1)
            tier_2 = sum(1 for s in sources if s.tier.value == 2)
            tier_3 = sum(1 for s in sources if s.tier.value == 3)
            console.print(f"    Tier 1 (critical): {tier_1}, Tier 2 (supporting): {tier_2}, Tier 3 (context): {tier_3}")
            for s in sources[:5]:
                console.print(f"    - [T{s.tier.value}] {s.url}")
            if len(sources) > 5:
                console.print(f"    ... and {len(sources) - 5} more")

        # Step 3: Build corpus
        _print_step(3, 6, "Building documentation corpus...")
        if stealth and verbose:
            console.print("    [yellow]Stealth mode enabled (9x crawl cost)[/]")
        corpus_path = build_corpus(task, sources, limit=corpus_limit, stealth=stealth)
        _print_success(f"Corpus created at {corpus_path.name}")
        if verbose:
            import json
            manifest = json.loads((corpus_path / "manifest.json").read_text())
            console.print(f"    Pages: {manifest['total_pages']}")
            console.print(f"    Est. tokens: {manifest['total_tokens_estimate']:,}")
            if "tier_breakdown" in manifest:
                tb = manifest["tier_breakdown"]
                console.print(f"    Tiers: T1={tb['tier_1_critical']}, T2={tb['tier_2_supporting']}, T3={tb['tier_3_context']}")

        # Step 4: Teacher session
        _print_step(4, 6, "Running teacher session...")

        def on_attempt(attempt: int, outcome):
            if outcome.success:
                _print_success(f"Attempt {attempt}: Task completed")
            elif outcome.gap_query:
                _print_warning(f"Attempt {attempt}: Gap found - {outcome.gap_query}")
            else:
                _print_warning(f"Attempt {attempt}: No gap identified")

        result = run_teacher_session(
            task=task,
            corpus_path=corpus_path,
            model=model,
            max_attempts=max_attempts,
            verbose=verbose,
            on_attempt=on_attempt if verbose else None,
            stealth=stealth,
        )
        _print_success(f"Completed in {result.attempts} attempt(s)")
        if result.gaps_filled:
            console.print(f"    Gaps filled: {', '.join(result.gaps_filled)}")

        # Step 5: Validate output
        _print_step(5, 6, "Validating teacher output...")
        validation = validate_or_raise(result)
        _print_success(f"Validation passed ({validation.checks_passed}/{validation.checks_run} checks)")
        if verbose and validation.warnings:
            for warning in validation.warnings:
                _print_warning(warning)

        # Step 6: Generate skill
        _print_step(6, 6, "Generating SKILL.md...")
        skill_path = generate_skill(task, result, corpus_path)
        _print_success(f"Skill saved to {skill_path}")

        # Final summary
        console.print()
        console.print(
            Panel(
                f"[bold green]Skill generated successfully![/]\n\n"
                f"[bold]Location:[/] {skill_path}\n"
                f"[bold]Files:[/]\n"
                f"  • SKILL.md\n"
                f"  • tests.json\n"
                f"  • skill_manifest.json\n\n"
                f"[bold]Corpus:[/] {corpus_path}",
                title="✨ Done",
                border_style="green",
            )
        )

    except SkillForgeError as e:
        console.print()
        console.print(f"[bold red]Error:[/] {e}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Interrupted[/]")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
