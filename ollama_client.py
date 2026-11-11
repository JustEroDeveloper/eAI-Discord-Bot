"""Ollama chat client."""

from typing import AsyncIterator

import httpx

import config


class OllamaError(Exception):
    """Raised when the Ollama request fails."""


SYSTEM_PROMPT = (
    "You are a helpful Discord bot. Answer the user's question using the web search "
    "results provided when they are relevant. Be concise (under 1800 characters), "
    "accurate, and friendly. Cite sources by mentioning [1], [2], etc. when you use "
    "them. If the search results don't help, answer from your own knowledge and say so."
)


async def chat_stream(question: str, search_results: list[dict]) -> AsyncIterator[str]:
    """Yield answer chunks from Ollama's streaming chat API."""
    context = "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['url']}\n{r['snippet']}"
        for i, r in enumerate(search_results)
    )
    payload = {
        "model": config.OLLAMA_MODEL,
        "stream": True,
        "options": {"temperature": config.TEMPERATURE},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Web search results:\n{context}\n\nQuestion: {question}",
            },
        ],
    }

    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        try:
            async with client.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise OllamaError(f"Ollama HTTP {resp.status_code}: {body.decode(errors='replace')[:300]}")
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    # Each line is a JSON object; the last has "done": true
                    import json

                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise OllamaError(f"Could not reach Ollama at {config.OLLAMA_URL}: {exc}") from exc
