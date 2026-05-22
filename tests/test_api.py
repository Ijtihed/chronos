"""Integration tests for API endpoints. LLM calls mocked with respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


FAKE_PARSED_ACTION = json.dumps({
    "action_type": "negotiate",
    "target": "Lucius Gallus",
    "intent": "Forge alliance with the garrison",
    "era_description": "Corvinus approaches the centurion to propose a mutual defense pact.",
    "is_travel": False,
    "destination": None,
    "is_inaction": False,
    "npc_impacts": [
        {"name": "Lucius Gallus", "sentiment": "positive", "relevant": True, "reason": "direct benefit"},
    ],
})

FAKE_TRAVEL_ACTION = json.dumps({
    "action_type": "travel",
    "target": "Ravenna",
    "intent": "Travel to the imperial capital",
    "era_description": "Corvinus sets out on the road to Ravenna.",
    "is_travel": True,
    "destination": "ravenna",
    "is_inaction": False,
    "npc_impacts": [],
})

FAKE_INACTION = json.dumps({
    "action_type": "wait",
    "target": None,
    "intent": "Wait and see what happens",
    "era_description": "Corvinus waits, watching the harbor.",
    "is_travel": False,
    "destination": None,
    "is_inaction": True,
    "npc_impacts": [],
})

FAKE_SKIP = json.dumps({
    "action": "The character rests.",
    "effect": "Nothing changes.",
})

FAKE_NPC_POV = "I watch as the merchant approaches. His intentions are unclear."

FAKE_DEATH_SAFE = json.dumps({
    "death_risk": 0.1,
    "could_die": False,
    "cause": None,
})


def _mock_ollama_down():
    return respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))


def _mock_chat(*contents):
    return respx.post(OLLAMA_CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json={"message": {"role": "assistant", "content": c}})
            for c in contents
        ]
    )


# Post-Gemini-migration helper. The Ollama HTTP path is no longer in
# the runtime path; respx-mocking it is a no-op for the actual code.
# Tests that need a deterministic call_llm response must patch
# call_llm() at every import site.
def _patch_call_llm_returning(monkeypatch, raw_text: str):
    from backend.llm_provider import UsageInfo

    usage = UsageInfo(
        provider="noop", model="noop",
        input_tokens=0, output_tokens=0,
        cost_usd=0.0, duration_s=0.0,
    )

    async def _fake(prompt, **kw):
        return raw_text, usage

    import backend.llm_provider as _llm
    monkeypatch.setattr(_llm, "call_llm", _fake)
    for mod in (
        "backend.action_parser",
        "backend.npc_engine",
        "backend.world_engine",
        "backend.hce",
        "backend.death_engine",
        "backend.character_gen",
        "backend.scene_director",
        "backend.connection_proposal",
        "backend.inner_thought",
    ):
        try:
            monkeypatch.setattr(f"{mod}.call_llm", _fake)
        except AttributeError:
            pass


class TestHealth:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_ok(self, client):
        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestRunManagement:
    @pytest.mark.asyncio
    @respx.mock
    async def test_create_run(self, client):
        _mock_ollama_down()
        resp = await client.post("/api/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["player_view"]["run_status"] == "active"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_run(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]
        resp = await client.get(f"/api/run/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_run(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]
        await client.delete(f"/api/run/{run_id}")
        resp = await client.get(f"/api/run/{run_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_run_404(self, client):
        resp = await client.get("/api/run/nonexistent")
        assert resp.status_code == 404


class TestUnifiedTurn:
    @pytest.mark.asyncio
    @respx.mock
    async def test_regular_action(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_PARSED_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)

        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "forge an alliance with the garrison"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "parsed_action" in data
        assert "player_view" in data
        assert "npc_responses" in data

    @pytest.mark.asyncio
    async def test_travel_via_turn(self, client, monkeypatch):
        _patch_call_llm_returning(monkeypatch, FAKE_TRAVEL_ACTION)
        run_id = (await client.post(
            "/api/run", json={"era": "roman_late_empire"},
        )).json()["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state.player.location = "ariminum"
        if "ariminum" not in state.visited_locations:
            state.visited_locations.append("ariminum")
        await persistence.save_session(state)

        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "travel to Ravenna"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_view"]["player_location"] == "ravenna"
        assert "travel" in data
        assert data["travel"]["to"] == "Ravenna"

    @pytest.mark.asyncio
    @respx.mock
    async def test_inaction_via_turn(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_SKIP, FAKE_SKIP, FAKE_INACTION, FAKE_SKIP, FAKE_DEATH_SAFE)

        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "wait and see what happens"},
        )
        assert resp.status_code == 200
        assert resp.json()["player_view"]["turn"] >= 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_turn_increments(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_PARSED_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)

        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "do something"},
        )
        state = (await client.get(f"/api/run/{run_id}")).json()
        assert state["turn"] >= 1

    @pytest.mark.asyncio
    async def test_empty_input_rejected(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]
        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "   "},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @respx.mock
    async def test_ended_run_blocked(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state.run_status = "ended"
        await persistence.save_session(state)

        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "hello"},
        )
        assert resp.status_code == 403


class TestReset:
    @pytest.mark.asyncio
    @respx.mock
    async def test_reset_restores_state(self, client):
        _mock_ollama_down()
        run_id = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_PARSED_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)
        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "do something"},
        )

        await client.post(f"/api/run/{run_id}/reset")
        state = (await client.get(f"/api/run/{run_id}")).json()
        assert state["turn"] == 0
