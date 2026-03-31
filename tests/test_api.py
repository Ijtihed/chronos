"""Integration tests for API endpoints.

LLM calls are mocked with respx so these run without Ollama.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


def _mock_ollama_tags():
    return respx.get(OLLAMA_TAGS_URL).mock(
        return_value=httpx.Response(200, json={"models": []})
    )


FAKE_PARSED_ACTION = json.dumps({
    "action_type": "speak",
    "target": "Lucius Gallus",
    "intent": "Ask about troop readiness",
    "era_description": (
        "Corvinus approaches the centurion at the garrison gate "
        "to inquire about the state of the cohort."
    ),
    "npc_impacts": [
        {"name": "Lucius Gallus", "sentiment": "positive", "reason": "showing concern for the garrison"},
        {"name": "Deacon Paulus", "sentiment": "neutral", "reason": "not directly involved"},
    ],
})

FAKE_NPC_POV = (
    "The merchant comes again with his questions. I have told him "
    "what I can — the cohort holds, though I know not for how long. "
    "He smells of fear, as we all do now."
)


class TestHealthEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_ok(self, client):
        _mock_ollama_tags()
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["phase"] == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_reports_ollama_status(self, client):
        _mock_ollama_tags()
        resp = await client.get("/api/health")
        assert "ollama" in resp.json()


class TestStateEndpoint:
    @pytest.mark.asyncio
    async def test_returns_initial_state(self, client):
        resp = await client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["era"]["name"] == "Roman Late Empire"
        assert data["turn"] == 0
        assert len(data["npcs"]) >= 1

    @pytest.mark.asyncio
    async def test_state_has_required_fields(self, client):
        data = (await client.get("/api/state")).json()
        for field in ("era", "player", "npcs", "location", "events", "turn"):
            assert field in data, f"Missing field: {field}"


class TestTurnEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path(self, client):
        respx.post(OLLAMA_CHAT_URL).mock(
            side_effect=[
                httpx.Response(200, json={"message": {"role": "assistant", "content": FAKE_PARSED_ACTION}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": FAKE_NPC_POV}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": FAKE_NPC_POV}}),
            ]
        )

        resp = await client.post(
            "/api/turn",
            json={"player_input": "talk to the centurion about the troops"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "parsed_action" in data
        assert "world_state" in data
        assert "npc_responses" in data

    @pytest.mark.asyncio
    @respx.mock
    async def test_turn_increments(self, client):
        respx.post(OLLAMA_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": FAKE_PARSED_ACTION}},
            )
        )

        await client.post("/api/turn", json={"player_input": "look around"})
        resp = await client.get("/api/state")
        assert resp.json()["turn"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_world_state_changes_after_turn(self, client):
        respx.post(OLLAMA_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": FAKE_PARSED_ACTION}},
            )
        )

        before = (await client.get("/api/state")).json()
        await client.post("/api/turn", json={"player_input": "speak to Gallus"})
        after = (await client.get("/api/state")).json()

        assert after["turn"] > before["turn"]
        assert len(after["events"]) > len(before["events"])

    @pytest.mark.asyncio
    @respx.mock
    async def test_npc_responses_present(self, client):
        respx.post(OLLAMA_CHAT_URL).mock(
            side_effect=[
                httpx.Response(200, json={"message": {"role": "assistant", "content": FAKE_PARSED_ACTION}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": FAKE_NPC_POV}}),
                httpx.Response(200, json={"message": {"role": "assistant", "content": FAKE_NPC_POV}}),
            ]
        )

        resp = await client.post(
            "/api/turn", json={"player_input": "talk to centurion"}
        )
        data = resp.json()
        assert len(data["npc_responses"]) >= 1
        for r in data["npc_responses"]:
            assert "npc_name" in r
            assert "pov" in r
            assert len(r["pov"]) > 0

    @pytest.mark.asyncio
    async def test_empty_input_rejected(self, client):
        resp = await client.post("/api/turn", json={"player_input": "   "})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @respx.mock
    async def test_parsed_action_has_required_fields(self, client):
        respx.post(OLLAMA_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": FAKE_PARSED_ACTION}},
            )
        )

        resp = await client.post(
            "/api/turn", json={"player_input": "observe the town"}
        )
        pa = resp.json()["parsed_action"]
        for field in ("action_type", "target", "intent", "era_description"):
            assert field in pa, f"Parsed action missing: {field}"


class TestResetEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_reset_restores_initial_state(self, client):
        respx.post(OLLAMA_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": FAKE_PARSED_ACTION}},
            )
        )

        await client.post("/api/turn", json={"player_input": "do something"})
        mid = (await client.get("/api/state")).json()
        assert mid["turn"] > 0

        resp = await client.post("/api/reset")
        assert resp.status_code == 200
        after = (await client.get("/api/state")).json()
        assert after["turn"] == 0
        assert after["events"] == []
