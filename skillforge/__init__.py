"""Skill Forge - Generate agent skills from documentation."""

__version__ = "0.1.0"

from .exceptions import (
    SkillForgeError,
    ConfigError,
    DiscoveryError,
    SearchError,
    CorpusBuildError,
    CorpusLoadError,
    CorpusUpdateError,
    GenerationError,
    FirecrawlError,
    FirecrawlMapError,
    FirecrawlCrawlError,
    FirecrawlSearchError,
    ClaudeRunnerError,
)
from .discovery import Source, SourceType, discover_sources, search_for_gap
from .corpus import build_corpus, load_corpus_as_context, add_pages_to_corpus
from .claude_runner import ensure_core_skills, write_task_file, launch_claude, build_appended_system_prompt

__all__ = [
    "__version__",
    # Exceptions
    "SkillForgeError",
    "ConfigError",
    "DiscoveryError",
    "SearchError",
    "CorpusBuildError",
    "CorpusLoadError",
    "CorpusUpdateError",
    "GenerationError",
    "FirecrawlError",
    "FirecrawlMapError",
    "FirecrawlCrawlError",
    "FirecrawlSearchError",
    "ClaudeRunnerError",
    # Discovery
    "Source",
    "SourceType",
    "discover_sources",
    "search_for_gap",
    # Corpus
    "build_corpus",
    "load_corpus_as_context",
    "add_pages_to_corpus",
    # Claude runner
    "ensure_core_skills",
    "write_task_file",
    "launch_claude",
    "build_appended_system_prompt",
]
