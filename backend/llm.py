"""Shared Ollama client for all local LLM calls.

Model tier: LOCAL — all calls in Phase 0 route through Ollama.
The action parser is a frontier stub (see prompts/action_parser.md);
swap to a frontier API client here when that tier is enabled.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"


def load_prompt(path: Path) -> str:
    """Load a prompt template, stripping the metadata header above the first '---'."""
    text = path.read_text()
    parts = text.split("\n---\n", 1)
    return parts[1].strip() if len(parts) == 2 else text.strip()


async def chat(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    json_mode: bool = False,
) -> str:
    """Send a chat request to local Ollama and return the assistant message."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def ollama_ok() -> bool:
    """Quick check: is Ollama reachable?"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False
