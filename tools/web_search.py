"""Web search provider abstraction for V1 single-shot retrieval using Tavily.

Provides a deterministic, minimal tool to execute exactly one web search
per question using Tavily's basic search API, returning compact evidence snippets
without using Tavily's generated answer field, browser automation, or query rewriting.
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv, find_dotenv

# Automatically load environment variables from .env if present
load_dotenv(find_dotenv() or ".env")

logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


def discover_tavily_api_keys(api_key: Optional[str] = None, env_path: Optional[str] = None) -> List[str]:
    """Discovers all available Tavily API keys from explicit args, os.environ, and the .env file.

    Supports:
    - Explicit api_key argument (single key or comma/semicolon-separated)
    - TAVILY_API_KEY, TAVILY_API_KEYS, TAVILY_API_KEY_1, TAVILY_API_KEY_2, etc. in os.environ
    - Multiple duplicate TAVILY_API_KEY=... lines in the .env file
    """
    keys: List[str] = []

    # 1. Explicit api_key argument takes precedence
    if api_key:
        for sub in re.split(r"[,;]", api_key):
            sub = sub.strip().strip("\"'")
            if sub and sub not in keys:
                keys.append(sub)
        return keys

    # 2. Check os.environ for TAVILY_API_KEY, TAVILY_API_KEYS, TAVILY_API_KEY_*
    env_keys: List[str] = []
    primary = os.getenv("TAVILY_API_KEY")
    if primary:
        for sub in re.split(r"[,;]", primary):
            sub = sub.strip().strip("\"'")
            if sub and sub not in env_keys:
                env_keys.append(sub)

    for k in sorted(os.environ.keys()):
        if k.startswith("TAVILY_API_KEY") and k != "TAVILY_API_KEY":
            val = os.environ[k]
            for sub in re.split(r"[,;]", val):
                sub = sub.strip().strip("\"'")
                if sub and sub not in env_keys:
                    env_keys.append(sub)

    for k in env_keys:
        if k not in keys:
            keys.append(k)

    # 3. If Tavily keys exist in environment, parse .env file to discover all duplicate lines
    if env_keys:
        target_env = env_path or find_dotenv() or ".env"
        if os.path.exists(target_env):
            try:
                with open(target_env, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        m = re.match(r"^(TAVILY_API_KEY\w*)\s*=\s*(.*)$", line)
                        if m:
                            val = m.group(2).strip().strip("\"'")
                            for sub in re.split(r"[,;]", val):
                                sub = sub.strip()
                                if sub and sub not in keys and not sub.startswith("your_"):
                                    keys.append(sub)
            except Exception:
                pass

    return keys


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
    provider_query: str = ""
    search_query_truncated: bool = False
    original_query_length: int = 0
    provider_query_length: int = 0
    results: List[SearchResultItem] = field(default_factory=list)
    success: bool = False
    latency_seconds: float = 0.0
    call_count: int = 1
    provider: str = "tavily"
    search_depth: str = "basic"
    max_results: int = 5
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        cleaned = self.query.strip() if self.query else ""
        if not self.original_query_length and cleaned:
            self.original_query_length = len(cleaned)
        if not self.provider_query and cleaned:
            self.provider_query = cleaned[:1500]
        if not self.provider_query_length and self.provider_query:
            self.provider_query_length = len(self.provider_query)
        if not self.search_query_truncated and self.original_query_length > 1500:
            self.search_query_truncated = True

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
    """Official Tavily Search provider tool with multi-key discovery and automatic rotation."""

    _shared_key_index: int = 0

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_results: int = 5,
        search_depth: str = "basic",
        env_path: Optional[str] = None,
    ):
        self._explicit_key = api_key is not None
        self.api_keys = discover_tavily_api_keys(api_key, env_path=env_path)
        self.max_results = max_results
        self.search_depth = search_depth
        if self._explicit_key:
            self._current_key_index = 0
        else:
            self._current_key_index = (
                TavilySearchTool._shared_key_index % len(self.api_keys)
                if self.api_keys
                else 0
            )
        self._client = None
        self._client_key = None

        if self.api_key and TavilyClient is not None:
            try:
                self._client = TavilyClient(api_key=self.api_key)
                self._client_key = self.api_key
            except Exception:
                self._client = None
                self._client_key = None

    @property
    def api_key(self) -> Optional[str]:
        """Returns the currently active Tavily API key."""
        if self.api_keys and 0 <= self._current_key_index < len(self.api_keys):
            return self.api_keys[self._current_key_index]
        return None

    @api_key.setter
    def api_key(self, value: Optional[str]) -> None:
        """Sets or prepends the active Tavily API key."""
        if value:
            if value not in self.api_keys:
                self.api_keys.insert(0, value)
            self._current_key_index = self.api_keys.index(value)
        else:
            self.api_keys = []
            self._current_key_index = 0
        self._client = None
        self._client_key = None

    def search(self, query: str) -> WebSearchResult:
        """Executes a single search query against the Tavily Search API.

        Deterministic configuration:
        - provider_query = cleaned_query[:1500] (deterministic truncation for long queries)
        - search_depth: 'basic'
        - max_results: 5
        - include_answer: False (never use generated answer)
        - include_raw_content: False
        - include_images: False
        - auto_parameters: False
        """
        start_time = time.time()

        cleaned_query = query.strip() if query else ""
        original_query_length = len(cleaned_query)
        search_query_truncated = original_query_length > 1500
        provider_query = cleaned_query[:1500]
        provider_query_length = len(provider_query)

        if not cleaned_query:
            return WebSearchResult(
                query=query,
                provider_query="",
                search_query_truncated=False,
                original_query_length=0,
                provider_query_length=0,
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

        if not self.api_keys or not self.api_key:
            return WebSearchResult(
                query=cleaned_query,
                provider_query=provider_query,
                search_query_truncated=search_query_truncated,
                original_query_length=original_query_length,
                provider_query_length=provider_query_length,
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
                query=cleaned_query,
                provider_query=provider_query,
                search_query_truncated=search_query_truncated,
                original_query_length=original_query_length,
                provider_query_length=provider_query_length,
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

        num_keys = len(self.api_keys)
        last_exception: Optional[Exception] = None
        last_error_type: Optional[str] = None

        for attempt in range(num_keys):
            current_key = self.api_key
            if not current_key:
                break
            masked_key = (current_key[:8] + "..." + current_key[-4:]) if len(current_key) > 12 else "***"

            try:
                if self._client is None or getattr(self, "_client_key", None) != current_key:
                    self._client = TavilyClient(api_key=current_key)
                    self._client_key = current_key

                raw_response = self._client.search(
                    query=provider_query,
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

                if not self._explicit_key:
                    TavilySearchTool._shared_key_index = self._current_key_index

                return WebSearchResult(
                    query=cleaned_query,
                    provider_query=provider_query,
                    search_query_truncated=search_query_truncated,
                    original_query_length=original_query_length,
                    provider_query_length=provider_query_length,
                    results=parsed_items,
                    success=True,
                    latency_seconds=latency,
                    call_count=1,
                    provider="tavily",
                    search_depth=self.search_depth,
                    max_results=self.max_results,
                )

            except Exception as e:
                last_exception = e
                last_error_type = type(e).__name__

                if attempt < num_keys - 1:
                    next_index = (self._current_key_index + 1) % num_keys
                    logger.warning(
                        f"[TavilySearchTool] Search failed with key {masked_key} ({last_error_type}: {e}). "
                        f"Rotating to key {next_index + 1}/{num_keys}..."
                    )
                    self._current_key_index = next_index
                    if not self._explicit_key:
                        TavilySearchTool._shared_key_index = next_index
                    continue
                else:
                    break

        latency = round(time.time() - start_time, 2)
        error_msg = str(last_exception) if last_exception else "Unknown search error"
        if num_keys > 1:
            error_msg = f"All {num_keys} Tavily API keys failed. Last error ({last_error_type}): {error_msg}"

        return WebSearchResult(
            query=cleaned_query,
            provider_query=provider_query,
            search_query_truncated=search_query_truncated,
            original_query_length=original_query_length,
            provider_query_length=provider_query_length,
            results=[],
            success=False,
            latency_seconds=latency,
            call_count=1,
            provider="tavily",
            search_depth=self.search_depth,
            max_results=self.max_results,
            error_type=last_error_type or "SearchError",
            error_message=error_msg,
        )

