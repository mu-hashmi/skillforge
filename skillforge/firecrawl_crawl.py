"""Deep documentation crawl CLI."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import get_firecrawl_api_key
from .exceptions import FirecrawlCrawlError
from .firecrawl_client import crawl_url


def _slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:64] or "untitled"


def _domain_to_dirname(url: str) -> str:
    domain = urlparse(url).netloc
    return domain.replace(".", "_")


def run(url: str, limit: int = 50) -> Path:
    """Crawl a documentation site and save to knowledge base."""
    get_firecrawl_api_key()

    domain_dir = _domain_to_dirname(url)
    knowledge_dir = Path.cwd() / ".skillforge" / "knowledge" / domain_dir
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    print(f"Crawling {url} (limit: {limit} pages)...")
    crawl_result = crawl_url(url, limit=limit)
    print(f"Crawled {crawl_result.total} pages")

    manifest_entries = []
    for i, page in enumerate(crawl_result.pages):
        filename = f"{i:03d}_{_slugify(page.title or 'untitled')}.md"
        filepath = knowledge_dir / filename

        content = f"""---
url: {page.url}
title: {page.title or 'Untitled'}
crawled_at: {datetime.now(timezone.utc).isoformat()}
---

{page.markdown}
"""
        filepath.write_text(content, encoding="utf-8")
        manifest_entries.append({
            "file": filename,
            "url": page.url,
            "title": page.title,
        })

    manifest = {
        "source_url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "total_pages": len(crawl_result.pages),
        "pages": manifest_entries,
    }
    (knowledge_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"Saved {len(crawl_result.pages)} pages to {knowledge_dir}")
    if crawl_result.failed_urls:
        print(f"Failed to crawl: {len(crawl_result.failed_urls)} URLs")

    return knowledge_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl an entire documentation site and save to knowledge base."
    )
    parser.add_argument("url", help="Documentation URL to crawl")
    parser.add_argument(
        "--limit", type=int, default=50, help="Maximum pages to crawl (default: 50)"
    )
    args = parser.parse_args()

    try:
        run(args.url, limit=args.limit)
    except FirecrawlCrawlError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
