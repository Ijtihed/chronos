"""Tests for the turn log system — state diffs, narrative output, persistence."""

import json

import httpx
import pytest
import respx

from backend.persistence import (
    append_turn_log,
    build_narrative_output,
    compute_state_diff,
    get_turn_logs,
    init_db,
)
from backend.world_state import WorldState, apply_action, create_initial_state

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

FAKE_ACTION = json.dumps({
    "action_type": "negotiate",
    "target": "Lucius Gallus",
    "intent": "forge alliance",
    "era_description": "Corvinus approaches the centurion.",
    "is_travel": False,
    "destination": None,
    "is_inaction": False,
    "npc_impacts": [
        {"name": "Lucius Gallus", "sentiment": "positive", "relevant": True,
         "reason": "direct"},
    ],
})

FAKE_NPC_POV = "I observe the merchant with interest."
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


class TestComputeStateDiff:
    def test_detects_turn_change(self):
        before = create_initial_state().model_dump()
        after = create_initial_state().model_dump()
        after["turn"] = 3
        diff = compute_state_diff(before, after)
        assert diff["turn"] == {"from": 0, "to": 3}

    def test_detects_player_location_change(self):
        before = create_initial_state().model_dump()
        after = create_initial_state().model_dump()
        after["player"]["location"] = "ravenna"
        diff = compute_state_diff(before, after)
        assert diff["player_location"]["to"] == "ravenna"

    def test_detects_new_events(self):
        state = create_initial_state()
        before = state.model_dump()
        action = {
            "action_type": "speak", "target": "Gallus",
            "era_description": "Speaks.", "intent": "talk",
        }
        after_state = apply_action(state, action)
        diff = compute_state_diff(before, after_state.model_dump())
        assert len(diff.get("new_events", [])) == 1

    def test_detects_npc_disposition_change(self):
        state = create_initial_state()
        before = state.model_dump()
        action = {
            "action_type": "trade", "target": "Lucius Gallus",
            "era_description": "Trades.", "intent": "supply",
            "npc_impacts": [
                {"name": "Lucius Gallus", "sentiment": "positive", "reason": "grain"},
            ],
        }
        after_state = apply_action(state, action)
        diff = compute_state_diff(before, after_state.model_dump())
        npc_changes = diff.get("npc_changes", [])
        disp_change = [c for c in npc_changes if c.get("field") == "disposition"]
        assert len(disp_change) >= 1

    def test_detects_new_visited_locations(self):
        before = create_initial_state().model_dump()
        after = create_initial_state().model_dump()
        after["visited_locations"].append("ravenna")
        diff = compute_state_diff(before, after)
        assert "ravenna" in diff["new_visited_locations"]

    def test_empty_diff_for_identical_states(self):
        state = create_initial_state().model_dump()
        diff = compute_state_diff(state, state)
        assert diff == {}

    def test_detects_tension_change(self):
        before = create_initial_state().model_dump()
        after = create_initial_state().model_dump()
        after["locations"][0]["political_tension"] = "critical"
        diff = compute_state_diff(before, after)
        assert len(diff.get("location_changes", [])) == 1


class TestBuildNarrativeOutput:
    def test_includes_ambient(self):
        ambient = [{"npc_name": "Gallus", "activity": "drills his men"}]
        text = build_narrative_output(ambient, {}, [])
        assert "Gallus" in text
        assert "drills" in text

    def test_includes_player_action(self):
        parsed = {"era_description": "Corvinus speaks to the centurion."}
        text = build_narrative_output([], parsed, [])
        assert "Corvinus speaks" in text

    def test_includes_npc_responses(self):
        responses = [{"npc_name": "Paulus", "pov": "I pray for guidance."}]
        text = build_narrative_output([], {}, responses)
        assert "Paulus" in text
        assert "pray" in text

    def test_includes_travel(self):
        travel = {"from": "Ariminum", "to": "Ravenna", "turns_spent": 2}
        text = build_narrative_output([], {}, [], travel=travel)
        assert "Ravenna" in text

    def test_includes_death(self):
        death = {"cause": "Killed by raiders."}
        text = build_narrative_output([], {}, [], death=death)
        assert "DEATH" in text

    def test_includes_erasure(self):
        text = build_narrative_output([], {}, [], erasure="No one remembers.")
        assert "ERASURE" in text

    def test_empty_inputs_produce_empty_string(self):
        text = build_narrative_output([], {}, [])
        assert text == ""


class TestAppendTurnLog:
    @pytest.mark.asyncio
    async def test_appends_and_retrieves(self):
        await init_db()
        from backend.persistence import save_session
        state = create_initial_state()
        await save_session(state)

        await append_turn_log(
            run_id=state.run_id,
            turn_number=1,
            player_input="forge an alliance",
            parsed_action={"action_type": "negotiate"},
            ambient_activity=[{"npc_name": "Gallus", "activity": "drills"}],
            npc_responses=[{"npc_name": "Gallus", "pov": "I observe."}],
            state_changes={"turn": {"from": 0, "to": 1}},
            narrative_output="Gallus drills.\n> Corvinus negotiates.",
            player_view_snapshot={"turn": 1},
        )

        logs = await get_turn_logs(state.run_id)
        assert len(logs) == 1
        log = logs[0]
        assert log["run_id"] == state.run_id
        assert log["turn_number"] == 1
        assert log["player_input"] == "forge an alliance"
        assert log["parsed_action"]["action_type"] == "negotiate"
        assert len(log["ambient_activity"]) == 1
        assert len(log["npc_responses"]) == 1
        assert "turn" in log["state_changes"]
        assert "Gallus" in log["narrative_output"]

    @pytest.mark.asyncio
    async def test_multiple_turns_append(self):
        await init_db()
        from backend.persistence import save_session
        state = create_initial_state()
        await save_session(state)

        for t in range(1, 4):
            await append_turn_log(
                run_id=state.run_id, turn_number=t,
                player_input=f"action {t}", parsed_action={},
                ambient_activity=[], npc_responses=[],
                state_changes={}, narrative_output=f"Turn {t}.",
                player_view_snapshot={},
            )

        logs = await get_turn_logs(state.run_id)
        assert len(logs) == 3
        assert [l["turn_number"] for l in logs] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_logs_are_ordered(self):
        await init_db()
        from backend.persistence import save_session
        state = create_initial_state()
        await save_session(state)

        for t in [3, 1, 2]:
            await append_turn_log(
                run_id=state.run_id, turn_number=t,
                player_input="", parsed_action={},
                ambient_activity=[], npc_responses=[],
                state_changes={}, narrative_output="",
                player_view_snapshot={},
            )

        logs = await get_turn_logs(state.run_id)
        assert [l["turn_number"] for l in logs] == [1, 2, 3]


class TestTurnLogIntegration:
    """Turn logs are written during actual turn processing."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_turn_writes_log(self, client):
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)

        await client.post(
            f"/api/run/{rid}/turn",
            json={"player_input": "forge alliance with garrison"},
        )

        logs = await get_turn_logs(rid)
        assert len(logs) >= 1
        log = logs[-1]
        assert log["run_id"] == rid
        assert log["player_input"] == "forge alliance with garrison"
        assert log["state_changes"] != {}
        assert log["narrative_output"] != ""
        assert log["player_view_snapshot"] != {}

    @pytest.mark.asyncio
    @respx.mock
    async def test_log_does_not_contain_full_world_state(self, client):
        """Turn logs store diffs, not full WorldState clones."""
        _down()
        rid = (await client.post("/api/run")).json()["run_id"]

        respx.get(OLLAMA_TAGS_URL).mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        _chat(FAKE_SKIP, FAKE_SKIP, FAKE_ACTION, FAKE_DEATH_SAFE, FAKE_NPC_POV)

        await client.post(
            f"/api/run/{rid}/turn",
            json={"player_input": "act"},
        )

        logs = await get_turn_logs(rid)
        log = logs[-1]
        sc = log["state_changes"]
        assert "era" not in sc
        assert "player" not in sc
        assert "npcs" not in sc
        assert "locations" not in sc
