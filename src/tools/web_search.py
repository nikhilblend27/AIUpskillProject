"""Web search tool (M3) — deliberately mocked, as the curriculum specifies.

The point of M3 is the function-calling loop, not a search vendor. The mock
returns deterministic, clearly-labelled results so tests stay offline.
Swap `web_search` for a real API (Tavily, Brave, SerpAPI...) later without
touching the agent — only this function changes.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus


def web_search(query: str, num_results: int = 3) -> dict[str, Any]:
    num_results = max(1, min(int(num_results), 10))
    results = [
        {
            "title": f"[mock result {i + 1}] {query}",
            "url": f"https://example.com/search?q={quote_plus(query)}&r={i + 1}",
            "snippet": f"Mock search result {i + 1} for '{query}'. No live data.",
        }
        for i in range(num_results)
    ]
    return {"success": True, "mock": True, "query": query, "results": results}


WEB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for context about a claim or term. (Mock results.)",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results (1-10)",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
}
