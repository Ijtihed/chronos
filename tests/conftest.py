"""Shared fixtures for CHRONOS tests."""

from __future__ import annotations

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
        "npc_impacts": [
            {"name": "Lucius Gallus", "sentiment": "positive", "reason": "showing concern"},
            {"name": "Deacon Paulus", "sentiment": "neutral", "reason": "not involved"},
        ],
    }


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async test client hitting the FastAPI app directly (no network)."""
    from backend import main, persistence

    await persistence.init_db()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: requires a live Gemini API key"
    )
