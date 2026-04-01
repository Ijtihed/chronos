"""Comprehensive Phase 1 tests — unified turn endpoint, design principles."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.world_state import (
    WorldState,
    apply_action,
    create_initial_state,
    get_location,
    get_player_location,
    npcs_at_location,
    npcs_near_player,
)
from backend.death_engine import apply_death, decay_memories
from backend.eras import ALL_ERAS, ERA_KEYS, random_era

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

FAKE_ACTION = json.dumps({
    "action_type": "negotiate",
    "target": "someone",
    "intent": "talk",
    "era_description": "The character speaks.",
    "is_travel": False,
    "destination": None,
    "is_inaction": False,
    "npc_impacts": [{"name": "Lucius Gallus", "sentiment": "positive", "relevant": True, "reason": "direct"}],
})

FAKE_TRAVEL = json.dumps({
    "action_type": "travel",
    "target": "Ravenna",
    "intent": "Go to Ravenna",
    "era_description": "Sets out for Ravenna.",
    "is_travel": True,
    "destination": "ravenna",
    "is_inaction": False,
    "npc_impacts": [],
})

FAKE_INACTION = json.dumps({
    "action_type": "wait",
    "target": None,
    "intent": "Wait",
    "era_description": "Waits.",
    "is_travel": False,
    "destination": None,
    "is_inaction": True,
    "npc_impacts": [],
})

FAKE_NPC_POV = "I observe with interest."
FAKE_SKIP = json.dumps({"action": "Rests.", "effect": "Nothing."})
FAKE_DEATH_SAFE = json.dumps({"death_risk": 0.1, "could_die": False, "cause": None})


def _down():
    return respx.get(OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("mock"))


def _chat(*c):
    return respx.post(OLLAMA_CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json={"message": {"role": "assistant", "content": x}})
            for x in c
        ]
    )


class TestEraConfigs:
    def test_five_eras(self):
        assert len(ALL_ERAS) == 5

    def test_each_has_locations(self):
        for key, era in ALL_ERAS.items():
            assert len(era["locations"]) >= 3, f"{key}"

    def test_each_has_archetypes(self):
        for key, era in ALL_ERAS.items():
            assert len(era["npc_archetypes"]) >= 8, f"{key}"


class TestLocationGraph:
    def test_multi_location(self):
        assert len(create_initial_state().locations) >= 3

    def test_neighbors_exist(self):
        state = create_initial_state()
        loc = get_player_location(state)
        assert len(loc.neighbors) >= 1

    def test_npcs_filter_by_location(self):
        state = create_initial_state()
        nearby = npcs_near_player(state)
        for npc in nearby:
            assert npc.location == state.player.location


class TestUnifiedTurnAction:
    @pytest.mark.asyncio
    @respx.mock
    async def test_action_works(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "forge alliance"})
        assert resp.status_code == 200
        assert resp.json()["world_state"]["turn"] >= 1


class TestUnifiedTurnTravel:
    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_changes_location(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_TRAVEL, FAKE_SKIP, FAKE_SKIP, FAKE_NPC_POV)
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "go to Ravenna"})
        assert resp.json()["world_state"]["player"]["location"] == "ravenna"

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_returns_info(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_TRAVEL, FAKE_SKIP, FAKE_SKIP, FAKE_NPC_POV)
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "travel to Ravenna"})
        assert "travel" in resp.json()


class TestUnifiedTurnInaction:
    @pytest.mark.asyncio
    @respx.mock
    async def test_inaction_increments_turn(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_INACTION, FAKE_SKIP, FAKE_DEATH_SAFE)
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "wait"})
        assert resp.json()["world_state"]["turn"] >= 1


class TestDeathAndAging:
    def test_age_increases(self):
        state = create_initial_state()
        for _ in range(20):
            state = apply_action(state, {"action_type": "observe", "era_description": "Waits."})
        assert state.current_year - state.player.birth_year > 35

    def test_death_transitions(self):
        state = create_initial_state()
        new = apply_death(state, "Died.")
        assert new.run_status == "dead_observing"

    @pytest.mark.asyncio
    @respx.mock
    async def test_dead_run_handles_input(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        from backend import persistence
        state = await persistence.load_session(rid)
        state = apply_death(state, "Died.")
        await persistence.save_session(state)

        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _chat(FAKE_TRAVEL, FAKE_SKIP, FAKE_SKIP)
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "travel to ravenna"})
        assert resp.status_code == 200


class TestMemoryDecay:
    def test_decay_reduces_memory(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.5
        new = decay_memories(state)
        for npc in new.npcs:
            assert npc.memory_of_player < 0.5

    def test_all_forgotten_ends_run(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.0
        new = decay_memories(state)
        assert new.run_status == "ended"

    def test_full_cycle_ends(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 1.0
        for _ in range(500):
            state = decay_memories(state)
            if state.run_status == "ended":
                break
        assert state.run_status == "ended"


class TestPersistence:
    @pytest.mark.asyncio
    @respx.mock
    async def test_state_persists(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        respx.get(OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)
        await client.post(f"/api/run/{rid}/turn", json={"player_input": "act"})
        state = (await client.get(f"/api/run/{rid}")).json()
        assert state["turn"] >= 1


class TestRunStatusEnforcement:
    @pytest.mark.asyncio
    @respx.mock
    async def test_ended_blocks_turn(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        from backend import persistence
        state = await persistence.load_session(rid)
        state.run_status = "ended"
        await persistence.save_session(state)
        resp = await client.post(f"/api/run/{rid}/turn", json={"player_input": "hello"})
        assert resp.status_code == 403
