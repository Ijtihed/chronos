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
    "loading_events": ['1347 AD — Genoese ships bring plague from Caffa to Messina. The Black Death enters Europe.', '1348 AD — The plague reaches Florence. Boccaccio will later write that the dead outnumber the living.', '1348 AD — Flagellant processions sweep through Germany and France.', '1349 AD — Jewish communities across Europe are scapegoated and massacred.'],
    "loading_voices": [{'quote': 'Father abandoned child, wife husband, one brother another; for this illness seemed to strike through breath and sight.', 'source': 'Boccaccio, The Decameron, 1353'}, {'quote': 'So many died that all believed it was the end of the world.', 'source': 'Agnolo di Tura, Chronicle of Siena'}],

}
