"""Integration tests for API endpoints. LLM calls mocked with respx."""

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
        {"name": "Lucius Gallus", "sentiment": "positive", "reason": "showing concern"},
        {"name": "Deacon Paulus", "sentiment": "neutral", "reason": "not involved"},
    ],
})

FAKE_NPC_POV = (
    "The merchant comes again with his questions. I have told him "
    "what I can — the cohort holds, though I know not for how long. "
    "He smells of fear, as we all do now."
)


def _mock_chat_sequence(*contents):
    """Mock Ollama chat with a sequence of responses."""
    return respx.post(OLLAMA_CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json={"message": {"role": "assistant", "content": c}})
            for c in contents
        ]
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
        assert data["phase"] == 1


class TestRunManagement:
    @pytest.mark.asyncio
    @respx.mock
    async def test_create_run(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))
        resp = await client.post("/api/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert "world_state" in data
        assert data["world_state"]["run_status"] == "active"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_run_state(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]

        resp = await client.get(f"/api/run/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_runs(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))
        await client.post("/api/run")
        await client.post("/api/run")

        resp = await client.get("/api/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_run(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]

        resp = await client.delete(f"/api/run/{run_id}")
        assert resp.status_code == 200

        resp2 = await client.get(f"/api/run/{run_id}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_run_returns_404(self, client):
        resp = await client.get("/api/run/nonexistent")
        assert resp.status_code == 404


def _mock_ollama_down():
    """Mock Ollama as unreachable so run creation uses hardcoded state."""
    return respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))


class TestTurnEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path(self, client):
        _mock_ollama_down()
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _mock_chat_sequence(FAKE_PARSED_ACTION, FAKE_NPC_POV, FAKE_NPC_POV)

        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "talk to the centurion"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "parsed_action" in data
        assert "world_state" in data
        assert "npc_responses" in data

    @pytest.mark.asyncio
    @respx.mock
    async def test_turn_increments(self, client):
        _mock_ollama_down()
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _mock_chat_sequence(FAKE_PARSED_ACTION, FAKE_NPC_POV, FAKE_NPC_POV)
        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "look around"},
        )

        state = (await client.get(f"/api/run/{run_id}")).json()
        assert state["turn"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_state_persists_across_requests(self, client):
        _mock_ollama_down()
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _mock_chat_sequence(FAKE_PARSED_ACTION, FAKE_NPC_POV, FAKE_NPC_POV)
        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "speak"},
        )

        state = (await client.get(f"/api/run/{run_id}")).json()
        assert state["turn"] == 1
        assert len(state["events"]) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_input_rejected(self, client):
        _mock_ollama_down()
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]
        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "   "},
        )
        assert resp.status_code == 400


class TestResetEndpoint:
    @pytest.mark.asyncio
    @respx.mock
    async def test_reset_restores_state(self, client):
        _mock_ollama_down()
        create = (await client.post("/api/run")).json()
        run_id = create["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _mock_chat_sequence(FAKE_PARSED_ACTION, FAKE_NPC_POV, FAKE_NPC_POV)
        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "do something"},
        )

        resp = await client.post(f"/api/run/{run_id}/reset")
        assert resp.status_code == 200
        after = (await client.get(f"/api/run/{run_id}")).json()
        assert after["turn"] == 0
        assert after["events"] == []


class TestBackwardCompat:
    @pytest.mark.asyncio
    @respx.mock
    async def test_compat_state_endpoint(self, client):
        _mock_ollama_down()
        resp = await client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "era" in data
        assert "turn" in data

    @pytest.mark.asyncio
    @respx.mock
    async def test_compat_turn_endpoint(self, client):
        _mock_ollama_down()
        await client.get("/api/state")
        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _mock_chat_sequence(FAKE_PARSED_ACTION, FAKE_NPC_POV, FAKE_NPC_POV)
        resp = await client.post(
            "/api/turn",
            json={"player_input": "look around"},
        )
        assert resp.status_code == 200
        assert "parsed_action" in resp.json()
