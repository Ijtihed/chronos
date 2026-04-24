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
            "lat": 44.06,
            "lon": 12.57,
            "neighbors": {"ravenna": 2, "mediolanum": 4},
            "trade_routes": ["ravenna", "mediolanum"],
            "material_conditions": "Grain arrives irregularly from the south. The harbor still functions but fewer ships dock.",
            "food_scarcity": "scarce",
        },
        {
            "id": "ravenna",
            "name": "Ravenna",
            "description": (
                "The imperial capital, surrounded by marshes. Emperor Honorius "
                "hides behind its walls. The court seethes with intrigue."
            ),
            "political_tension": "critical",
            "lat": 44.42,
            "lon": 12.20,
            "neighbors": {"ariminum": 2, "mediolanum": 3},
            "trade_routes": ["ariminum", "mediolanum"],
            "material_conditions": "The imperial granaries are stocked but refugees strain resources.",
            "food_scarcity": "normal",
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
            "lat": 45.46,
            "lon": 9.19,
            "neighbors": {"ariminum": 4, "ravenna": 3},
            "trade_routes": ["ariminum", "ravenna"],
            "material_conditions": "Trade from the north has slowed. The bishop's granary feeds the poor.",
            "food_scarcity": "scarce",
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
    "npc_opportunities": {
        "soldier": ["patrol the road to Ravenna for Visigoth scouts", "drill the garrison with men who haven't been paid in months", "argue with the tribune about whether to hold or retreat", "escort a grain wagon through bandit country", "interrogate a captured barbarian interpreter", "stand guard at the harbor while ships load refugees"],
        "clergy": ["preach against the Arian heresy to a congregation that isn't listening", "hide church silver before the barbarians arrive", "argue with the bishop about sheltering pagans in the basilica", "baptize a dying soldier who never believed until now", "write a letter to Rome begging for reinforcements that won't come", "distribute bread from the church stores to refugees"],
        "administrator": ["count the grain reserves and realize they last two weeks", "forge travel papers for a senator trying to reach Ravenna", "negotiate with the Visigoth interpreter about tribute", "collect taxes from merchants who have nothing left to give", "argue with the centurion about billeting soldiers in civilian homes", "inventory weapons in the armory and find half are rusted through"],
        "refugee": ["beg the innkeeper for a corner to sleep in", "trade a silver brooch for a sack of millet", "hide children from soldiers conscripting anyone who can hold a spear", "search abandoned villas for food and blankets", "argue with other refugees about which road south is still open", "pray at a roadside shrine and leave the last coin as an offering"],
        "merchant": ["bribe the harbor master for a berth on the next ship south", "sell grain at triple the price because there is no competition left", "hide the best goods in a false-bottomed cart", "negotiate with a barbarian war band for safe passage of a caravan", "argue with the tax collector about duties on goods that won't reach their destination", "count remaining stock and decide what to abandon"],
        "outsider": ["scout the Roman defenses and report back to the war band", "trade stolen Roman silver for information about troop movements", "approach the barbarian interpreter with a message from the chief", "slip through the gate at night posing as a refugee", "watch the harbor from the hills and count the ships", "bargain with a Roman merchant for iron and salt"],
        "civilian": ["board up the inn and hide the wine in the cellar", "barter with a soldier for protection in exchange for lodging", "cook the last of the stored grain into bread for the neighborhood", "argue with the landlord about rent when there is no money left", "carry water from the aqueduct before it gets cut off", "tend the garden behind the house because the market is empty"],
    },
    "loading_events": ['395 AD — Emperor Theodosius dies. The Roman Empire splits permanently into East and West.', '402 AD — The Western court flees Rome for the marshes of Ravenna.', '406 AD — Vandals, Alans, and Suevi cross the frozen Rhine into Gaul. The frontier collapses.', '408 AD — Stilicho, last effective defender of the West, is executed by Honorius.'],
    "loading_voices": [{'quote': 'The city which had taken the whole world was itself taken.', 'source': 'Jerome, Letter 127'}, {'quote': 'Rome is not bricks and mortar. Rome is wherever Romans stand.', 'source': 'Attributed, 5th century'}],

}
