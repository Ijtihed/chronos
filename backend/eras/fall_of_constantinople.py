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
            "lat": 41.01,
            "lon": 28.98,
            "neighbors": {"galata": 1, "adrianople": 4},
            "trade_routes": ["galata", "adrianople"],
            "material_conditions": (
                "Siege stores shrink daily while smugglers and blockade-runners "
                "risk the walls for grain, salt fish, and fodder."
            ),
            "food_scarcity": "critical",
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
            "lat": 41.03,
            "lon": 28.97,
            "neighbors": {"constantinople": 1},
            "trade_routes": ["constantinople"],
            "material_conditions": (
                "Neutral Genoese warehouses still see grain, iron, and silver "
                "from both empires for whoever pays the toll."
            ),
            "food_scarcity": "normal",
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
            "lat": 41.68,
            "lon": 26.56,
            "neighbors": {"constantinople": 4},
            "trade_routes": ["constantinople"],
            "material_conditions": (
                "Ottoman magazines and Balkan convoys stock the camp with "
                "flour, livestock, and timber for the siege train."
            ),
            "food_scarcity": "abundant",
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
    "npc_opportunities": {
        "soldier": ["man the walls during the night watch", "trade rations for information about Ottoman movements", "desert through the harbor district", "drag a wounded man to the physician", "argue with the captain about defending a breach", "pray in the Hagia Sophia before the next assault"],
        "mercenary": ["negotiate a higher fee from the Emperor's steward", "scout the Ottoman lines from the sea walls", "threaten to leave unless paid in gold not promises", "drill the Greek militia who have never held a sword", "steal supplies from an unguarded warehouse", "drink with the Venetian sailors and trade rumors"],
        "administrator": ["ration the last grain stores between the garrison and civilians", "forge a letter requesting Venetian reinforcements", "argue with the Patriarch about melting church silver for coin", "count surviving defenders and realize the numbers are worse than reported", "bribe a Genoese captain to smuggle a message out", "order civilians to carry stones to the walls"],
        "diplomat": ["draft a letter to the Doge that will arrive too late", "negotiate safe passage for Venetian nationals with a Turkish envoy", "assess whether the Genoese in Galata are truly neutral", "argue with the Emperor about surrender terms", "send a runner to the harbor to check which ships remain", "meet secretly with a Greek official about betrayal"],
        "clergy": ["preach to terrified civilians in the Hagia Sophia", "argue with the Catholic cardinal about church union", "hide sacred relics in a cellar before the walls fall", "refuse to bless the cannon because killing is sin", "comfort a dying soldier who is terrified of hell", "write a chronicle entry in case no one survives to remember"],
        "civilian": ["haul water from the cisterns to the men on the walls", "board up the shop and hide valuables in the floor", "beg the harbor master for a spot on the last ship", "search the rubble after a bombardment for anything usable", "cook what little food remains for the neighborhood", "argue with a soldier who wants to requisition the house"],
        "healer": ["treat a soldier with a festering wound from yesterday's bombardment", "beg the monastery for herbs that are no longer available", "set up a field station near the breach in the walls", "refuse to waste medicine on a man who will die anyway", "argue with the priest about whether plague is God's will or Greek fire residue", "boil instruments in vinegar while casualties pile up outside"],
        "refugee": ["beg for shelter at a church that is already full", "hide children in a cistern passage in case the walls fall", "steal bread from an unguarded cart in the harbor district", "plead with a Venetian captain to take your family aboard", "sleep in the ruins of a house destroyed by cannon fire", "trade a family heirloom for a day's worth of food"],
        "engineer": ["inspect cannon damage to the Theodosian Walls at first light", "cast replacement parts for the bombard using melted church bells", "argue with the general about where to position the remaining artillery", "reinforce a section of wall with timber and rubble overnight", "repair the great chain across the Golden Horn", "design a counter-mine against Ottoman tunneling"],
        "caretaker": ["sweep debris from the Hagia Sophia nave after the latest bombardment", "hide manuscripts and icons in the crypt", "bar the doors against soldiers looking for firewood", "tend the oil lamps that have burned continuously for centuries", "argue with the Patriarch's secretary about refugees sheltering inside", "pray alone in the gallery while cannon fire shakes the walls"],
    },
    "loading_events": ['1422 AD — Murad II besieges Constantinople but fails to take it.', '1444 AD — The Crusade of Varna ends in Ottoman victory. No western relief is coming.', '1452 AD — Mehmed II builds the fortress of Rumelihisarı, choking the Bosphorus.', '1453 AD — The siege begins. 80,000 Ottoman troops face 7,000 defenders.'],
    "loading_voices": [{'quote': 'The city has fallen and I am still alive.', 'source': 'Attributed to Constantine XI Palaiologos'}, {'quote': 'The spider weaves the curtains in the palace of the Caesars.', 'source': 'Mehmed II, quoting Persian poetry after entering the city'}],

}
