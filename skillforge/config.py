"""Configuration management."""

import os

from .exceptions import ConfigError


def get_firecrawl_api_key() -> str:
    """Get Firecrawl API key from environment."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise ConfigError("FIRECRAWL_API_KEY environment variable not set")
    return key


def validate_config() -> None:
    """Validate required configuration is present."""
    get_firecrawl_api_key()
