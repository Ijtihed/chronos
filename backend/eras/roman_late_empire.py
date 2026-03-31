ERA = {
    "name": "Roman Late Empire",
    "year_start": 410,
    "region": "Italia",
    "description": (
        "The Western Roman Empire crumbles. Emperor Honorius cowers in "
        "Ravenna while Alaric's Visigoths march south through Italia. "
        "The legions are stretched thin, the grain supply from Africa is "
        "uncertain, and provincial towns brace for what comes next."
    ),
    "years_per_turn": 0.25,
    "lifespan_turns": [40, 60],
    "locations": [
        {
            "id": "ariminum",
            "name": "Ariminum",
            "description": (
                "A fortified Roman town on the Adriatic coast where the Via "
                "Flaminia meets the sea. The garrison is half its former "
                "strength. Refugees trickle in from the north."
            ),
            "political_tension": "high",
            "neighbors": {"ravenna": 2, "mediolanum": 4},
        },
        {
            "id": "ravenna",
            "name": "Ravenna",
            "description": (
                "The imperial capital, surrounded by marshes. Emperor Honorius "
                "hides behind its walls. The court seethes with intrigue."
            ),
            "political_tension": "critical",
            "neighbors": {"ariminum": 2, "mediolanum": 3},
        },
        {
            "id": "mediolanum",
            "name": "Mediolanum",
            "description": (
                "Once the administrative capital, now declining. A powerful "
                "bishop holds sway. Trade persists but barbarian raids "
                "threaten the northern approaches."
            ),
            "political_tension": "high",
            "neighbors": {"ariminum": 4, "ravenna": 3},
        },
    ],
    "player_archetypes": [
        {"role": "Grain merchant", "archetype": "merchant", "social_class": "plebeian"},
        {"role": "Retired legionary", "archetype": "soldier", "social_class": "military"},
        {"role": "Scribe at the basilica", "archetype": "scholar", "social_class": "religious"},
        {"role": "Refugee from Pannonia", "archetype": "refugee", "social_class": "displaced"},
    ],
    "npc_archetypes": [
        {"role": "Centurion of the garrison", "archetype": "soldier", "social_class": "military"},
        {"role": "Christian deacon", "archetype": "clergy", "social_class": "religious"},
        {"role": "Senator's steward", "archetype": "administrator", "social_class": "patrician"},
        {"role": "Refugee family elder", "archetype": "refugee", "social_class": "displaced"},
        {"role": "Harbor master", "archetype": "merchant", "social_class": "plebeian"},
        {"role": "Barbarian interpreter", "archetype": "outsider", "social_class": "liminal"},
        {"role": "Widowed innkeeper", "archetype": "civilian", "social_class": "plebeian"},
        {"role": "Tax collector", "archetype": "administrator", "social_class": "imperial"},
        {"role": "Local bishop", "archetype": "clergy", "social_class": "religious"},
        {"role": "Visigoth scout", "archetype": "outsider", "social_class": "barbarian"},
    ],
}
