"""Custom exceptions for Skill Forge. NO SILENT FAILURES."""


class SkillForgeError(Exception):
    """Base exception for all Skill Forge errors."""


class ConfigError(SkillForgeError):
    """Missing or invalid configuration (API keys, etc)."""


class DiscoveryError(SkillForgeError):
    """Failed to discover sources from seed URL."""


class SearchError(SkillForgeError):
    """Search operation failed."""


class CorpusBuildError(SkillForgeError):
    """Failed to build corpus from sources."""


class CorpusLoadError(SkillForgeError):
    """Failed to load existing corpus."""


class CorpusUpdateError(SkillForgeError):
    """Failed to update corpus with new pages."""


class TeacherSessionError(SkillForgeError):
    """Teacher session failed after all attempts."""


class GapDetectionError(SkillForgeError):
    """Failed to identify knowledge gap from failure."""


class AnalysisError(SkillForgeError):
    """Could not determine if attempt succeeded or failed."""


class GenerationError(SkillForgeError):
    """Failed to generate skill file."""


class FirecrawlError(SkillForgeError):
    """Base for Firecrawl API errors."""


class FirecrawlMapError(FirecrawlError):
    """Map operation failed."""


class FirecrawlCrawlError(FirecrawlError):
    """Crawl operation failed."""


class FirecrawlSearchError(FirecrawlError):
    """Search operation failed."""


class ClaudeRunnerError(SkillForgeError):
    """Claude Code launcher or setup failed."""
