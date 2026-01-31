"""Source discovery using Firecrawl."""

import sys
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from .firecrawl_client import map_url, search
from .exceptions import DiscoveryError, SearchError


class SourceType(Enum):
    SEED = "seed"
    MAPPED = "mapped"
    SEARCHED = "searched"


@dataclass
class Source:
    url: str
    title: str | None
    source_type: SourceType
    priority: int  # 1 = high, 10 = low
    content: str | None = None


def _is_docs_url(url: str) -> bool:
    """Heuristic to identify documentation URLs."""
    docs_indicators = [
        "/docs", "/documentation", "/guide", "/tutorial",
        "/api", "/reference", "/manual", "/learn", "/getting-started",
        "/quickstart", "/handbook", "/wiki",
    ]
    path = urlparse(url).path.lower()
    return any(ind in path for ind in docs_indicators)


def _deduplicate_sources(sources: list[Source]) -> list[Source]:
    """Remove duplicate URLs, keeping highest priority."""
    seen: dict[str, Source] = {}
    for s in sources:
        normalized = s.url.rstrip("/")
        if normalized not in seen or s.priority < seen[normalized].priority:
            seen[normalized] = s
    return list(seen.values())


def discover_sources(task: str, seed_url: str) -> list[Source]:
    """
    Discover documentation sources for a task.

    1. Map the seed URL to find all pages
    2. Filter to docs-like paths
    3. Search for supplementary GitHub/tutorial content
    4. Return deduplicated, priority-sorted list
    """
    sources: list[Source] = []

    # Add seed URL as highest priority
    sources.append(Source(
        url=seed_url,
        title=None,
        source_type=SourceType.SEED,
        priority=1,
    ))

    # Map the seed URL to discover linked pages
    try:
        map_result = map_url(seed_url, limit=200)
        for link in map_result.urls:
            url = link["url"]
            # Filter to docs-like paths or same domain
            seed_domain = urlparse(seed_url).netloc
            link_domain = urlparse(url).netloc
            if link_domain == seed_domain or _is_docs_url(url):
                sources.append(Source(
                    url=url,
                    title=link.get("title"),
                    source_type=SourceType.MAPPED,
                    priority=3 if _is_docs_url(url) else 5,
                ))
    except Exception as e:
        raise DiscoveryError(f"Failed to map seed URL {seed_url}: {e}") from e

    # Search for supplementary materials (best-effort with warning)
    search_query = f"{task} documentation tutorial"
    try:
        search_result = search(search_query, limit=5, scrape=True)
        for item in search_result.results:
            sources.append(Source(
                url=item.url,
                title=item.title,
                source_type=SourceType.SEARCHED,
                priority=7,
                content=item.markdown,
            ))
    except Exception as e:
        # Log warning instead of silent pass
        print(f"Warning: Supplementary search failed for '{search_query}': {e}", file=sys.stderr)

    # Deduplicate and sort by priority
    sources = _deduplicate_sources(sources)
    sources.sort(key=lambda s: (s.priority, s.url))

    return sources


def search_for_gap(gap_query: str) -> list[Source]:
    """Search for specific missing information to fill a knowledge gap."""
    try:
        result = search(gap_query, limit=5, scrape=True)
        return [
            Source(
                url=item.url,
                title=item.title,
                source_type=SourceType.SEARCHED,
                priority=8,
                content=item.markdown,
            )
            for item in result.results
        ]
    except Exception as e:
        raise SearchError(f"Gap search failed for '{gap_query}': {e}") from e
