"""Shared Ollama client for all local LLM calls.

Model selection: prefers llama3.1:70b if available locally (better quality
on capable hardware), falls back to llama3.1:8b. Checked once at startup.

This is consistent with MODEL TIER POLICY in roadmap.md: both 70b and 8b
are local Ollama models with zero API cost. The policy constraint is
"local only for everything except the action parser frontier swap point."
70b produces richer NPC voices and more historically grounded responses
when the hardware can run it; 8b is the minimum viable local model.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("chronos")

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
PREFERRED_MODEL = "llama3.1:70b"
_MODEL_OVERRIDE = os.environ.get("CHRONOS_MODEL")

_resolved_model: Optional[str] = None


async def _resolve_model() -> str:
    """Pick the best available model. Cached after first call.

    Set CHRONOS_MODEL env var to force a specific model (e.g. llama3.2:3b for demos).
    """
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    if _MODEL_OVERRIDE:
        _resolved_model = _MODEL_OVERRIDE
        logger.info("Using model (env override): %s", _MODEL_OVERRIDE)
        return _MODEL_OVERRIDE
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                if PREFERRED_MODEL in models:
                    _resolved_model = PREFERRED_MODEL
                    logger.info("Using model: %s", PREFERRED_MODEL)
                    return PREFERRED_MODEL
    except Exception:
        pass
    _resolved_model = DEFAULT_MODEL
    logger.info("Using model: %s", DEFAULT_MODEL)
    return DEFAULT_MODEL


def load_prompt(path: Path) -> str:
    """Load a prompt template, stripping the metadata header above the first '---'."""
    text = path.read_text()
    parts = text.split("\n---\n", 1)
    return parts[1].strip() if len(parts) == 2 else text.strip()


async def chat(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    json_mode: bool = False,
) -> str:
    """Send a chat request to local Ollama and return the assistant message."""
    if model is None:
        model = await _resolve_model()

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

    async with httpx.AsyncClient(timeout=300.0) as client:
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
