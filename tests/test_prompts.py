"""Unit tests for prompt template loading and substitution."""

from pathlib import Path
from string import Template

from backend.llm_provider import load_prompt
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
    # Updated to include variables added by Fix 2 (player_actions_toward_you,
    # memory_level, current_preoccupation) and Fix 5 (this_turn_events).
    def test_all_placeholders_fill(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        state = create_initial_state()
        npc = state.npcs[0]
        player_loc = get_player_location(state)

        result = Template(raw).safe_substitute(
            npc_name=npc.name,
            npc_role=npc.role,
            npc_description=npc.description,
            social_class=npc.social_class or npc.archetype,
            npc_disposition=npc.disposition,
            dominant_need="duty",
            urgent_needs="nothing urgent",
            current_activity=getattr(npc, "current_activity", "") or "Patrolling the walls.",
            relationship_to_player=npc.relationship_to_player,
            player_actions_toward_you="None -- first contact.",
            memory_level="faint",
            current_preoccupation="the immediate situation",
            already_used_details="",
            player_name=state.player.name,
            era_description=state.era.description,
            era_feel="The empire crumbles around us.",
            material_conditions="Grain is scarce. Prices rise.",
            what_character_knows="What anyone in your position would know.",
            local_rumors="Nothing specific.",
            location_name=player_loc.name,
            year=state.current_year or state.era.year_start,
            story_so_far=build_story_summary(state),
            historical_context="No sources available.",
            era_description_of_action="Something happened.",
            action_intent="unknown",
            this_turn_events="Nothing notable.",
        )
        assert "$" not in result, f"Unfilled: {result}"

    def test_instructs_first_person(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "first person" in raw.lower()

    def test_directs_authentic_voice(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "illiterate" in raw.lower()
        assert "swearing" in raw.lower()
        assert "not the player" in raw.lower()

    def test_includes_player_actions_toward_you_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "$player_actions_toward_you" in raw
        assert "$prior_player_interactions" not in raw, (
            "$prior_player_interactions was renamed to $player_actions_toward_you"
        )

    def test_includes_current_preoccupation_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "$current_preoccupation" in raw

    def test_includes_memory_level_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "$memory_level" in raw

    def test_includes_this_turn_events_placeholder(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "$this_turn_events" in raw

    def test_voice_rules_ban_similes(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "NO similes" in raw

    def test_voice_rules_ban_metaphors(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "NO metaphors" in raw

    def test_banned_phrases_listed(self):
        raw = load_prompt(PROMPTS_DIR / "npc_pov.md")
        assert "dark cloud" in raw
        assert "BANNED" in raw


class TestPromptCallSiteCoverage:
    """Catch the class of bug where a prompt template uses a $variable
    that the corresponding call site doesn't actually substitute.

    The contract: every $variable mentioned in the *body* of a prompt
    (below the `---` metadata header) must be filled in by a
    `safe_substitute(...)` call somewhere in `backend/`. `safe_substitute`
    leaves unbound variables as literal `$name` strings in the rendered
    prompt — which then goes to the LLM as noise. The fix is either to
    pass the variable from the call site OR remove it from the template.

    This test scans every prompt and the union of every safe_substitute
    kwarg set in backend/, then fails if any prompt has a variable that
    no call site provides.
    """

    def test_every_prompt_variable_is_provided_by_some_call_site(self):
        import re

        backend_dir = Path(__file__).resolve().parent.parent / "backend"

        # Walk each safe_substitute(...) call using a paren-aware
        # scanner. A naive regex with `(.*?)` would stop at the first
        # `)` it finds, which is usually `build_story_summary(state)`
        # nested inside the kwarg block — leaving most kwargs uncounted.
        provided: set[str] = set()
        for py_file in backend_dir.rglob("*.py"):
            text = py_file.read_text()
            i = 0
            while True:
                idx = text.find("safe_substitute", i)
                if idx == -1:
                    break
                open_paren = text.find("(", idx)
                if open_paren == -1:
                    break
                # Walk to the matching `)` accounting for nested parens.
                depth = 0
                pos = open_paren
                while pos < len(text):
                    ch = text[pos]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    pos += 1
                if pos >= len(text):
                    break
                kw_block = text[open_paren + 1:pos]
                # Match `name=` at top level (only when not inside a
                # nested call's parens). Simpler: just collect every
                # name=... whose `=` is followed by anything other than
                # another `=` (so we avoid `==` comparisons).
                for kw in re.findall(
                    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=(?!=)",
                    kw_block,
                ):
                    provided.add(kw)
                i = pos + 1

        # For each prompt template, compute the variable set used in
        # the body (after the metadata header). Both `$var` and `${var}`
        # syntaxes are valid for Python's Template.
        var_pattern = re.compile(r"\$\{?([a-zA-Z_][a-zA-Z0-9_]*)\}?")
        missing_by_prompt: dict[str, list[str]] = {}
        for prompt_path in sorted(PROMPTS_DIR.glob("*.md")):
            raw = load_prompt(prompt_path)
            used = set(var_pattern.findall(raw))
            missing = sorted(v for v in used if v not in provided)
            if missing:
                missing_by_prompt[prompt_path.name] = missing

        assert not missing_by_prompt, (
            "These prompt variables appear in a template body but no "
            "safe_substitute() call in backend/ provides them. The LLM "
            "will receive literal $var strings. Either pass the variable "
            "from the call site or remove it from the prompt:\n"
            + "\n".join(
                f"  {name}: missing {vars}"
                for name, vars in missing_by_prompt.items()
            )
        )
