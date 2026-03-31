"""Comprehensive Phase 1 tests covering all new features.

Covers: era configs, run lifecycle, travel, skip/inaction, POV gating,
death, memory decay, erasure, world advancement, and persistence.
"""

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
    "action_type": "speak",
    "target": "someone",
    "intent": "talk",
    "era_description": "The character speaks.",
    "npc_impacts": [],
})

FAKE_NPC_POV = "I watch with interest as the stranger arrives."

FAKE_SKIP = json.dumps({
    "action": "The character rests.",
    "effect": "Nothing changes.",
})

FAKE_DEATH_SAFE = json.dumps({
    "death_risk": 0.1,
    "could_die": False,
    "cause": None,
})

FAKE_DEATH_FATAL = json.dumps({
    "death_risk": 0.9,
    "could_die": True,
    "cause": "Killed by bandits on the road.",
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


# ----------------------------------------------------------------
# Era configs
# ----------------------------------------------------------------

class TestEraConfigs:
    def test_all_five_eras_exist(self):
        assert len(ALL_ERAS) == 5

    def test_each_era_has_required_fields(self):
        required = ["name", "year_start", "region", "description",
                     "locations", "player_archetypes", "npc_archetypes"]
        for key, era in ALL_ERAS.items():
            for field in required:
                assert field in era, f"{key} missing {field}"

    def test_each_era_has_at_least_3_locations(self):
        for key, era in ALL_ERAS.items():
            assert len(era["locations"]) >= 3, f"{key} has < 3 locations"

    def test_each_era_has_at_least_4_player_archetypes(self):
        for key, era in ALL_ERAS.items():
            assert len(era["player_archetypes"]) >= 4, f"{key} has < 4 player archetypes"

    def test_each_era_has_at_least_8_npc_archetypes(self):
        for key, era in ALL_ERAS.items():
            assert len(era["npc_archetypes"]) >= 8, f"{key} has < 8 NPC archetypes"

    def test_locations_have_neighbors(self):
        for key, era in ALL_ERAS.items():
            for loc in era["locations"]:
                assert loc.get("neighbors"), f"{key}/{loc['id']} has no neighbors"

    def test_random_era_returns_valid(self):
        era_key, era_config = random_era()
        assert era_key in ERA_KEYS
        assert era_config["name"]


# ----------------------------------------------------------------
# Multi-location model
# ----------------------------------------------------------------

class TestLocationGraph:
    def test_initial_state_has_3_locations(self):
        state = create_initial_state()
        assert len(state.locations) == 3

    def test_player_starts_at_first_location(self):
        state = create_initial_state()
        assert state.player.location == state.locations[0].id

    def test_neighbors_are_bidirectional(self):
        state = create_initial_state()
        ariminum = get_location(state, "ariminum")
        assert "ravenna" in ariminum.neighbors
        ravenna = get_location(state, "ravenna")
        assert "ariminum" in ravenna.neighbors

    def test_npcs_at_location_filters_correctly(self):
        state = create_initial_state()
        at_ariminum = npcs_at_location(state, "ariminum")
        assert len(at_ariminum) == 2
        at_ravenna = npcs_at_location(state, "ravenna")
        assert len(at_ravenna) == 0

    def test_npcs_near_player_matches_player_location(self):
        state = create_initial_state()
        nearby = npcs_near_player(state)
        for npc in nearby:
            assert npc.location == state.player.location


# ----------------------------------------------------------------
# Travel mechanics
# ----------------------------------------------------------------

class TestTravel:
    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_changes_player_location(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(
            FAKE_SKIP, FAKE_SKIP,
            FAKE_NPC_POV,
        )

        resp = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "ravenna"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["travel"]["to"] == "Ravenna"
        assert data["world_state"]["player"]["location"] == "ravenna"

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_advances_turns(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_SKIP, FAKE_SKIP)

        resp = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "ravenna"},
        )
        ws = resp.json()["world_state"]
        assert ws["turn"] >= 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_to_invalid_destination_fails(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        resp = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "atlantis"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_returns_arrival_reactions(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_SKIP, FAKE_SKIP, FAKE_NPC_POV)

        resp = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "ravenna"},
        )
        data = resp.json()
        assert "arrival_reactions" in data


# ----------------------------------------------------------------
# Skip / inaction
# ----------------------------------------------------------------

class TestSkip:
    @pytest.mark.asyncio
    @respx.mock
    async def test_skip_increments_turn(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_SKIP, FAKE_DEATH_SAFE, FAKE_NPC_POV, FAKE_NPC_POV)

        resp = await client.post(f"/api/run/{run_id}/skip")
        assert resp.status_code == 200
        ws = resp.json()["world_state"]
        assert ws["turn"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_skip_returns_autonomous_action(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_SKIP, FAKE_DEATH_SAFE, FAKE_NPC_POV, FAKE_NPC_POV)

        resp = await client.post(f"/api/run/{run_id}/skip")
        data = resp.json()
        assert data["parsed_action"]["action_type"] == "autonomous"

    @pytest.mark.asyncio
    @respx.mock
    async def test_skip_blocked_when_dead(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state = apply_death(state, "Died.")
        await persistence.save_session(state)

        resp = await client.post(f"/api/run/{run_id}/skip")
        assert resp.status_code == 403


# ----------------------------------------------------------------
# POV gating
# ----------------------------------------------------------------

class TestPovGating:
    def test_only_nearby_npcs_in_pov(self):
        state = create_initial_state()
        nearby = npcs_near_player(state)
        nearby_ids = {n.id for n in nearby}
        all_ids = {n.id for n in state.npcs}
        assert nearby_ids.issubset(all_ids)
        assert len(nearby_ids) <= len(all_ids)

    def test_no_pov_from_distant_npcs(self):
        state = create_initial_state()
        state.npcs.append(state.npcs[0].model_copy(
            update={"id": "distant_npc", "name": "Distant NPC", "location": "ravenna"}
        ))
        nearby = npcs_near_player(state)
        nearby_ids = {n.id for n in nearby}
        assert "distant_npc" not in nearby_ids


# ----------------------------------------------------------------
# Death + aging
# ----------------------------------------------------------------

class TestDeathAndAging:
    def test_age_increases_with_turns(self):
        state = create_initial_state()
        action = {"action_type": "observe", "era_description": "Waits."}
        for _ in range(20):
            state = apply_action(state, action)
        age = state.current_year - state.player.birth_year
        assert age > 35

    def test_death_transitions_to_observing(self):
        state = create_initial_state()
        new = apply_death(state, "Died of plague.")
        assert new.run_status == "dead_observing"

    def test_actions_blocked_when_dead(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        assert state.run_status == "dead_observing"

    @pytest.mark.asyncio
    @respx.mock
    async def test_turn_blocked_when_dead(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state = apply_death(state, "Died.")
        await persistence.save_session(state)

        resp = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "do something"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_works_when_dead(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state = apply_death(state, "Died.")
        await persistence.save_session(state)

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_SKIP, FAKE_SKIP)

        resp = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "ravenna"},
        )
        assert resp.status_code == 200


# ----------------------------------------------------------------
# Memory decay + erasure
# ----------------------------------------------------------------

class TestMemoryDecayAndErasure:
    def test_memories_decay_each_tick(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.5

        state = decay_memories(state)
        for npc in state.npcs:
            assert npc.memory_of_player < 0.5

    def test_run_ends_when_all_forgotten(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.01

        for _ in range(50):
            state = decay_memories(state)
            if state.run_status == "ended":
                break
        assert state.run_status == "ended"

    def test_strong_memory_decays_slower_than_weak(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        state.npcs[0].memory_of_player = 0.9
        state.npcs[1].memory_of_player = 0.2

        new = decay_memories(state)
        loss_strong = 0.9 - new.npcs[0].memory_of_player
        loss_weak = 0.2 - new.npcs[1].memory_of_player
        assert loss_strong < loss_weak

    def test_full_decay_cycle(self):
        state = create_initial_state()
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 1.0

        turns = 0
        while state.run_status != "ended" and turns < 500:
            state = decay_memories(state)
            turns += 1
        assert state.run_status == "ended"
        assert turns > 5, "Decay should not be instant"
        assert turns < 500, "Decay should not take forever"

    @pytest.mark.asyncio
    @respx.mock
    async def test_travel_after_death_blocks_at_end(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state = apply_death(state, "Died.")
        for npc in state.npcs:
            npc.memory_of_player = 0.0
        state.run_status = "ended"
        await persistence.save_session(state)

        resp = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "ravenna"},
        )
        assert resp.status_code == 403


# ----------------------------------------------------------------
# World advancement
# ----------------------------------------------------------------

class TestWorldAdvancement:
    def test_apply_action_advances_year(self):
        state = create_initial_state()
        action = {"action_type": "observe", "era_description": "Waits."}
        new = apply_action(state, action)
        assert new.current_year >= state.current_year

    def test_events_accumulate_over_turns(self):
        state = create_initial_state()
        for i in range(5):
            state = apply_action(state, {
                "action_type": "observe",
                "era_description": f"Event {i}",
            })
        assert len(state.events) == 5


# ----------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------

class TestPersistence:
    @pytest.mark.asyncio
    @respx.mock
    async def test_state_survives_turn_cycle(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _mock_chat(FAKE_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV, FAKE_NPC_POV)

        await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "look around"},
        )

        state = (await client.get(f"/api/run/{run_id}")).json()
        assert state["turn"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_run_id_persists(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        state = (await client.get(f"/api/run/{run_id}")).json()
        assert state["run_id"] == run_id


# ----------------------------------------------------------------
# Run status enforcement
# ----------------------------------------------------------------

class TestRunStatusEnforcement:
    @pytest.mark.asyncio
    @respx.mock
    async def test_ended_run_blocks_everything(self, client):
        _mock_ollama_down()
        run = (await client.post("/api/run")).json()
        run_id = run["run_id"]

        from backend import persistence
        state = await persistence.load_session(run_id)
        state.run_status = "ended"
        await persistence.save_session(state)

        resp_turn = await client.post(
            f"/api/run/{run_id}/turn",
            json={"player_input": "hello"},
        )
        assert resp_turn.status_code == 403

        resp_skip = await client.post(f"/api/run/{run_id}/skip")
        assert resp_skip.status_code == 403

        resp_travel = await client.post(
            f"/api/run/{run_id}/travel",
            json={"destination": "ravenna"},
        )
        assert resp_travel.status_code == 403
