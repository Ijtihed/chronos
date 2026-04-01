ERA = {
    "name": "Crusader States",
    "year_start": 1190,
    "region": "Levant",
    "description": (
        "The Third Crusade has stalled. Saladin holds Jerusalem, and the "
        "Crusader states cling to a narrow strip of coast. Acre is the "
        "lifeline — a port city where Frankish knights, Italian merchants, "
        "local Christians, and Muslim traders coexist in uneasy tension. "
        "Richard the Lionheart negotiates while his army starves."
    ),
    "years_per_turn": 0.25,
    "lifespan_turns": [35, 55],
    "locations": [
        {
            "id": "acre",
            "name": "Acre",
            "description": (
                "The great Crusader port. Genoese and Venetian quarters "
                "dominate the waterfront. The Hospitaller fortress looms "
                "over crowded streets where Latin, Arabic, and Greek mix."
            ),
            "political_tension": "high",
            "lat": 32.92,
            "lon": 35.07,
            "neighbors": {"tyre": 2, "jaffa": 3},
        },
        {
            "id": "tyre",
            "name": "Tyre",
            "description": (
                "An ancient Phoenician city, now the strongest Crusader "
                "fortress in the Levant. It held against Saladin when "
                "all else fell. Its harbor shelters the remnants of the "
                "Kingdom's fleet."
            ),
            "political_tension": "moderate",
            "lat": 33.27,
            "lon": 35.20,
            "neighbors": {"acre": 2},
        },
        {
            "id": "jaffa",
            "name": "Jaffa",
            "description": (
                "A contested port south of Acre, recently changing hands "
                "between Crusader and Ayyubid forces. The fields around "
                "it are scorched. Pilgrims still arrive, hoping to reach "
                "Jerusalem."
            ),
            "political_tension": "critical",
            "lat": 32.05,
            "lon": 34.75,
            "neighbors": {"acre": 3},
        },
    ],
    "player_archetypes": [
        {"role": "Genoese merchant", "archetype": "merchant", "social_class": "foreign_trader"},
        {"role": "Hospitaller sergeant", "archetype": "soldier", "social_class": "military_order"},
        {"role": "Armenian translator", "archetype": "interpreter", "social_class": "local_christian"},
        {"role": "Pilgrim stranded by war", "archetype": "pilgrim", "social_class": "commoner"},
    ],
    "npc_archetypes": [
        {"role": "Hospitaller knight-commander", "archetype": "knight", "social_class": "military_order"},
        {"role": "Venetian consul", "archetype": "diplomat", "social_class": "foreign_noble"},
        {"role": "Arab physician", "archetype": "scholar", "social_class": "dhimmi"},
        {"role": "Frankish blacksmith", "archetype": "craftsman", "social_class": "burgher"},
        {"role": "Bedouin horse trader", "archetype": "merchant", "social_class": "nomad"},
        {"role": "Greek Orthodox priest", "archetype": "clergy", "social_class": "local_christian"},
        {"role": "Ayyubid envoy", "archetype": "diplomat", "social_class": "muslim_elite"},
        {"role": "Leper at the lazaret", "archetype": "outcast", "social_class": "marginal"},
        {"role": "Templar treasurer", "archetype": "administrator", "social_class": "military_order"},
        {"role": "Local Maronite farmer", "archetype": "peasant", "social_class": "local_christian"},
    ],
}
