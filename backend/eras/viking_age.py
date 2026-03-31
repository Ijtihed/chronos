ERA = {
    "name": "Viking Age",
    "year_start": 870,
    "region": "Scandinavia and the North Sea",
    "description": (
        "The Norse world is in motion. Raiders turned settlers push into "
        "England, Francia, and beyond. In Scandinavia, petty kings compete "
        "for dominance while the old gods share altars with the new Christ. "
        "Trade routes stretch from Byzantium to Iceland."
    ),
    "years_per_turn": 0.5,
    "lifespan_turns": [35, 50],
    "locations": [
        {
            "id": "kaupang",
            "name": "Kaupang",
            "description": (
                "A bustling Norse trading post on the Oslofjord. Merchants "
                "from across the known world barter silver, furs, and slaves. "
                "Longships crowd the harbor."
            ),
            "political_tension": "moderate",
            "neighbors": {"hedeby": 3, "birka": 4},
        },
        {
            "id": "hedeby",
            "name": "Hedeby",
            "description": (
                "The great emporium of the Danes, straddling the trade route "
                "between the North Sea and the Baltic. Fortified with an "
                "earthen rampart, it teems with Frisians, Saxons, and Slavs."
            ),
            "political_tension": "high",
            "neighbors": {"kaupang": 3, "birka": 3, "jorvik": 5},
        },
        {
            "id": "birka",
            "name": "Birka",
            "description": (
                "An island trading town on Lake Malaren in Svealand. The "
                "Rus trade routes to the east flow through here. A Christian "
                "mission has recently arrived, unsettling the local priests."
            ),
            "political_tension": "moderate",
            "neighbors": {"kaupang": 4, "hedeby": 3},
        },
        {
            "id": "jorvik",
            "name": "Jorvik",
            "description": (
                "The Norse kingdom in England, formerly Anglo-Saxon York. "
                "A contested city where Norse warriors rule over English "
                "subjects. The Great Heathen Army's legacy lingers."
            ),
            "political_tension": "high",
            "neighbors": {"hedeby": 5},
        },
    ],
    "player_archetypes": [
        {"role": "Fur trader", "archetype": "merchant", "social_class": "free"},
        {"role": "Thrall freed by a jarl", "archetype": "freed_slave", "social_class": "freed"},
        {"role": "Shipwright's apprentice", "archetype": "craftsman", "social_class": "free"},
        {"role": "Skald without a patron", "archetype": "storyteller", "social_class": "wanderer"},
    ],
    "npc_archetypes": [
        {"role": "Jarl's hirdman", "archetype": "warrior", "social_class": "noble_retainer"},
        {"role": "Volva (seeress)", "archetype": "mystic", "social_class": "religious"},
        {"role": "Christian missionary", "archetype": "clergy", "social_class": "religious"},
        {"role": "Slave trader", "archetype": "merchant", "social_class": "free"},
        {"role": "Blacksmith", "archetype": "craftsman", "social_class": "free"},
        {"role": "Jarl's wife", "archetype": "noble", "social_class": "nobility"},
        {"role": "Rus river trader", "archetype": "merchant", "social_class": "foreign"},
        {"role": "Saxon captive", "archetype": "captive", "social_class": "enslaved"},
        {"role": "Shipmaster", "archetype": "sailor", "social_class": "free"},
        {"role": "Gotland silver merchant", "archetype": "merchant", "social_class": "wealthy_free"},
    ],
}
