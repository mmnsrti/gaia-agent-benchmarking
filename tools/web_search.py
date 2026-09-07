"""Web search provider abstraction for V1 single-shot retrieval using Tavily.

Provides a deterministic, minimal tool to execute exactly one web search
per question using Tavily's basic search API, returning compact evidence snippets
without using Tavily's generated answer field, browser automation, or query rewriting.
"""

import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


@dataclass
class SearchResultItem:
    """A single retrieved web search result item."""
    title: str
    url: str
    content: str
    score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "score": self.score,
        }


@dataclass
class WebSearchResult:
    """Encapsulates the output and metadata of a single web search call."""
    query: str
    results: List[SearchResultItem] = field(default_factory=list)
    success: bool = False
    latency_seconds: float = 0.0
    call_count: int = 1
    provider: str = "tavily"
    search_depth: str = "basic"
    max_results: int = 5
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def format_evidence_block(self) -> str:
        """Formats retrieved snippets into a compact, structured evidence block."""
        if not self.results:
            return "No web search results found."

        blocks = []
        for idx, item in enumerate(self.results, start=1):
            snippet = item.content.strip() if item.content else ""
            blocks.append(
                f"[{idx}] Title: {item.title}\n"
                f"    URL: {item.url}\n"
                f"    Snippet: {snippet}"
            )
        return "\n\n".join(blocks)


class TavilySearchTool:
    """Official Tavily Search provider tool for V1."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_results: int = 5,
        search_depth: str = "basic",
    ):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.max_results = max_results
        self.search_depth = search_depth
        self._client = None

        if self.api_key and TavilyClient is not None:
            try:
                self._client = TavilyClient(api_key=self.api_key)
            except Exception:
                self._client = None

    def search(self, query: str) -> WebSearchResult:
        """Executes a single search query against the Tavily Search API.

        Deterministic configuration:
        - search_depth: 'basic'
        - max_results: 5
        - include_answer: False (never use generated answer)
        - include_raw_content: False
        - include_images: False
        """
        start_time = time.time()

        if not query or not query.strip():
            return WebSearchResult(
                query=query,
                results=[],
                success=False,
                latency_seconds=0.0,
                call_count=1,
                provider="tavily",
                search_depth=self.search_depth,
                max_results=self.max_results,
                error_type="EmptyQueryError",
                error_message="Search query cannot be empty.",
            )

        if not self.api_key:
            return WebSearchResult(
                query=query.strip(),
                results=[],
                success=False,
                latency_seconds=0.0,
                call_count=1,
                provider="tavily",
                search_depth=self.search_depth,
                max_results=self.max_results,
                error_type="MissingAPIKeyError",
                error_message="TAVILY_API_KEY is not set in environment.",
            )

        if TavilyClient is None:
            return WebSearchResult(
                query=query.strip(),
                results=[],
                success=False,
                latency_seconds=0.0,
                call_count=1,
                provider="tavily",
                search_depth=self.search_depth,
                max_results=self.max_results,
                error_type="DependencyMissingError",
                error_message="tavily-python is not installed.",
            )

        try:
            if self._client is None:
                self._client = TavilyClient(api_key=self.api_key)

            raw_response = self._client.search(
                query=query.strip(),
                search_depth=self.search_depth,
                max_results=self.max_results,
                include_answer=False,
                include_raw_content=False,
                include_images=False,
                auto_parameters=False,
            )
            latency = round(time.time() - start_time, 2)

            raw_results = raw_response.get("results", []) if isinstance(raw_response, dict) else []
            parsed_items: List[SearchResultItem] = []
            for r in raw_results:
                parsed_items.append(
                    SearchResultItem(
                        title=str(r.get("title") or "").strip(),
                        url=str(r.get("url") or "").strip(),
                        content=str(r.get("content") or "").strip(),
                        score=r.get("score"),
                    )
                )

            return WebSearchResult(
                query=query.strip(),
                results=parsed_items,
                success=True,
                latency_seconds=latency,
                call_count=1,
                provider="tavily",
                search_depth=self.search_depth,
                max_results=self.max_results,
            )

        except Exception as e:
            latency = round(time.time() - start_time, 2)
            return WebSearchResult(
                query=query.strip(),
                results=[],
                success=False,
                latency_seconds=latency,
                call_count=1,
                provider="tavily",
                search_depth=self.search_depth,
                max_results=self.max_results,
                error_type=type(e).__name__,
                error_message=str(e),
            )

