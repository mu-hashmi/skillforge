"""Corpus building and management."""

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .discovery import Source, SourceType, SourceTier, _is_crawlable_url, _normalize_github_url
from .firecrawl_client import crawl_url
from .exceptions import CorpusBuildError, CorpusLoadError, CorpusUpdateError, FirecrawlCrawlError


def _filter_crawlable_sources(sources: list[Source]) -> list[Source]:
    """Filter out sources that can't be crawled."""
    filtered = []
    for source in sources:
        url = source.url
        # Normalize GitHub URLs
        if "github.com" in url:
            normalized = _normalize_github_url(url)
            if normalized is None:
                print(f"  Skipping non-crawlable GitHub URL: {url}", file=sys.stderr)
                continue
            # Create a new source with normalized URL if changed
            if normalized != url:
                source = Source(
                    url=normalized,
                    title=source.title,
                    source_type=source.source_type,
                    priority=source.priority,
                    tier=source.tier,
                    content=source.content,
                )
        # Check if URL is crawlable
        if not _is_crawlable_url(source.url):
            print(f"  Skipping non-crawlable URL: {source.url}", file=sys.stderr)
            continue
        filtered.append(source)
    return filtered


@dataclass
class PageInfo:
    filename: str
    url: str
    title: str | None
    source_type: str
    priority: int
    tier: int  # 1, 2, or 3
    token_estimate: int


def _slugify(text: str, max_length: int = 50) -> str:
    """Convert text to URL-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_length].strip("-")


def _url_to_filename(url: str, index: int) -> str:
    """Convert URL to safe filename."""
    parsed = urlparse(url)
    path_slug = _slugify(parsed.netloc + parsed.path, max_length=60)
    return f"{index:03d}_{path_slug}.md"


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return len(text) // 4


def _write_page(
    corpus_path: Path,
    url: str,
    title: str | None,
    markdown: str,
    index: int,
    source_type: str,
    priority: int,
    tier: int = 2,
) -> PageInfo:
    """Write a single page to the corpus with frontmatter."""
    filename = _url_to_filename(url, index)
    filepath = corpus_path / filename

    frontmatter = f"""---
url: {url}
title: {title or 'Untitled'}
crawled_at: {datetime.now(timezone.utc).isoformat()}
source_type: {source_type}
priority: {priority}
tier: {tier}
---

"""
    content = frontmatter + markdown
    filepath.write_text(content, encoding="utf-8")

    return PageInfo(
        filename=filename,
        url=url,
        title=title,
        source_type=source_type,
        priority=priority,
        tier=tier,
        token_estimate=_estimate_tokens(markdown),
    )


def _get_base_url(url: str) -> str:
    """Extract base URL (scheme + netloc) from a URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _crawl_domain(
    base_url: str,
    include_paths: list[str] | None,
    limit: int,
    stealth: bool,
) -> tuple[list, list[str]]:
    """Crawl a domain with automatic stealth fallback on anti-bot detection."""
    from .firecrawl_client import crawl_url

    pages = []
    errors = []

    try:
        crawl_result = crawl_url(
            base_url,
            limit=limit,
            include_paths=include_paths,
            stealth=stealth,
        )
        pages = crawl_result.pages

        # Heuristic: if we got very few pages and stealth wasn't used, retry with stealth
        # This catches anti-bot protection that returns partial results
        if len(pages) <= 1 and not stealth and limit > 5:
            print(f"Warning: Only {len(pages)} page(s) crawled from {base_url}, retrying with stealth...", file=sys.stderr)
            try:
                stealth_result = crawl_url(
                    base_url,
                    limit=limit,
                    include_paths=include_paths,
                    stealth=True,
                )
                if len(stealth_result.pages) > len(pages):
                    print(f"  Stealth mode recovered {len(stealth_result.pages)} pages", file=sys.stderr)
                    pages = stealth_result.pages
            except FirecrawlCrawlError as stealth_e:
                print(f"  Stealth retry also failed: {stealth_e}", file=sys.stderr)

    except FirecrawlCrawlError as e:
        # If initial crawl failed completely and stealth wasn't used, try stealth
        if not stealth:
            print(f"Warning: Crawl failed for {base_url}, retrying with stealth...", file=sys.stderr)
            try:
                stealth_result = crawl_url(
                    base_url,
                    limit=limit,
                    include_paths=include_paths,
                    stealth=True,
                )
                pages = stealth_result.pages
                print(f"  Stealth mode succeeded with {len(pages)} pages", file=sys.stderr)
            except FirecrawlCrawlError as stealth_e:
                errors.append(f"{base_url}: {stealth_e} (stealth also failed)")
                print(f"  Stealth retry also failed: {stealth_e}", file=sys.stderr)
        else:
            errors.append(f"{base_url}: {e}")
            print(f"Warning: Failed to crawl {base_url}: {e}", file=sys.stderr)

    return pages, errors


def build_corpus(task: str, sources: list[Source], limit: int = 50, stealth: bool = False) -> Path:
    """
    Build a corpus from discovered sources.

    1. Filter out non-crawlable URLs
    2. Group SEED and MAPPED sources by domain
    3. Crawl each domain with include_paths from mapped URLs
    4. Add any pre-fetched search results
    5. Save pages as markdown with frontmatter
    6. Create manifest.json

    Args:
        stealth: Use Firecrawl stealth proxies for sites with anti-bot protection.
                 If False, will automatically retry with stealth on anti-bot detection.
    """
    # Filter out non-crawlable URLs first
    sources = _filter_crawlable_sources(sources)

    if not sources:
        raise CorpusBuildError("No crawlable sources found after filtering")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    corpus_name = f"corpus_{_slugify(task)}_{timestamp}"
    corpus_path = Path.cwd() / "corpus" / corpus_name
    corpus_path.mkdir(parents=True, exist_ok=True)

    pages_info: list[PageInfo] = []
    page_index = 1
    seen_urls: set[str] = set()
    remaining_limit = limit
    crawl_errors: list[str] = []

    # Find seed URL for manifest
    seed_url = None
    for source in sources:
        if source.source_type == SourceType.SEED:
            seed_url = source.url
            break

    # Group SEED and MAPPED sources by base URL (domain)
    domain_sources: dict[str, list[Source]] = {}
    for source in sources:
        if source.source_type in (SourceType.SEED, SourceType.MAPPED):
            base = _get_base_url(source.url)
            if base not in domain_sources:
                domain_sources[base] = []
            domain_sources[base].append(source)

    # Crawl each domain
    for base_url, domain_srcs in domain_sources.items():
        if remaining_limit <= 0:
            break

        # Build include_paths from the mapped URLs for this domain
        include_paths = []
        # Get the best tier from this domain's sources (lowest tier number = highest priority)
        domain_tier = min(src.tier.value for src in domain_srcs)
        for src in domain_srcs:
            parsed = urlparse(src.url)
            if parsed.path and parsed.path != "/":
                # Convert path to regex pattern (strip leading slash, escape special chars)
                path = parsed.path.lstrip("/").rstrip("/")
                if path:
                    include_paths.append(f"{re.escape(path)}.*")

        # Deduplicate include_paths
        include_paths = list(set(include_paths)) if include_paths else None

        # Crawl with automatic stealth fallback
        crawled_pages, errors = _crawl_domain(
            base_url,
            include_paths,
            remaining_limit,
            stealth,
        )
        crawl_errors.extend(errors)

        for page in crawled_pages:
            if page.url in seen_urls:
                continue
            seen_urls.add(page.url)
            info = _write_page(
                corpus_path,
                url=page.url,
                title=page.title,
                markdown=page.markdown,
                index=page_index,
                source_type="crawled",
                priority=domain_tier + 1,  # Priority based on domain tier
                tier=domain_tier,
            )
            pages_info.append(info)
            page_index += 1
            remaining_limit -= 1
            if remaining_limit <= 0:
                break

    # If all crawls failed, raise error
    if not pages_info and crawl_errors:
        raise CorpusBuildError(
            f"All crawl attempts failed:\n" + "\n".join(crawl_errors)
        )

    # Add any pre-fetched content from search results
    for source in sources:
        if source.content and source.url not in seen_urls:
            seen_urls.add(source.url)
            info = _write_page(
                corpus_path,
                url=source.url,
                title=source.title,
                markdown=source.content,
                index=page_index,
                source_type=source.source_type.value,
                priority=source.priority,
                tier=source.tier.value,
            )
            pages_info.append(info)
            page_index += 1

    if not pages_info:
        raise CorpusBuildError("No pages retrieved for corpus")

    # Write manifest
    total_tokens = sum(p.token_estimate for p in pages_info)
    tier_counts = {1: 0, 2: 0, 3: 0}
    for p in pages_info:
        tier_counts[p.tier] = tier_counts.get(p.tier, 0) + 1
    manifest = {
        "task": task,
        "seed_url": seed_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "pages": [
            {
                "filename": p.filename,
                "url": p.url,
                "title": p.title,
                "source_type": p.source_type,
                "priority": p.priority,
                "tier": p.tier,
                "token_estimate": p.token_estimate,
            }
            for p in pages_info
        ],
        "total_pages": len(pages_info),
        "total_tokens_estimate": total_tokens,
        "tier_breakdown": {
            "tier_1_critical": tier_counts[1],
            "tier_2_supporting": tier_counts[2],
            "tier_3_context": tier_counts[3],
        },
    }
    (corpus_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return corpus_path


def load_corpus_as_context(corpus_path: Path) -> str:
    """Load corpus as a single string for injection into model context."""
    manifest_path = corpus_path / "manifest.json"
    if not manifest_path.exists():
        raise CorpusLoadError(f"No manifest found at {corpus_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    parts = []
    for page_info in manifest["pages"]:
        page_path = corpus_path / page_info["filename"]

        # Strict: missing files are errors
        if not page_path.exists():
            raise CorpusLoadError(
                f"Manifest references missing file: {page_info['filename']}"
            )

        content = page_path.read_text(encoding="utf-8")

        # Strict: empty files are errors
        if not content.strip():
            raise CorpusLoadError(
                f"Corpus file is empty: {page_info['filename']}"
            )

        # Skip frontmatter for context
        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx > 0:
                content = content[end_idx + 3:].strip()

        parts.append(f"=== SOURCE: {page_info['url']} ===\n\n{content}")

    if not parts:
        raise CorpusLoadError(f"No pages found in corpus at {corpus_path}")

    return "\n\n".join(parts)


def add_pages_to_corpus(corpus_path: Path, sources: list[Source]) -> int:
    """Add new pages to an existing corpus (for gap filling)."""
    manifest_path = corpus_path / "manifest.json"
    if not manifest_path.exists():
        raise CorpusUpdateError(f"No manifest found at {corpus_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing_urls = {p["url"] for p in manifest["pages"]}

    page_index = manifest["total_pages"] + 1
    added = 0

    for source in sources:
        if source.url in existing_urls:
            continue
        if not source.content:
            continue

        info = _write_page(
            corpus_path,
            url=source.url,
            title=source.title,
            markdown=source.content,
            index=page_index,
            source_type=source.source_type.value,
            priority=source.priority,
            tier=source.tier.value,
        )
        manifest["pages"].append({
            "filename": info.filename,
            "url": info.url,
            "title": info.title,
            "source_type": info.source_type,
            "priority": info.priority,
            "tier": info.tier,
            "token_estimate": info.token_estimate,
        })
        page_index += 1
        added += 1

    if added > 0:
        manifest["total_pages"] = len(manifest["pages"])
        manifest["total_tokens_estimate"] = sum(
            p["token_estimate"] for p in manifest["pages"]
        )
        # Update tier breakdown
        tier_counts = {1: 0, 2: 0, 3: 0}
        for p in manifest["pages"]:
            tier = p.get("tier", 2)  # Default to tier 2 for backwards compat
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        manifest["tier_breakdown"] = {
            "tier_1_critical": tier_counts[1],
            "tier_2_supporting": tier_counts[2],
            "tier_3_context": tier_counts[3],
        }
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return added
