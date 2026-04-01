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
}
