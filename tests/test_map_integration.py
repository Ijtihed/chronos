"""Phase 2d integration tests — marker state sync, travel updates, lifecycle states.

These test the backend state that the map depends on. The map itself
renders in the browser, but these verify the data it receives is correct
at every lifecycle stage.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.death_engine import apply_death, decay_memories
from backend.world_state import (
    apply_action,
    create_initial_state,
    get_player_location,
    npcs_near_player,
)

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
    "npc_impacts": [
        {"name": "Lucius Gallus", "sentiment": "positive", "relevant": True, "reason": "direct"},
    ],
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


class TestMarkerStateMidRun:
    """Toggle map mid-run: markers must reflect current state."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_state_has_visited_locations_after_action(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)

        await client.post(f"/api/run/{rid}/turn", json={"player_input": "act"})
        state = (await client.get(f"/api/run/{rid}")).json()

        assert "visited_locations" in state
        assert len(state["visited_locations"]) >= 1
        assert state["player"]["location"] in state["visited_locations"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_locations_have_coords_in_state(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        state = (await client.get(f"/api/run/{rid}")).json()

        for loc in state["locations"]:
            assert "lat" in loc, f"{loc['id']} missing lat"
            assert "lon" in loc, f"{loc['id']} missing lon"

    @pytest.mark.asyncio
    @respx.mock
    async def test_npcs_have_memory_field_for_marker_state(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]
        state = (await client.get(f"/api/run/{rid}")).json()

        for npc in state["npcs"]:
            assert "memory_of_player" in npc
            assert "location" in npc


class TestTravelUpdatesMarkers:
    """Travel: camera should pan, markers should update, visited set grows."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_adds_destination_to_visited(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_TRAVEL, FAKE_SKIP, FAKE_SKIP, FAKE_NPC_POV)

        await client.post(
            f"/api/run/{rid}/turn",
            json={"player_input": "travel to Ravenna"},
        )
        state = (await client.get(f"/api/run/{rid}")).json()

        assert "ravenna" in state["visited_locations"]
        assert state["player"]["location"] == "ravenna"

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_preserves_previous_visited(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        state_before = (await client.get(f"/api/run/{rid}")).json()
        original_visited = state_before["visited_locations"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_TRAVEL, FAKE_SKIP, FAKE_SKIP, FAKE_NPC_POV)

        await client.post(
            f"/api/run/{rid}/turn",
            json={"player_input": "go to Ravenna"},
        )
        state_after = (await client.get(f"/api/run/{rid}")).json()

        for loc_id in original_visited:
            assert loc_id in state_after["visited_locations"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_player_location_matches_after_travel(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_TRAVEL, FAKE_SKIP, FAKE_SKIP, FAKE_NPC_POV)

        resp = await client.post(
            f"/api/run/{rid}/turn",
            json={"player_input": "travel to Ravenna"},
        )
        turn_state = resp.json()["world_state"]
        api_state = (await client.get(f"/api/run/{rid}")).json()

        assert turn_state["player"]["location"] == api_state["player"]["location"]


class TestObservationModeMarkers:
    """Observation mode: player marker fades, NPC markers reflect memory."""

    def test_dead_state_has_player_marker_data(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        loc = get_player_location(state)
        assert loc.lat != 0
        assert state.run_status == "dead_observing"

    def test_npc_memory_available_for_marker_opacity(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.5
        state = decay_memories(state)
        for npc in state.npcs:
            assert 0.0 <= npc.memory_of_player <= 1.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_dead_run_state_has_correct_status(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        from backend import persistence
        state = await persistence.load_session(rid)
        state = apply_death(state, "Died.")
        await persistence.save_session(state)

        api_state = (await client.get(f"/api/run/{rid}")).json()
        assert api_state["run_status"] == "dead_observing"


class TestErasureMarkersGone:
    """Erasure: all markers should be gone (run_status = ended)."""

    def test_ended_run_has_zero_memory_npcs(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.0
        state = decay_memories(state)
        assert state.run_status == "ended"
        for npc in state.npcs:
            assert npc.memory_of_player == 0.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_ended_run_state_via_api(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        from backend import persistence
        state = await persistence.load_session(rid)
        state.run_status = "ended"
        for npc in state.npcs:
            npc.memory_of_player = 0.0
        await persistence.save_session(state)

        api_state = (await client.get(f"/api/run/{rid}")).json()
        assert api_state["run_status"] == "ended"
        for npc in api_state["npcs"]:
            assert npc["memory_of_player"] == 0.0
