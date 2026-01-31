"""Corpus building and management."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .discovery import Source, SourceType
from .firecrawl_client import crawl_url, CrawledPage
from .exceptions import CorpusBuildError, CorpusLoadError, CorpusUpdateError


@dataclass
class PageInfo:
    filename: str
    url: str
    title: str | None
    source_type: str
    priority: int
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
        token_estimate=_estimate_tokens(markdown),
    )


def build_corpus(task: str, sources: list[Source], limit: int = 50) -> Path:
    """
    Build a corpus from discovered sources.

    1. Crawl the seed URL
    2. Add any pre-fetched search results
    3. Save pages as markdown with frontmatter
    4. Create manifest.json
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    corpus_name = f"corpus_{_slugify(task)}_{timestamp}"
    corpus_path = Path.cwd() / "corpus" / corpus_name
    corpus_path.mkdir(parents=True, exist_ok=True)

    pages_info: list[PageInfo] = []
    page_index = 1
    seen_urls: set[str] = set()

    # Find seed URL (first source with SEED type)
    seed_url = None
    for source in sources:
        if source.source_type == SourceType.SEED:
            seed_url = source.url
            break

    # Crawl the seed URL
    if seed_url:
        try:
            crawl_result = crawl_url(seed_url, limit=limit)
            for page in crawl_result.pages:
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
                    priority=2,
                )
                pages_info.append(info)
                page_index += 1
        except Exception as e:
            raise CorpusBuildError(f"Failed to crawl seed URL {seed_url}: {e}") from e

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
            )
            pages_info.append(info)
            page_index += 1

    if not pages_info:
        raise CorpusBuildError("No pages retrieved for corpus")

    # Write manifest
    total_tokens = sum(p.token_estimate for p in pages_info)
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
                "token_estimate": p.token_estimate,
            }
            for p in pages_info
        ],
        "total_pages": len(pages_info),
        "total_tokens_estimate": total_tokens,
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
        if page_path.exists():
            content = page_path.read_text(encoding="utf-8")
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
        )
        manifest["pages"].append({
            "filename": info.filename,
            "url": info.url,
            "title": info.title,
            "source_type": info.source_type,
            "priority": info.priority,
            "token_estimate": info.token_estimate,
        })
        page_index += 1
        added += 1

    if added > 0:
        manifest["total_pages"] = len(manifest["pages"])
        manifest["total_tokens_estimate"] = sum(
            p["token_estimate"] for p in manifest["pages"]
        )
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return added
