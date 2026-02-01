"""Firecrawl-powered search CLI."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import get_firecrawl_api_key
from .exceptions import FirecrawlSearchError
from .firecrawl_client import search


def _read_query(args: list[str]) -> str:
    if args:
        query = " ".join(args).strip()
    else:
        query = sys.stdin.read().strip()
    return query


def _write_cache(cache_path: Path, query: str, results) -> None:
    lines = [
        "# Firecrawl Search Results",
        "",
        f"Query: {query}",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Results",
    ]

    for idx, item in enumerate(results, start=1):
        title = item.title or item.url
        lines.append(f"### {idx}. {title}")
        lines.append(f"- URL: {item.url}")
        if item.description:
            lines.append(f"- Description: {item.description}")
        if item.markdown:
            lines.append("")
            lines.append(item.markdown.strip())
        lines.append("")

    cache_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _print_summary(cache_path: Path, query: str, results) -> None:
    if not results:
        print(f"No results found for: {query}")
        print("Try a different query or use /deep-dive with a specific docs URL.")
        return
    print("Top findings:")
    for idx, item in enumerate(results[:3], start=1):
        title = item.title or item.url
        desc = item.description or ""
        if desc:
            print(f"{idx}. {title} - {desc}")
        else:
            print(f"{idx}. {title}")
    print(f"Cache file: {cache_path}")
    print(f"Search query: {query}")


def run(query: str, limit: int = 10, retries: int = 3, github: bool = False) -> Path:
    if not query:
        raise ValueError("Empty query. Provide error text or a search query.")

    # Validate Firecrawl credentials early.
    get_firecrawl_api_key()

    categories = ["github"] if github else None

    last_error: Exception | None = None
    result = None
    for attempt in range(1, retries + 1):
        try:
            result = search(query, limit=limit, scrape=True, categories=categories)
            break
        except Exception as e:  # noqa: BLE001 - surface clear failure below
            last_error = e
            if attempt < retries:
                time.sleep(1.5 * attempt)

    if result is None:
        message = f"Firecrawl search failed after {retries} attempts."
        if last_error:
            message += f" Last error: {last_error}"
        raise FirecrawlSearchError(message)

    cache_dir = Path.cwd() / ".skillforge" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_path = cache_dir / f"{timestamp}_search.md"

    _write_cache(cache_path, query, result.results)
    _print_summary(cache_path, query, result.results)
    return cache_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Firecrawl search utility.")
    parser.add_argument("query", nargs="*", help="Search query or pasted stderr")
    parser.add_argument("--limit", type=int, default=10, help="Number of results to fetch")
    parser.add_argument("--retries", type=int, default=3, help="Retry attempts on failure")
    parser.add_argument("--github", action="store_true", help="Search GitHub issues/discussions only")
    args = parser.parse_args()

    query = _read_query(args.query)
    try:
        run(query, limit=args.limit, retries=args.retries, github=args.github)
    except (ValueError, FirecrawlSearchError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
