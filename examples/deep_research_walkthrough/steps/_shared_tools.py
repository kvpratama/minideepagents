"""Tools shared across walkthrough steps."""

import httpx
from langchain_core.tools import InjectedToolArg, tool
from markdownify import markdownify
from tavily import TavilyClient
from typing_extensions import Annotated, Literal

from config import get_settings

_tavily_client: TavilyClient | None = None


def _client() -> TavilyClient:
    """Return a lazily-built Tavily client using the configured API key."""
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(
            api_key=get_settings().tavily_api_key.get_secret_value()
        )
    return _tavily_client


def fetch_webpage_content(url: str, timeout: float = 10.0) -> str:
    """Fetch a webpage and return its content as markdown.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Webpage content converted to markdown, or an error string.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return markdownify(response.text)
    except Exception as e:  # noqa: BLE001  # surface any fetch error to the agent
        return f"Error fetching content from {url}: {e!s}"


@tool(parse_docstring=True)
def tavily_search(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 1,
    topic: Annotated[
        Literal["general", "news", "finance"], InjectedToolArg
    ] = "general",
) -> str:
    """Search the web for information on a given query.

    Uses Tavily to discover URLs, then fetches each page and converts it to
    markdown so the model sees full content (not Tavily's summary).

    Args:
        query: Search query to execute.
        max_results: Maximum number of results to return.
        topic: Topic filter - 'general', 'news', or 'finance'.

    Returns:
        Formatted search results with full webpage content.
    """
    search_results = _client().search(
        query, max_results=max_results, topic=topic
    )
    chunks = []
    for result in search_results.get("results", []):
        url = result["url"]
        title = result["title"]
        content = fetch_webpage_content(url)
        chunks.append(f"## {title}\n**URL:** {url}\n\n{content}\n\n---\n")
    return f"🔍 Found {len(chunks)} result(s) for '{query}':\n\n" + "\n".join(
        chunks
    )


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Record a strategic reflection on research progress.

    Use this between searches to pause, assess findings, identify gaps, and
    decide whether to keep searching or answer.

    Args:
        reflection: Detailed reflection on findings, gaps, and next steps.

    Returns:
        Confirmation that the reflection was recorded.
    """
    return f"Reflection recorded: {reflection}"
