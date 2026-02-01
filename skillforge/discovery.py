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


def _is_crawlable_url(url: str) -> bool:
    """Check if a URL is actually crawlable (not just a bare domain)."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    full_url = url.lower()

    # Always allow certain valuable paths
    valuable_patterns = [
        "/advisories", "/security", "/docs", "/documentation",
        "/guide", "/tutorial", "/reference", "/api-reference",
    ]
    for pattern in valuable_patterns:
        if pattern in full_url:
            return True

    # Reject bare domains with no path
    # e.g., https://github.com, https://twitter.com
    if not path:
        # Exception: docs domains are usually crawlable at root
        if _looks_like_docs_domain(url):
            return True
        return False

    # Reject known non-crawlable patterns
    non_crawlable_patterns = [
        # Social media / non-docs sites
        "twitter.com", "x.com", "facebook.com", "linkedin.com",
        "youtube.com", "reddit.com", "discord.com", "slack.com",
        # Login/auth pages
        "/login", "/signin", "/signup", "/auth",
        # API endpoints (not docs)
        "/api/v", "/v1/", "/v2/", "/v3/",
    ]

    for pattern in non_crawlable_patterns:
        if pattern in full_url:
            # Exception: /api/ in docs context is fine
            if "/api/" in full_url and ("docs" in full_url or "reference" in full_url):
                continue
            return False

    return True


def _normalize_github_url(url: str) -> str | None:
    """Convert GitHub URLs to their most crawlable form.

    Returns None if the URL should be skipped entirely.
    """
    parsed = urlparse(url)
    if "github.com" not in parsed.netloc:
        return url

    path = parsed.path.strip("/")

    # Skip bare github.com
    if not path:
        return None

    # Always keep valuable paths
    valuable_paths = ["advisories", "security", "wiki", "discussions"]
    if any(v in path for v in valuable_paths):
        return url

    # Skip non-content pages
    skip_patterns = [
        "login", "signup", "settings", "notifications",
        "marketplace", "explore", "trending", "collections",
        "sponsors", "orgs", "enterprises",
    ]
    if any(path.startswith(p) for p in skip_patterns):
        return None

    parts = path.split("/")

    # For repos, prefer the README or docs
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        # Skip if repo part looks like a non-content page
        if repo in skip_patterns:
            return None
        # If it's just owner/repo, that's fine (will show README)
        # If it has /blob/ or /tree/, keep it
        return url

    # Single path segment (user profile or top-level page) - skip most
    if len(parts) == 1:
        # Keep advisories at root level
        if parts[0] == "advisories":
            return url
        return None

    return url


def discover_sources(
    task: str,
    seed_url: str,
    *,
    map_limit: int = 200,
    search_limit: int = 5,
) -> list[Source]:
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
        map_result = map_url(seed_url, limit=map_limit)
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

    # Search for supplementary materials (best-effort with stealth fallback)
    search_query = f"{task} documentation tutorial"
    try:
        search_result = search(search_query, limit=search_limit, scrape=True)
        # If no results, try stealth
        if not search_result.results:
            print(f"Warning: Supplementary search returned no results, trying stealth...", file=sys.stderr)
            search_result = search(search_query, limit=search_limit, scrape=True, stealth=True)
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
        # Try stealth fallback before giving up
        try:
            search_result = search(search_query, limit=search_limit, scrape=True, stealth=True)
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
        except Exception as stealth_e:
            print(f"Warning: Supplementary search failed for '{search_query}': {e} (stealth also failed: {stealth_e})", file=sys.stderr)

    # Deduplicate and sort by priority (tier is reflected in priority)
    sources = _deduplicate_sources(sources)
    sources.sort(key=lambda s: (s.priority, s.url))

    return sources


def discover_sources_from_task(
    task: str,
    max_seeds: int = 3,
    *,
    search_limit: int = 5,
    map_limit: int = 200,
) -> list[Source]:
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
            search_result = search(query, limit=search_limit, scrape=False)
            # If no results, try stealth
            if not search_result.results:
                print(f"Warning: Seed search returned no results for '{query}', trying stealth...", file=sys.stderr)
                search_result = search(query, limit=search_limit, scrape=False, stealth=True)
        except Exception as e:
            # Try stealth fallback
            try:
                search_result = search(query, limit=search_limit, scrape=False, stealth=True)
            except Exception as stealth_e:
                print(f"Warning: Seed search failed for '{query}': {e} (stealth also failed)", file=sys.stderr)
                continue
        for item in search_result.results:
            url = item.url
            # Normalize GitHub URLs
            if "github.com" in url:
                url = _normalize_github_url(url)
                if url is None:
                    continue
            # Skip non-crawlable URLs
            if not _is_crawlable_url(url):
                print(f"  Skipping non-crawlable URL: {item.url}", file=sys.stderr)
                continue
            candidate_urls.append(url)

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
            sources.extend(
                discover_sources(
                    task,
                    seed_url,
                    map_limit=map_limit,
                    search_limit=search_limit,
                )
            )
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


def _simplify_gap_query(query: str) -> str:
    """Simplify verbose gap queries into shorter, more effective search terms.

    Bad: "Stripe API subscription creation endpoint documentation including authentication and code examples"
    Good: "Stripe API create subscription"
    """
    # Words that add noise to search queries
    noise_words = {
        "documentation", "docs", "official", "complete", "detailed", "comprehensive",
        "including", "example", "examples", "code", "tutorial", "guide", "reference",
        "endpoint", "endpoints", "authentication", "implementation", "usage", "using",
        "information", "details", "about", "regarding", "related", "specific",
        "how", "to", "the", "a", "an", "for", "with", "and", "or", "in", "on",
    }

    words = query.lower().split()
    simplified = [w for w in words if w not in noise_words]

    # If we stripped too much, keep first 5 words of original
    if len(simplified) < 2:
        simplified = words[:5]

    # Cap at 6 words max
    result = " ".join(simplified[:6])
    return result if result else query


def _extract_docs_domain(query: str) -> str | None:
    """Try to extract a likely documentation domain from a gap query.

    Examples:
        "Stripe API create subscription" -> "https://docs.stripe.com/api"
        "Firecrawl crawl endpoint" -> "https://docs.firecrawl.dev"
    """
    query_lower = query.lower()

    # Known API/service -> docs URL mappings
    docs_mappings = {
        "stripe": "https://docs.stripe.com/api",
        "firecrawl": "https://docs.firecrawl.dev",
        "openai": "https://platform.openai.com/docs",
        "anthropic": "https://docs.anthropic.com",
        "github": "https://docs.github.com",
        "github security": "https://github.com/advisories",
        "github advisory": "https://github.com/advisories",
        "security advisory": "https://github.com/advisories",
        "aws": "https://docs.aws.amazon.com",
        "google cloud": "https://cloud.google.com/docs",
        "azure": "https://learn.microsoft.com/azure",
        "vercel": "https://vercel.com/docs",
        "next.js": "https://nextjs.org/docs",
        "nextjs": "https://nextjs.org/docs",
        "supabase": "https://supabase.com/docs",
        "twilio": "https://www.twilio.com/docs",
        "sendgrid": "https://docs.sendgrid.com",
        "resend": "https://resend.com/docs",
        "redis": "https://redis.io/docs",
        "mongodb": "https://www.mongodb.com/docs",
        "postgres": "https://www.postgresql.org/docs",
        "cuda": "https://docs.nvidia.com/cuda",
        "pytorch": "https://pytorch.org/docs",
        "tensorflow": "https://www.tensorflow.org/api_docs",
        "numpy": "https://numpy.org/doc",
        "pandas": "https://pandas.pydata.org/docs",
        "react": "https://react.dev/reference",
        "vue": "https://vuejs.org/guide",
        "svelte": "https://svelte.dev/docs",
    }

    for service, docs_url in docs_mappings.items():
        if service in query_lower:
            return docs_url

    return None


def search_for_gap(gap_query: str, stealth: bool = False) -> list[Source]:
    """Search for specific missing information to fill a knowledge gap.

    Uses simplified queries for better search results. Falls back to crawling
    known docs URLs if search repeatedly fails.
    """
    # Simplify verbose queries
    simplified_query = _simplify_gap_query(gap_query)
    if simplified_query != gap_query.lower().strip():
        print(f"  Simplified query: '{gap_query}' -> '{simplified_query}'", file=sys.stderr)

    result = None

    # First attempt with simplified query
    try:
        result = search(simplified_query, limit=5, scrape=True, stealth=stealth)
    except Exception as e:
        print(f"Warning: Gap search failed for '{simplified_query}': {e}", file=sys.stderr)
        result = None

    # If no results, check if we can fall back to crawling a known docs domain
    if result is None or len(result.results) == 0:
        docs_url = _extract_docs_domain(gap_query)
        if docs_url:
            print(f"  Search returned no results, falling back to crawl: {docs_url}", file=sys.stderr)
            try:
                from .firecrawl_client import crawl_url
                crawl_result = crawl_url(docs_url, limit=10, stealth=stealth)
                sources = []
                for page in crawl_result.pages:
                    tier = _classify_tier(page.url)
                    sources.append(Source(
                        url=page.url,
                        title=page.title,
                        source_type=SourceType.SEARCHED,
                        priority=_tier_to_priority(tier, SourceType.SEARCHED),
                        tier=tier,
                        content=page.markdown,
                    ))
                if sources:
                    print(f"  Crawl fallback found {len(sources)} pages", file=sys.stderr)
                    sources.sort(key=lambda s: s.priority)
                    return sources
            except Exception as crawl_e:
                print(f"  Crawl fallback also failed: {crawl_e}", file=sys.stderr)

    # Return whatever we got from search (may be empty)
    sources = []
    if result:
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
