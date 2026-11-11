"""SearXNG search client (JSON API)."""

from typing import Any

import httpx

import config


class SearchError(Exception):
    """Raised when the SearXNG query fails."""


async def search(query: str) -> list[dict[str, Any]]:
    """Return a list of results: [{"title", "url", "snippet"}]."""
    params = {
        "q": query,
        "format": "json",
        "language": "en",
        "safesearch": 1,
    }
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        try:
            resp = await client.get(f"{config.SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                raise SearchError(
                    "SearXNG returned 403. Enable the JSON API in settings.yml "
                    '(search: formats: [html, json]) and restart SearXNG.'
                ) from exc
            raise SearchError(f"SearXNG HTTP error: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SearchError(f"Could not reach SearXNG at {config.SEARXNG_URL}: {exc}") from exc

    data = resp.json()
    results = []
    for item in data.get("results", [])[: config.MAX_SEARCH_RESULTS]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            }
        )
    return results
