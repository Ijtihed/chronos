"""Tests for /api/run/{run_id}/interaction_graph.

Pure read endpoint: no LLM calls, no schema mutation. Tests construct
realistic state directly via persistence and assert the response shape
and derived fields (sentiment, memory_label, node-selection rule).
"""

from __future__ import annotations

import pytest

from backend import persistence
from backend.world_state import Event, create_initial_state


@pytest.mark.asyncio
async def test_empty_run_has_zero_nodes(client):
    """A fresh run with no interactions yields nodes=[], player set."""
    run_id = (await client.post("/api/run")).json()["run_id"]
    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    assert resp.status_code == 200

    data = resp.json()
    assert data["run_id"] == run_id
    assert data["nodes"] == []
    assert data["player"]["name"]
    assert data["player"]["archetype"]
    assert data["player"]["role"]
    assert data["turn"] == 0
    assert data["year"] >= 1  # era year_start


@pytest.mark.asyncio
async def test_missing_run_returns_404(client):
    resp = await client.get("/api/run/nonexistent_run/interaction_graph")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_single_interaction_via_player_interactions(client):
    """One NPC with a single recorded speak interaction → one node, positive sentiment."""
    state = create_initial_state()
    run_id = state.run_id
    npc = state.npcs[0]
    npc.player_interactions = [{
        "turn": 1,
        "year": state.era.year_start,
        "action_type": "speak",
        "intent": "Ask about the garrison",
    }]
    npc.memory_of_player = 0.4
    npc.last_interaction_turn = 1
    state.turn = 1
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["nodes"]) == 1
    node = data["nodes"][0]
    assert node["id"] == npc.id
    assert node["name"] == npc.name
    assert node["interaction_count"] == 1
    assert node["last_interaction_turn"] == 1
    assert node["memory_of_player"] == pytest.approx(0.4)
    assert node["memory_label"] == "faint"
    assert len(node["interactions"]) == 1
    interaction = node["interactions"][0]
    assert interaction["action_type"] == "speak"
    assert interaction["sentiment"] == "positive"
    assert interaction["intent"] == "Ask about the garrison"


@pytest.mark.asyncio
async def test_multiple_npcs_with_multi_turn_histories(client):
    """Two NPCs, each with multiple interactions across turns."""
    state = create_initial_state()
    run_id = state.run_id
    npc_a, npc_b = state.npcs[0], state.npcs[1]

    npc_a.player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "Greet."},
        {"turn": 2, "year": 410, "action_type": "trade", "intent": "Sell grain."},
        {"turn": 4, "year": 411, "action_type": "petition", "intent": "Ask for protection."},
    ]
    npc_a.memory_of_player = 0.85
    npc_a.last_interaction_turn = 4

    npc_b.player_interactions = [
        {"turn": 3, "year": 410, "action_type": "speak", "intent": "Discuss faith."},
    ]
    npc_b.memory_of_player = 0.2
    npc_b.last_interaction_turn = 3

    state.turn = 4
    state.current_year = 411
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()

    assert len(data["nodes"]) == 2
    by_id = {n["id"]: n for n in data["nodes"]}

    a = by_id[npc_a.id]
    assert a["interaction_count"] == 3
    assert a["memory_label"] == "vivid"
    assert [i["action_type"] for i in a["interactions"]] == ["speak", "trade", "petition"]
    assert all(i["sentiment"] == "positive" for i in a["interactions"])

    b = by_id[npc_b.id]
    assert b["interaction_count"] == 1
    assert b["memory_label"] == "barely remember"
    assert b["interactions"][0]["sentiment"] == "positive"


@pytest.mark.asyncio
async def test_hostile_actions_reflect_in_sentiment(client):
    """Attack/threaten/betray/steal/fight/siege all produce negative sentiment."""
    state = create_initial_state()
    run_id = state.run_id
    npc = state.npcs[0]
    hostile_types = ["attack", "threaten", "betray", "steal", "fight", "siege"]
    npc.player_interactions = [
        {"turn": i + 1, "year": 410, "action_type": at, "intent": f"do {at}"}
        for i, at in enumerate(hostile_types)
    ][-5:]  # cap at 5 to mirror the production cap
    npc.memory_of_player = 0.95
    state.turn = 6
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()

    assert len(data["nodes"]) == 1
    node = data["nodes"][0]
    assert node["interaction_count"] == 5
    assert node["memory_label"] == "vivid"
    assert all(i["sentiment"] == "negative" for i in node["interactions"])
    assert node["interactions"][-1]["sentiment"] == "negative"


@pytest.mark.asyncio
async def test_neutral_action_types(client):
    """flee, hoard, other → neutral sentiment."""
    state = create_initial_state()
    run_id = state.run_id
    npc = state.npcs[0]
    npc.player_interactions = [
        {"turn": 1, "year": 410, "action_type": "flee", "intent": "run away"},
        {"turn": 2, "year": 410, "action_type": "hoard", "intent": "stockpile"},
        {"turn": 3, "year": 410, "action_type": "other", "intent": "something else"},
    ]
    npc.memory_of_player = 0.5
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()

    node = data["nodes"][0]
    assert all(i["sentiment"] == "neutral" for i in node["interactions"])


@pytest.mark.asyncio
async def test_disposition_surfaces_correctly(client):
    """Disposition is passed through verbatim as-is from npc.disposition."""
    state = create_initial_state()
    run_id = state.run_id
    state.npcs[0].player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "x"},
    ]
    state.npcs[0].disposition = "warming"
    state.npcs[1].player_interactions = [
        {"turn": 1, "year": 410, "action_type": "attack", "intent": "y"},
    ]
    state.npcs[1].disposition = "hostile"
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()
    by_id = {n["id"]: n for n in data["nodes"]}
    assert by_id[state.npcs[0].id]["disposition"] == "warming"
    assert by_id[state.npcs[1].id]["disposition"] == "hostile"


@pytest.mark.asyncio
async def test_node_selection_via_event_target_only(client):
    """An NPC with no player_interactions but matched by an Event.target
    is still surfaced (defensive OR-leg of the selection rule)."""
    state = create_initial_state()
    run_id = state.run_id
    npc = state.npcs[0]
    # Deliberately leave player_interactions empty.
    assert npc.player_interactions == []
    npc.memory_of_player = 0.0
    # Substring of npc.name lower-cased — mirrors _apply_target_fallback.
    state.events.append(Event(
        turn=1,
        action_type="speak",
        description=f"The merchant approaches {npc.name}.",
        target=npc.name.split()[0].lower(),
        location=state.player.location,
    ))
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()

    ids = [n["id"] for n in data["nodes"]]
    assert npc.id in ids
    matched = next(n for n in data["nodes"] if n["id"] == npc.id)
    # No player_interactions records → empty interactions list, count 0.
    assert matched["interactions"] == []
    assert matched["interaction_count"] == 0


@pytest.mark.asyncio
async def test_unrelated_npcs_excluded(client):
    """NPCs with no player_interactions and no event-target match are excluded."""
    state = create_initial_state()
    run_id = state.run_id
    # Exactly two NPCs in the initial state. Touch only the first.
    state.npcs[0].player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "x"},
    ]
    # The second NPC has zero interactions and no events target it.
    assert state.npcs[1].player_interactions == []
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()

    ids = [n["id"] for n in data["nodes"]]
    assert state.npcs[0].id in ids
    assert state.npcs[1].id not in ids


@pytest.mark.asyncio
async def test_response_shape_contract(client):
    """Top-level shape and player block stay stable for the frontend."""
    state = create_initial_state()
    run_id = state.run_id
    state.npcs[0].player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "hi"},
    ]
    await persistence.save_session(state)

    resp = await client.get(f"/api/run/{run_id}/interaction_graph")
    data = resp.json()

    assert set(data.keys()) == {"run_id", "year", "turn", "player", "nodes", "npc_links"}
    assert set(data["player"].keys()) == {"id", "name", "archetype", "role"}
    node_keys = {
        "id", "name", "archetype", "role", "memory_of_player",
        "memory_label", "disposition", "last_interaction_turn",
        "interactions", "interaction_count",
    }
    for node in data["nodes"]:
        assert set(node.keys()) == node_keys
    if data["nodes"] and data["nodes"][0]["interactions"]:
        i = data["nodes"][0]["interactions"][0]
        assert set(i.keys()) == {
            "turn", "year", "action_type", "intent", "sentiment",
        }


# ---------------------------------------------------------------------
# Witnessed NPC<->NPC link tests
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_npc_links_empty_when_no_shared_turns(client):
    """NPCs with no shared turn numbers produce no inter-npc links."""
    state = create_initial_state()
    run_id = state.run_id
    state.npcs[0].player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "x"},
    ]
    state.npcs[1].player_interactions = [
        {"turn": 2, "year": 410, "action_type": "speak", "intent": "y"},
    ]
    await persistence.save_session(state)

    data = (await client.get(f"/api/run/{run_id}/interaction_graph")).json()
    assert data["npc_links"] == []


@pytest.mark.asyncio
async def test_npc_links_one_shared_turn(client):
    """Two NPCs both engaged on the same turn produce one link."""
    state = create_initial_state()
    run_id = state.run_id
    a, b = state.npcs[0], state.npcs[1]
    a.player_interactions = [
        {"turn": 3, "year": 410, "action_type": "speak", "intent": "to A"},
    ]
    b.player_interactions = [
        {"turn": 3, "year": 410, "action_type": "speak", "intent": "to B"},
    ]
    await persistence.save_session(state)

    data = (await client.get(f"/api/run/{run_id}/interaction_graph")).json()
    assert len(data["npc_links"]) == 1
    link = data["npc_links"][0]
    assert {link["source"], link["target"]} == {a.id, b.id}
    assert link["shared_turns"] == [3]
    assert link["weight"] == 1


@pytest.mark.asyncio
async def test_npc_links_multiple_shared_turns(client):
    """A pair seen together on multiple turns has weight = #shared turns."""
    state = create_initial_state()
    run_id = state.run_id
    a, b = state.npcs[0], state.npcs[1]
    a.player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "x"},
        {"turn": 2, "year": 410, "action_type": "trade", "intent": "y"},
        {"turn": 5, "year": 411, "action_type": "speak", "intent": "z"},
    ]
    b.player_interactions = [
        {"turn": 1, "year": 410, "action_type": "speak", "intent": "x2"},
        {"turn": 2, "year": 410, "action_type": "speak", "intent": "y2"},
        {"turn": 4, "year": 411, "action_type": "speak", "intent": "alone"},
    ]
    await persistence.save_session(state)

    data = (await client.get(f"/api/run/{run_id}/interaction_graph")).json()
    assert len(data["npc_links"]) == 1
    link = data["npc_links"][0]
    assert link["shared_turns"] == [1, 2]
    assert link["weight"] == 2


@pytest.mark.asyncio
async def test_npc_links_shape_keys(client):
    """Each link record exposes exactly the documented keys."""
    state = create_initial_state()
    run_id = state.run_id
    a, b = state.npcs[0], state.npcs[1]
    a.player_interactions = [
        {"turn": 7, "year": 412, "action_type": "speak", "intent": "x"},
    ]
    b.player_interactions = [
        {"turn": 7, "year": 412, "action_type": "speak", "intent": "y"},
    ]
    await persistence.save_session(state)

    data = (await client.get(f"/api/run/{run_id}/interaction_graph")).json()
    assert len(data["npc_links"]) == 1
    assert set(data["npc_links"][0].keys()) == {
        "source", "target", "shared_turns", "weight",
    }


@pytest.mark.asyncio
async def test_npc_links_zero_turn_entries_ignored(client):
    """A turn=0 entry (defensive: should not happen but might in old data)
    must NOT trigger a spurious shared-turn link."""
    state = create_initial_state()
    run_id = state.run_id
    a, b = state.npcs[0], state.npcs[1]
    a.player_interactions = [
        {"turn": 0, "year": 410, "action_type": "speak", "intent": "stale"},
    ]
    b.player_interactions = [
        {"turn": 0, "year": 410, "action_type": "speak", "intent": "stale"},
    ]
    await persistence.save_session(state)

    data = (await client.get(f"/api/run/{run_id}/interaction_graph")).json()
    assert data["npc_links"] == []
