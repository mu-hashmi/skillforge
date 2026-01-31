"""Firecrawl API wrapper with error handling."""

from dataclasses import dataclass, field
from firecrawl import Firecrawl

from .config import get_firecrawl_api_key
from .exceptions import FirecrawlMapError, FirecrawlCrawlError, FirecrawlSearchError


@dataclass
class MapResult:
    urls: list[dict]  # [{url, title, description}]
    total: int


@dataclass
class CrawledPage:
    url: str
    title: str | None
    markdown: str
    metadata: dict = field(default_factory=dict)


@dataclass
class CrawlResult:
    pages: list[CrawledPage]
    total: int
    failed_urls: list[str] = field(default_factory=list)


@dataclass
class SearchResultItem:
    url: str
    title: str | None
    description: str | None
    markdown: str | None


@dataclass
class SearchResult:
    results: list[SearchResultItem]
    query: str


def _get_client() -> Firecrawl:
    return Firecrawl(api_key=get_firecrawl_api_key())


def map_url(url: str, limit: int = 100) -> MapResult:
    """Map a URL to discover all pages on the site."""
    client = _get_client()
    try:
        result = client.map(url, limit=limit)
        links = []
        if hasattr(result, "links") and result.links:
            for link in result.links:
                if isinstance(link, str):
                    links.append({"url": link, "title": None, "description": None})
                else:
                    links.append({
                        "url": getattr(link, "url", link) if hasattr(link, "url") else str(link),
                        "title": getattr(link, "title", None),
                        "description": getattr(link, "description", None),
                    })
        elif isinstance(result, dict) and "links" in result:
            for link in result["links"]:
                if isinstance(link, str):
                    links.append({"url": link, "title": None, "description": None})
                else:
                    links.append({
                        "url": link.get("url", str(link)),
                        "title": link.get("title"),
                        "description": link.get("description"),
                    })
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, str):
                    links.append({"url": item, "title": None, "description": None})
                else:
                    links.append({
                        "url": getattr(item, "url", str(item)),
                        "title": getattr(item, "title", None),
                        "description": getattr(item, "description", None),
                    })
        if not links:
            raise FirecrawlMapError(f"Map returned no URLs for {url}")
        return MapResult(urls=links, total=len(links))
    except FirecrawlMapError:
        raise
    except Exception as e:
        raise FirecrawlMapError(f"Failed to map {url}: {e}") from e


def crawl_url(
    url: str,
    limit: int = 50,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> CrawlResult:
    """Crawl a URL and its subpages."""
    client = _get_client()
    try:
        kwargs = {"limit": limit}
        if include_paths:
            kwargs["include_paths"] = include_paths
        if exclude_paths:
            kwargs["exclude_paths"] = exclude_paths

        result = client.crawl(url, **kwargs)

        pages = []
        failed = []

        # Handle different result formats
        data = None
        if hasattr(result, "data"):
            data = result.data
        elif isinstance(result, dict) and "data" in result:
            data = result["data"]
        elif isinstance(result, list):
            data = result

        if data:
            for doc in data:
                markdown = None
                doc_url = url
                title = None
                metadata = {}

                if hasattr(doc, "markdown"):
                    markdown = doc.markdown
                    if hasattr(doc, "metadata"):
                        metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
                        doc_url = metadata.get("url") or metadata.get("sourceURL") or url
                        title = metadata.get("title")
                elif isinstance(doc, dict):
                    markdown = doc.get("markdown")
                    metadata = doc.get("metadata", {})
                    doc_url = metadata.get("url") or metadata.get("sourceURL") or url
                    title = metadata.get("title")

                if markdown:
                    pages.append(CrawledPage(
                        url=doc_url,
                        title=title,
                        markdown=markdown,
                        metadata=metadata,
                    ))
                else:
                    failed.append(doc_url)

        if not pages:
            raise FirecrawlCrawlError(f"Crawl returned no pages for {url}")

        return CrawlResult(pages=pages, total=len(pages), failed_urls=failed)
    except FirecrawlCrawlError:
        raise
    except Exception as e:
        raise FirecrawlCrawlError(f"Failed to crawl {url}: {e}") from e


def search(
    query: str,
    limit: int = 10,
    scrape: bool = True,
) -> SearchResult:
    """Search the web for relevant content."""
    client = _get_client()
    try:
        kwargs = {"limit": limit}
        if scrape:
            kwargs["scrape_options"] = {"formats": ["markdown"]}

        result = client.search(query, **kwargs)

        items = []
        web_results = None

        if hasattr(result, "web"):
            web_results = result.web
        elif isinstance(result, dict) and "web" in result:
            web_results = result["web"]
        elif hasattr(result, "data"):
            web_results = result.data
        elif isinstance(result, list):
            web_results = result

        if web_results:
            for item in web_results:
                if hasattr(item, "url"):
                    items.append(SearchResultItem(
                        url=item.url,
                        title=getattr(item, "title", None),
                        description=getattr(item, "description", None),
                        markdown=getattr(item, "markdown", None),
                    ))
                elif isinstance(item, dict):
                    items.append(SearchResultItem(
                        url=item["url"],
                        title=item.get("title"),
                        description=item.get("description"),
                        markdown=item.get("markdown"),
                    ))

        if not items:
            raise FirecrawlSearchError(f"Search returned no results for '{query}'")

        return SearchResult(results=items, query=query)
    except FirecrawlSearchError:
        raise
    except Exception as e:
        raise FirecrawlSearchError(f"Search failed for '{query}': {e}") from e
