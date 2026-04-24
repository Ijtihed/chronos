ERA = {
    "name": "Black Death",
    "year_start": 1348,
    "region": "Northern Italy and Southern France",
    "description": (
        "The pestilence has arrived. Ships from the East brought it to "
        "Sicily, and now it spreads through Italy and into France. Cities "
        "are emptying. The Church offers no answers. Flagellants roam the "
        "roads. The social order is cracking — serfs abandon fields, "
        "prices collapse, and the dead outnumber the living in some towns."
    ),
    "years_per_turn": 0.1,
    "lifespan_turns": [30, 45],
    "locations": [
        {
            "id": "firenze",
            "name": "Firenze",
            "description": (
                "The great banking city of the Arno. The Bardi and Peruzzi "
                "fortunes are already strained; now the plague empties their "
                "counting houses. Boccaccio watches from the hills."
            ),
            "political_tension": "critical",
            "lat": 43.77,
            "lon": 11.25,
            "neighbors": {"siena": 2, "avignon": 5},
            "trade_routes": ["siena", "avignon"],
            "material_conditions": (
                "Wool, credit, and workshop goods pile up unsold as laborers "
                "die and overland routes thin to a trickle."
            ),
            "food_scarcity": "critical",
        },
        {
            "id": "siena",
            "name": "Siena",
            "description": (
                "Florence's rival, struck even harder by the plague. The "
                "great cathedral project halts as workers die. The city "
                "will never recover its former ambition."
            ),
            "political_tension": "critical",
            "lat": 43.32,
            "lon": 11.33,
            "neighbors": {"firenze": 2, "avignon": 4},
            "trade_routes": ["firenze", "avignon"],
            "material_conditions": (
                "Cathedral yards and contado farms lose hands faster than grain "
                "can be carted in from the hill towns."
            ),
            "food_scarcity": "critical",
        },
        {
            "id": "avignon",
            "name": "Avignon",
            "description": (
                "Seat of the Papacy in exile. Pope Clement VI blesses the "
                "dead from his window. The Rhone carries corpses. Jewish "
                "communities face scapegoating as the plague spreads."
            ),
            "political_tension": "critical",
            "lat": 43.95,
            "lon": 4.81,
            "neighbors": {"firenze": 5, "siena": 4, "marseille": 2},
            "trade_routes": ["firenze", "siena", "marseille"],
            "material_conditions": (
                "Papal warehouses and Rhone barges still move wine and grain "
                "while suburbs empty and prices spike with each new burial."
            ),
            "food_scarcity": "critical",
        },
        {
            "id": "marseille",
            "name": "Marseille",
            "description": (
                "The port where the plague first entered France. The harbor "
                "is quarantined but too late. Ships sit abandoned. The "
                "living avoid the docks."
            ),
            "political_tension": "high",
            "lat": 43.30,
            "lon": 5.37,
            "neighbors": {"avignon": 2},
            "trade_routes": ["avignon"],
            "material_conditions": (
                "Quarantined docks and fleeing stevedores have throttled "
                "Provencal grain and seaborne supplies alike."
            ),
            "food_scarcity": "critical",
        },
    ],
    "player_archetypes": [
        {"role": "Wool merchant", "archetype": "merchant", "social_class": "burgher"},
        {"role": "Apothecary's assistant", "archetype": "healer", "social_class": "artisan"},
        {"role": "Wandering friar", "archetype": "clergy", "social_class": "mendicant"},
        {"role": "Notary recording wills", "archetype": "scholar", "social_class": "professional"},
    ],
    "npc_archetypes": [
        {"role": "Plague doctor", "archetype": "healer", "social_class": "professional"},
        {"role": "Flagellant preacher", "archetype": "fanatic", "social_class": "wanderer"},
        {"role": "Jewish moneylender", "archetype": "financier", "social_class": "marginal"},
        {"role": "Bardi bank agent", "archetype": "merchant", "social_class": "elite"},
        {"role": "Gravedigger", "archetype": "laborer", "social_class": "underclass"},
        {"role": "Dominican inquisitor", "archetype": "clergy", "social_class": "religious"},
        {"role": "Contadina fleeing the fields", "archetype": "peasant", "social_class": "serf"},
        {"role": "Papal secretary", "archetype": "administrator", "social_class": "clerical"},
        {"role": "Genoese ship captain", "archetype": "sailor", "social_class": "merchant"},
        {"role": "Orphaned child of a guild master", "archetype": "orphan", "social_class": "displaced"},
    ],
    "npc_opportunities": {
        "healer": ["tend to a flagellant who has whipped himself too severely", "argue with the priest about whether to treat plague victims", "boil vinegar in the street hoping to purify the air", "search a dead merchant's house for medical supplies", "refuse a wealthy family's bribe to treat only them", "burn contaminated clothing over the objections of the owner"],
        "merchant": ["board up the warehouse before looters arrive", "bribe the city gate guards to let you leave", "buy cheap from families abandoning their homes", "hide gold in the church crypt", "negotiate with a moneylender for emergency credit", "send a servant to find out which roads are still open"],
        "fanatic": ["lead a flagellant procession through the streets", "preach that the plague is God's punishment for sin", "accuse the Jewish quarter of poisoning the wells", "whip yourself bloody in the piazza while a crowd watches", "demand the bishop join the procession or be named a heretic", "burn effigies outside the homes of suspected sinners"],
        "financier": ["collect debts from families who have lost their breadwinner", "hide ledgers and coin in a secret cellar", "negotiate interest rates with a desperate wool merchant", "assess which debtors have died and which debts are uncollectable", "bribe the city guard for protection against the mob", "lend to the commune at usurious rates because no one else will"],
        "clergy": ["administer last rites to the dying in a house marked with a cross", "argue with the Dominican inquisitor about who deserves to be saved", "bar the church doors against flagellants who want to preach inside", "write plague dead into the parish register by candlelight", "distribute blessed water that the faithful believe will protect them", "burn juniper in the nave and pray it keeps the pestilence out"],
        "laborer": ["dig graves from dawn until the light fails", "drag bodies on a cart through streets where no one opens a door", "demand higher wages because no one else will do this work", "drink heavily between loads because the smell never leaves", "steal rings from corpses before throwing them in the pit", "argue with the priest about whether the dead deserve proper burial"],
        "peasant": ["flee the fields because the landlord's family has all died", "carry a sick child to the nearest town hoping for a physician", "barricade the farmhouse and refuse to let anyone approach", "harvest whatever has ripened because no one else will", "pray at a roadside shrine and leave the last egg as an offering", "burn the bedding of a family member who showed the black spots"],
        "administrator": ["enforce quarantine by posting guards at the city gates", "count the dead and realize the records are weeks behind", "argue with the guild masters about whether to close the markets", "draft an emergency ordinance on burial outside the walls", "requisition houses of the dead for quarantine hospitals", "beg the Papal secretary to petition Avignon for aid"],
        "sailor": ["refuse to let anyone board who shows symptoms", "dump cargo in the harbor rather than open holds that might be contaminated", "negotiate with the harbor master about quarantine periods", "sail for a port that might still be open and pray the crew stays healthy", "throw a dead crewman overboard at night when no one is watching", "barter ship's biscuit for fresh water from a terrified fishing village"],
        "orphan": ["hide in the back of an abandoned shop and eat what is left on the shelves", "follow the gravedigger's cart hoping he drops food", "beg at the church door until a nun brings bread", "sleep in the bell tower because the plague carts don't come up stairs", "steal from a dead man's house before the neighbors seal it", "sit in the piazza alone because everyone who knew your name is gone"],
    },
    "loading_events": ['1347 AD — Genoese ships bring plague from Caffa to Messina. The Black Death enters Europe.', '1348 AD — The plague reaches Florence. Boccaccio will later write that the dead outnumber the living.', '1348 AD — Flagellant processions sweep through Germany and France.', '1349 AD — Jewish communities across Europe are scapegoated and massacred.'],
    "loading_voices": [{'quote': 'Father abandoned child, wife husband, one brother another; for this illness seemed to strike through breath and sight.', 'source': 'Boccaccio, The Decameron, 1353'}, {'quote': 'So many died that all believed it was the end of the world.', 'source': 'Agnolo di Tura, Chronicle of Siena'}],

}
