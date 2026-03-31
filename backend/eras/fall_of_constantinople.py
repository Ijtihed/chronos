ERA = {
    "name": "Fall of Constantinople",
    "year_start": 1453,
    "region": "Byzantine Empire and the Ottoman frontier",
    "description": (
        "Sultan Mehmed II masses his army outside the walls of Constantinople. "
        "The city that stood for a thousand years is defended by barely 7,000 "
        "men against over 80,000 Ottoman troops. Emperor Constantine XI "
        "appeals to the West, but no relief comes. The great chain blocks "
        "the Golden Horn. The final siege has begun."
    ),
    "years_per_turn": 0.05,
    "lifespan_turns": [40, 55],
    "locations": [
        {
            "id": "constantinople",
            "name": "Constantinople",
            "description": (
                "The Queen of Cities, reduced to a shadow. Great churches "
                "stand half-empty. The Theodosian Walls have held for a "
                "millennium, but the Ottoman cannons are something new."
            ),
            "political_tension": "critical",
            "neighbors": {"galata": 1, "adrianople": 4},
        },
        {
            "id": "galata",
            "name": "Galata",
            "description": (
                "The Genoese trading colony across the Golden Horn. "
                "Officially neutral, its merchants profit from both sides. "
                "The chain stretching across the harbor is anchored here."
            ),
            "political_tension": "high",
            "neighbors": {"constantinople": 1},
        },
        {
            "id": "adrianople",
            "name": "Adrianople",
            "description": (
                "The Ottoman capital in Europe, where Mehmed marshaled "
                "his forces. The great cannon of Orban was cast here. "
                "A cosmopolitan city of Turks, Greeks, and Slavs living "
                "under Ottoman rule."
            ),
            "political_tension": "moderate",
            "neighbors": {"constantinople": 4},
        },
    ],
    "player_archetypes": [
        {"role": "Greek icon painter", "archetype": "artisan", "social_class": "craftsman"},
        {"role": "Venetian ship captain", "archetype": "sailor", "social_class": "foreign_trader"},
        {"role": "Monastery librarian", "archetype": "scholar", "social_class": "religious"},
        {"role": "Armenian merchant", "archetype": "merchant", "social_class": "minority_trader"},
    ],
    "npc_archetypes": [
        {"role": "Emperor's steward", "archetype": "administrator", "social_class": "imperial"},
        {"role": "Genoese condottiere", "archetype": "mercenary", "social_class": "foreign_military"},
        {"role": "Orthodox patriarch's secretary", "archetype": "clergy", "social_class": "religious"},
        {"role": "Turkish janissary deserter", "archetype": "soldier", "social_class": "ottoman_military"},
        {"role": "Venetian bailo (consul)", "archetype": "diplomat", "social_class": "foreign_noble"},
        {"role": "Greek fisherman", "archetype": "civilian", "social_class": "commoner"},
        {"role": "Hungarian cannon founder", "archetype": "engineer", "social_class": "foreign_artisan"},
        {"role": "Hagia Sophia custodian", "archetype": "caretaker", "social_class": "religious"},
        {"role": "Jewish physician", "archetype": "healer", "social_class": "minority"},
        {"role": "Slavic refugee from Thessaloniki", "archetype": "refugee", "social_class": "displaced"},
    ],
}
