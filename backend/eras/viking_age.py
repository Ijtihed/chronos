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
            "lat": 59.05,
            "lon": 10.22,
            "neighbors": {"hedeby": 3, "birka": 4},
            "trade_routes": ["hedeby", "birka"],
            "material_conditions": (
                "Silver, furs, and Baltic goods move through timber warehouses "
                "and busy seasonal markets."
            ),
            "food_scarcity": "normal",
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
            "lat": 54.49,
            "lon": 9.57,
            "neighbors": {"kaupang": 3, "birka": 3, "jorvik": 5},
            "trade_routes": ["kaupang", "birka", "jorvik"],
            "material_conditions": (
                "North Sea and Baltic trade meet here, with iron, cloth, and "
                "slaves bartered inside the ramparts year-round."
            ),
            "food_scarcity": "abundant",
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
            "lat": 59.34,
            "lon": 17.54,
            "neighbors": {"kaupang": 4, "hedeby": 3},
            "trade_routes": ["kaupang", "hedeby"],
            "material_conditions": (
                "Eastern silver and river-borne goods from Rus routes supply "
                "smithies, scales, and the king's toll collectors."
            ),
            "food_scarcity": "normal",
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
            "lat": 53.96,
            "lon": -1.08,
            "neighbors": {"hedeby": 5},
            "trade_routes": ["hedeby"],
            "material_conditions": (
                "English grain and Danelaw tribute feed Norse households while "
                "metal and cloth still move along the old Roman roads."
            ),
            "food_scarcity": "normal",
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
    "npc_opportunities": {
        "warrior": ["sharpen weapons before the next raid", "challenge a rival to a holmgang over an insult at the feast", "demand a larger share of the plunder from the jarl", "drill with the younger warriors on the beach", "stand watch over the longships at night", "argue about whether to raid south or trade east this season"],
        "merchant": ["weigh silver dirhams against furs in the market", "bribe the harbor master at Hedeby for a better berth", "negotiate passage on a ship heading to Miklagard", "hide the best pelts from the jarl's tax collector", "argue with a Rus trader about the price of amber", "assess whether the ice will close the trade route early this year"],
        "mystic": ["cast runes to read the fate of the coming raid", "warn the jarl's wife about an omen in the entrails", "prepare a ritual offering to Odin before the ships sail", "argue with the Christian missionary about whose god is stronger", "tend a sick child with herbs and chanting", "interpret a dream that foretold a death at sea"],
        "clergy": ["preach to skeptical Norsemen who mock the cross", "baptize a thrall who hopes it will earn better treatment", "argue with the volva about pagan rites in the hall", "hide the silver chalice when raiders approach", "write a letter to the bishop begging for protection from the Northmen", "tend the small wooden church that the locals use for firewood"],
        "craftsman": ["hammer rivets into a new longship hull on the beach", "repair a sword that was notched in the last raid", "argue with the jarl about payment for a shield commission", "cast silver arm-rings from melted-down Arabic coins", "mend fishing nets before the herring run", "work the bellows through the night to finish a blade for the sailing"],
        "noble": ["hold court in the great hall and settle a land dispute", "plan the spring raid and argue about targets", "feast with visiting traders and extract news of the south", "negotiate a marriage alliance with a neighboring jarl", "punish a thrall who tried to escape last night", "count the tribute from the English and decide it is not enough"],
        "sailor": ["caulk the hull of the longship with tar and animal hair", "read the sky and argue about when to sail", "repair the sail that tore in the last storm", "teach a young man to navigate by the stars", "load provisions for a voyage east along the river routes", "check the oars for rot and replace two that have cracked"],
        "captive": ["carry firewood from the forest for the jarl's hall", "serve food at the feast and try not to be noticed", "whisper prayers in Saxon while scrubbing the floor", "hide a stolen knife under the straw bedding", "beg the jarl's wife for warmer clothing before winter", "plan an escape route through the forest if the chance comes"],
    },
    "loading_events": ['793 AD — Norse raiders sack Lindisfarne. The Viking Age begins.', '845 AD — Ragnar Lothbrok besieges Paris with 120 ships.', '865 AD — The Great Heathen Army lands in England.', '867 AD — The Norse capture York. The Danelaw is born.'],
    "loading_voices": [{'quote': 'From the fury of the Northmen, O Lord, deliver us.', 'source': 'Frankish prayer, 9th century'}, {'quote': 'Cattle die, kinsmen die, you yourself will die. But the reputation of the dead never dies.', 'source': 'Havamal, verse 77'}],

}
