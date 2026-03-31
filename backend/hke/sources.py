"""Source material catalog for each era.

Maps era keys to Gutenberg text IDs and Wikipedia article titles.
These are downloaded and chunked by the ingestion pipeline.
"""

ERA_SOURCES = {
    "roman_late_empire": {
        "gutenberg": [
            {"id": 25717, "title": "The History of the Decline and Fall of the Roman Empire, Vol. 3 — Gibbon"},
            {"id": 25717, "title": "Decline and Fall Vol. 3"},
            {"id": 890, "title": "The Confessions of St. Augustine"},
        ],
        "wikipedia": [
            "Fall of the Western Roman Empire",
            "Sack of Rome (410)",
            "Alaric I",
            "Honorius (emperor)",
            "Late Roman Empire",
            "Roman economy in late antiquity",
        ],
    },
    "viking_age": {
        "gutenberg": [
            {"id": 13882, "title": "The Story of Burnt Njal (Njal's Saga)"},
            {"id": 1150, "title": "The Prose Edda — Snorri Sturluson"},
        ],
        "wikipedia": [
            "Viking Age",
            "Norse mythology",
            "Viking expansion",
            "Danelaw",
            "Norse trade routes",
            "Thing (assembly)",
        ],
    },
    "crusader_states": {
        "gutenberg": [
            {"id": 4927, "title": "Chronicles of the Crusades — Joinville and Villehardouin"},
        ],
        "wikipedia": [
            "Crusader states",
            "Third Crusade",
            "Siege of Acre (1189-1191)",
            "Saladin",
            "Kingdom of Jerusalem",
            "Military orders in the Middle Ages",
        ],
    },
    "black_death": {
        "gutenberg": [
            {"id": 3726, "title": "The Decameron — Boccaccio"},
        ],
        "wikipedia": [
            "Black Death",
            "Black Death in England",
            "Flagellants",
            "Plague doctor",
            "Consequences of the Black Death",
            "Medieval Jewish persecutions",
        ],
    },
    "fall_of_constantinople": {
        "gutenberg": [
            {"id": 13382, "title": "The Fall of Constantinople — Edwin Pears"},
        ],
        "wikipedia": [
            "Fall of Constantinople",
            "Mehmed the Conqueror",
            "Constantine XI Palaiologos",
            "Walls of Constantinople",
            "Byzantine Empire under the Palaiologos dynasty",
            "Ottoman conquest of the Balkans",
        ],
    },
}
