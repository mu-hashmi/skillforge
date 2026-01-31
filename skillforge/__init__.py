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
    TeacherSessionError,
    GapDetectionError,
    AnalysisError,
    GenerationError,
    FirecrawlError,
    FirecrawlMapError,
    FirecrawlCrawlError,
    FirecrawlSearchError,
)
from .discovery import Source, SourceType, discover_sources, search_for_gap
from .corpus import build_corpus, load_corpus_as_context, add_pages_to_corpus
from .teacher import TeacherResult, AttemptOutcome, run_teacher_session, analyze_attempt
from .generator import generate_skill

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
    "TeacherSessionError",
    "GapDetectionError",
    "AnalysisError",
    "GenerationError",
    "FirecrawlError",
    "FirecrawlMapError",
    "FirecrawlCrawlError",
    "FirecrawlSearchError",
    # Discovery
    "Source",
    "SourceType",
    "discover_sources",
    "search_for_gap",
    # Corpus
    "build_corpus",
    "load_corpus_as_context",
    "add_pages_to_corpus",
    # Teacher
    "TeacherResult",
    "AttemptOutcome",
    "run_teacher_session",
    "analyze_attempt",
    # Generator
    "generate_skill",
]
