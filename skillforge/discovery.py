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


class SourceTier(Enum):
    """Domain layering for source authority (per CLAUDE.md)."""
    TIER_1 = 1  # Critical: Official documentation
    TIER_2 = 2  # Supporting: GitHub, Arxiv
    TIER_3 = 3  # Context: Blogs, Stack Overflow


# Tier 1: Official documentation domains/patterns
TIER_1_PATTERNS = [
    "docs.",           # docs.python.org, docs.nvidia.com
    ".readthedocs.",   # *.readthedocs.io
    "/docs/",          # path-based docs
    "/documentation/",
    "/reference/",
    "/api/",
]

# Tier 2: Known technical hubs
TIER_2_DOMAINS = [
    "github.com",
    "gitlab.com",
    "arxiv.org",
    "developer.",      # developer.apple.com, developer.mozilla.org
    "devdocs.io",
]

# Tier 3: Context sources (use with caution)
TIER_3_DOMAINS = [
    "stackoverflow.com",
    "stackexchange.com",
    "medium.com",
    "dev.to",
    "blog.",
    "towardsdatascience.com",
]


@dataclass
class Source:
    url: str
    title: str | None
    source_type: SourceType
    priority: int  # 1 = high, 10 = low
    tier: SourceTier = SourceTier.TIER_3
    content: str | None = None


def _classify_tier(url: str, is_seed: bool = False) -> SourceTier:
    """Classify URL into source authority tier."""
    if is_seed:
        return SourceTier.TIER_1  # Seed URL is always Tier 1

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    full_url = url.lower()

    # Check Tier 1 patterns
    for pattern in TIER_1_PATTERNS:
        if pattern in domain or pattern in path:
            return SourceTier.TIER_1

    # Check Tier 2 domains
    for tier2 in TIER_2_DOMAINS:
        if tier2 in domain:
            return SourceTier.TIER_2

    # Check Tier 3 domains
    for tier3 in TIER_3_DOMAINS:
        if tier3 in domain:
            return SourceTier.TIER_3

    # Default: if on same domain as a docs site, treat as Tier 2
    return SourceTier.TIER_2


def _tier_to_priority(tier: SourceTier, source_type: SourceType) -> int:
    """Convert tier + source type to priority value."""
    # Base priority by tier
    base = {
        SourceTier.TIER_1: 1,
        SourceTier.TIER_2: 4,
        SourceTier.TIER_3: 7,
    }[tier]

    # Adjust by source type
    if source_type == SourceType.SEED:
        return 1  # Seed always highest
    elif source_type == SourceType.MAPPED:
        return base + 1
    else:  # SEARCHED
        return base + 2


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


def _looks_like_docs_domain(url: str) -> bool:
    """Heuristic to identify documentation-oriented domains."""
    netloc = urlparse(url).netloc.lower()
    return any(
        indicator in netloc
        for indicator in ("docs.", "developer.", "developers.", "learn.", "devdocs.")
    )


def discover_sources(task: str, seed_url: str) -> list[Source]:
    """
    Discover documentation sources for a task.

    1. Map the seed URL to find all pages
    2. Filter to docs-like paths
    3. Classify sources into tiers (Tier 1 > Tier 2 > Tier 3)
    4. Search for supplementary GitHub/tutorial content
    5. Return deduplicated, priority-sorted list
    """
    sources: list[Source] = []

    # Add seed URL as highest priority (always Tier 1)
    seed_tier = SourceTier.TIER_1
    sources.append(Source(
        url=seed_url,
        title=None,
        source_type=SourceType.SEED,
        priority=1,
        tier=seed_tier,
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
                tier = _classify_tier(url)
                # Same domain as seed inherits Tier 1
                if link_domain == seed_domain:
                    tier = SourceTier.TIER_1
                sources.append(Source(
                    url=url,
                    title=link.get("title"),
                    source_type=SourceType.MAPPED,
                    priority=_tier_to_priority(tier, SourceType.MAPPED),
                    tier=tier,
                ))
    except Exception as e:
        raise DiscoveryError(f"Failed to map seed URL {seed_url}: {e}") from e

    # Search for supplementary materials (best-effort with warning)
    search_query = f"{task} documentation tutorial"
    try:
        search_result = search(search_query, limit=5, scrape=True)
        for item in search_result.results:
            tier = _classify_tier(item.url)
            sources.append(Source(
                url=item.url,
                title=item.title,
                source_type=SourceType.SEARCHED,
                priority=_tier_to_priority(tier, SourceType.SEARCHED),
                tier=tier,
                content=item.markdown,
            ))
    except Exception as e:
        # Log warning instead of silent pass
        print(f"Warning: Supplementary search failed for '{search_query}': {e}", file=sys.stderr)

    # Deduplicate and sort by priority (tier is reflected in priority)
    sources = _deduplicate_sources(sources)
    sources.sort(key=lambda s: (s.priority, s.url))

    return sources


def discover_sources_from_task(task: str, max_seeds: int = 3) -> list[Source]:
    """
    Discover sources without a seed URL by searching for official docs.

    This enables automatic context discovery when Claude fails a task -
    it searches for relevant documentation and uses top results as seeds.

    1. Search for official documentation related to the task
    2. Filter results to docs-like URLs/domains (prefer Tier 1)
    3. Use top results as seed URLs for deeper discovery
    4. Apply same tiering system as seeded discovery
    """
    # Extract key terms from task (remove common verbs/articles)
    stop_words = {"use", "the", "a", "an", "to", "for", "with", "how", "do", "i", "can", "build", "create", "make"}
    words = task.lower().split()
    key_terms = " ".join(w for w in words if w not in stop_words) or task

    # Try progressively simpler queries
    search_queries = [
        f"{key_terms} documentation",
        f"{key_terms} docs",
        f"{key_terms} api",
        task,  # fallback to full task as query
    ]
    candidate_urls: list[str] = []

    for query in search_queries:
        try:
            # Use scrape=False for discovery - we'll crawl these URLs later
            search_result = search(query, limit=5, scrape=False)
        except Exception as e:
            print(f"Warning: Seed search failed for '{query}': {e}", file=sys.stderr)
            continue
        for item in search_result.results:
            candidate_urls.append(item.url)

    if not candidate_urls:
        raise DiscoveryError(
            "Unable to discover any documentation sources automatically. "
            "Provide --seed to continue."
        )

    # Prefer docs-like URLs/domains (these are likely Tier 1)
    docs_candidates = [
        url for url in candidate_urls
        if _is_docs_url(url) or _looks_like_docs_domain(url)
    ]
    if docs_candidates:
        candidate_urls = docs_candidates

    # Deduplicate candidate URLs
    seen_urls = set()
    unique_candidates = []
    for url in candidate_urls:
        normalized = url.rstrip("/")
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            unique_candidates.append(url)

    # Use top candidates as seeds and run full discovery on each
    sources: list[Source] = []
    for seed_url in unique_candidates[:max_seeds]:
        try:
            sources.extend(discover_sources(task, seed_url))
        except DiscoveryError as e:
            print(f"Warning: Discovery failed for auto-seed {seed_url}: {e}", file=sys.stderr)
            continue

    if not sources:
        raise DiscoveryError(
            "Auto-discovery found candidates but failed to crawl any. "
            "Provide --seed to continue."
        )

    sources = _deduplicate_sources(sources)
    sources.sort(key=lambda s: (s.priority, s.url))
    return sources


def search_for_gap(gap_query: str, stealth: bool = False) -> list[Source]:
    """Search for specific missing information to fill a knowledge gap."""
    try:
        result = search(gap_query, limit=5, scrape=True, stealth=stealth)
        sources = []
        for item in result.results:
            tier = _classify_tier(item.url)
            sources.append(Source(
                url=item.url,
                title=item.title,
                source_type=SourceType.SEARCHED,
                priority=_tier_to_priority(tier, SourceType.SEARCHED),
                tier=tier,
                content=item.markdown,
            ))
        # Sort by tier priority so Tier 1 sources come first
        sources.sort(key=lambda s: s.priority)
        return sources
    except Exception as e:
        raise SearchError(f"Gap search failed for '{gap_query}': {e}") from e
