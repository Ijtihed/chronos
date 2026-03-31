"""Shared fixtures for CHRONOS Phase 0 tests."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

from backend.main import app
from backend.world_state import WorldState, create_initial_state


@pytest.fixture
def initial_state() -> WorldState:
    return create_initial_state()


@pytest.fixture
def sample_parsed_action() -> dict:
    """A representative parsed action for testing mutation and NPC generation."""
    return {
        "action_type": "speak",
        "target": "Lucius Gallus",
        "intent": "Ask the centurion about troop movements",
        "era_description": (
            "Corvinus approaches the centurion at the garrison gate "
            "and inquires about the disposition of the remaining cohorts."
        ),
    }


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async test client hitting the FastAPI app directly (no network)."""
    from backend import main

    main._state = create_initial_state()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    main._state = create_initial_state()


async def ollama_reachable() -> bool:
    """Check if Ollama is up — used to skip live tests."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            resp = await c.get("http://localhost:11434/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


_ollama_up = None


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: requires a running Ollama instance"
    )


def pytest_collection_modifyitems(config, items):
    global _ollama_up
    if _ollama_up is None:
        _ollama_up = asyncio.get_event_loop().run_until_complete(ollama_reachable())

    if not _ollama_up:
        skip = pytest.mark.skip(reason="Ollama not reachable")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip)
