"""Unit tests for prompt template loading and substitution."""

from pathlib import Path
from string import Template

from backend.llm import load_prompt
from backend.world_state import (
    build_story_summary,
    create_initial_state,
    get_player_location,
    npcs_near_player,
)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class TestPromptLoading:
    def test_action_parser_template_exists(self):
        assert (PROMPTS_DIR / "action_parser.md").exists()

    def test_npc_pov_template_exists(self):
        assert (PROMPTS_DIR / "npc_pov.md").exists()

    def test_action_parser_strips_metadata(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert not raw.startswith("#")
        assert "$player_input" in raw

    def test_npc_pov_strips_metadata(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert not raw.startswith("#")
        assert "$npc_name" in raw


class TestActionParserPrompt:
    def test_all_placeholders_fill(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        state = create_initial_state()
        nearby = npcs_near_player(state)
        npc_list = ", ".join(f"{n.name} ({n.role})" for n in nearby)
        player_loc = get_player_location(state)

        result = Template(raw).safe_substitute(
            year=state.current_year or state.era.year_start,
            era_description=state.era.description,
            player_name=state.player.name,
            player_role=state.player.role,
            location_name=player_loc.name,
            location_description=player_loc.description,
            npcs=npc_list,
            story_so_far=build_story_summary(state),
            political_tension=player_loc.political_tension,
            reachable_locations="Ravenna (ravenna, 2 turns)",
            player_input="flee the city",
        )
        assert "$" not in result, f"Unfilled: {result}"

    def test_includes_npc_impacts(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "npc_impacts" in raw
        assert "relevant" in raw

    def test_includes_travel_detection(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "is_travel" in raw
        assert "destination" in raw

    def test_includes_inaction_detection(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "is_inaction" in raw

    def test_emphasizes_total_freedom(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "total freedom" in raw.lower()

    def test_includes_reachable_locations(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "$reachable_locations" in raw


class TestNpcPovPrompt:
    def test_all_placeholders_fill(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        state = create_initial_state()
        npc = state.npcs[0]
        player_loc = get_player_location(state)

        result = Template(raw).safe_substitute(
            npc_name=npc.name,
            npc_role=npc.role,
            npc_description=npc.description,
            npc_disposition=npc.disposition,
            relationship_to_player=npc.relationship_to_player,
            player_name=state.player.name,
            era_description=state.era.description,
            location_name=player_loc.name,
            year=state.current_year or state.era.year_start,
            story_so_far=build_story_summary(state),
            historical_context="No sources available.",
            era_description_of_action="Something happened.",
            action_intent="unknown",
        )
        assert "$" not in result, f"Unfilled: {result}"

    def test_instructs_first_person(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "first person" in raw.lower()

    def test_forbids_modern_language(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "modern" in raw.lower()
