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

    def test_action_parser_strips_metadata_header(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert not raw.startswith("#")
        assert "Model tier" not in raw
        assert "$player_input" in raw

    def test_npc_pov_strips_metadata_header(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert not raw.startswith("#")
        assert "$npc_name" in raw


class TestActionParserSubstitution:
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
            player_input="talk to the centurion",
        )
        assert "$" not in result, f"Unfilled placeholders remain: {result}"

    def test_includes_npc_impacts_in_output_spec(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "npc_impacts" in raw
        assert "sentiment" in raw

    def test_includes_story_so_far_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "$story_so_far" in raw


class TestNpcPovSubstitution:
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
            era_description_of_action="Corvinus approached the garrison.",
            action_intent="speak to the centurion",
        )
        assert "$" not in result, f"Unfilled placeholders remain: {result}"

    def test_instructs_first_person(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "first person" in raw.lower()

    def test_forbids_modern_language(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "modern" in raw.lower()

    def test_limits_response_length(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "2-4 sentences" in raw

    def test_includes_story_so_far_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "$story_so_far" in raw
