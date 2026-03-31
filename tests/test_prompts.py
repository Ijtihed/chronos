"""Unit tests for prompt template loading and substitution.

No LLM calls — verifies templates exist, parse correctly, and substitute cleanly.
"""

from pathlib import Path
from string import Template

from backend.llm import load_prompt
from backend.world_state import build_story_summary, create_initial_state

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class TestPromptLoading:
    def test_action_parser_template_exists(self):
        path = PROMPTS_DIR / "action_parser.md"
        assert path.exists(), "prompts/action_parser.md missing"

    def test_npc_pov_template_exists(self):
        path = PROMPTS_DIR / "npc_pov.md"
        assert path.exists(), "prompts/npc_pov.md missing"

    def test_action_parser_strips_metadata_header(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert not raw.startswith("#"), "Header should be stripped"
        assert "Model tier" not in raw, "Metadata should be stripped"
        assert "$player_input" in raw, "Prompt body should remain"

    def test_npc_pov_strips_metadata_header(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert not raw.startswith("#"), "Header should be stripped"
        assert "$npc_name" in raw, "Prompt body should remain"


class TestActionParserSubstitution:
    def test_all_placeholders_fill(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        state = create_initial_state()
        npc_list = ", ".join(f"{n.name} ({n.role})" for n in state.npcs)

        result = Template(raw).safe_substitute(
            year=state.era.year,
            era_description=state.era.description,
            player_name=state.player.name,
            player_role=state.player.role,
            location_name=state.location.name,
            location_description=state.location.description,
            npcs=npc_list,
            story_so_far=build_story_summary(state),
            political_tension=state.location.political_tension,
            player_input="talk to the centurion",
        )

        assert "$" not in result, f"Unfilled placeholders remain: {result}"

    def test_contains_player_input(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        result = Template(raw).safe_substitute(
            year=410,
            era_description="test",
            player_name="Test",
            player_role="test",
            location_name="Test",
            location_description="test",
            npcs="none",
            story_so_far="nothing yet",
            political_tension="high",
            player_input="steal the horse",
        )
        assert "steal the horse" in result

    def test_mentions_json_output_format(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "action_type" in raw
        assert "era_description" in raw
        assert "JSON" in raw

    def test_includes_story_so_far_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "$story_so_far" in raw

    def test_includes_npc_impacts_in_output_spec(self):
        raw = load_prompt(PROMPTS_DIR / "action_parser.md")
        assert "npc_impacts" in raw
        assert "sentiment" in raw


class TestNpcPovSubstitution:
    def test_all_placeholders_fill(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        state = create_initial_state()
        npc = state.npcs[0]

        result = Template(raw).safe_substitute(
            npc_name=npc.name,
            npc_role=npc.role,
            npc_description=npc.description,
            npc_disposition=npc.disposition,
            relationship_to_player=npc.relationship_to_player,
            player_name=state.player.name,
            era_description=state.era.description,
            location_name=state.location.name,
            year=state.era.year,
            story_so_far=build_story_summary(state),
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

    def test_instructs_accumulation_awareness(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "accumulation" in raw.lower()
