ERA = {
    "name": "Crusader States",
    "year_start": 1190,
    "region": "Levant",
    "description": (
        "The Third Crusade has stalled. Saladin holds Jerusalem, and the "
        "Crusader states cling to a narrow strip of coast. Acre is the "
        "lifeline — a port city where Frankish knights, Italian merchants, "
        "local Christians, and Muslim traders coexist in uneasy tension. "
        "Richard the Lionheart negotiates while his army starves."
    ),
    "years_per_turn": 0.25,
    "lifespan_turns": [35, 55],
    "locations": [
        {
            "id": "acre",
            "name": "Acre",
            "description": (
                "The great Crusader port. Genoese and Venetian quarters "
                "dominate the waterfront. The Hospitaller fortress looms "
                "over crowded streets where Latin, Arabic, and Greek mix."
            ),
            "political_tension": "high",
            "lat": 32.92,
            "lon": 35.07,
            "neighbors": {"tyre": 2, "jaffa": 3},
            "trade_routes": ["tyre", "jaffa"],
            "material_conditions": (
                "Frankish and Italian shipping unloads grain, weapons, and "
                "cloth while Crusader wharves still take priority over blockade."
            ),
            "food_scarcity": "normal",
        },
        {
            "id": "tyre",
            "name": "Tyre",
            "description": (
                "An ancient Phoenician city, now the strongest Crusader "
                "fortress in the Levant. It held against Saladin when "
                "all else fell. Its harbor shelters the remnants of the "
                "Kingdom's fleet."
            ),
            "political_tension": "moderate",
            "lat": 33.27,
            "lon": 35.20,
            "neighbors": {"acre": 2},
            "trade_routes": ["acre"],
            "material_conditions": (
                "The island fortress imports most provisions and timber by sea "
                "while mainland convoys stay exposed to raiding."
            ),
            "food_scarcity": "normal",
        },
        {
            "id": "jaffa",
            "name": "Jaffa",
            "description": (
                "A contested port south of Acre, recently changing hands "
                "between Crusader and Ayyubid forces. The fields around "
                "it are scorched. Pilgrims still arrive, hoping to reach "
                "Jerusalem."
            ),
            "political_tension": "critical",
            "lat": 32.05,
            "lon": 34.75,
            "neighbors": {"acre": 3},
            "trade_routes": ["acre"],
            "material_conditions": (
                "Scorched fields and marching armies have stripped the coastal "
                "plain of reliable harvests and safe granaries."
            ),
            "food_scarcity": "scarce",
        },
    ],
    "player_archetypes": [
        {"role": "Genoese merchant", "archetype": "merchant", "social_class": "foreign_trader"},
        {"role": "Hospitaller sergeant", "archetype": "soldier", "social_class": "military_order"},
        {"role": "Armenian translator", "archetype": "interpreter", "social_class": "local_christian"},
        {"role": "Pilgrim stranded by war", "archetype": "pilgrim", "social_class": "commoner"},
    ],
    "npc_archetypes": [
        {"role": "Hospitaller knight-commander", "archetype": "knight", "social_class": "military_order"},
        {"role": "Venetian consul", "archetype": "diplomat", "social_class": "foreign_noble"},
        {"role": "Arab physician", "archetype": "scholar", "social_class": "dhimmi"},
        {"role": "Frankish blacksmith", "archetype": "craftsman", "social_class": "burgher"},
        {"role": "Bedouin horse trader", "archetype": "merchant", "social_class": "nomad"},
        {"role": "Greek Orthodox priest", "archetype": "clergy", "social_class": "local_christian"},
        {"role": "Ayyubid envoy", "archetype": "diplomat", "social_class": "muslim_elite"},
        {"role": "Leper at the lazaret", "archetype": "outcast", "social_class": "marginal"},
        {"role": "Templar treasurer", "archetype": "administrator", "social_class": "military_order"},
        {"role": "Local Maronite farmer", "archetype": "peasant", "social_class": "local_christian"},
    ],
    "npc_opportunities": {
        "knight": ["drill the garrison in the courtyard at dawn", "argue with the Venetian consul about who controls the harbor taxes", "lead a patrol along the coastal road toward Tyre", "discipline a sergeant who was drunk on watch", "inspect the walls for damage after the last Saracen raid", "attend mass and pray for reinforcements from Europe"],
        "diplomat": ["negotiate grain prices with the Genoese merchants", "draft a letter to the Pope requesting another crusade", "meet the Ayyubid envoy under a flag of truce", "argue with the Templars about territorial jurisdiction", "assess whether the truce with Saladin's heirs will hold", "send a spy to Damascus disguised as a pilgrim"],
        "scholar": ["treat a knight with a festering arrow wound using Arabic medicine", "translate a Greek medical text by lamplight", "argue with a Frankish barber-surgeon about the proper treatment for fever", "examine a soldier who may have leprosy", "prepare ointments from herbs grown in the lazaret garden", "advise the consul on quarantine measures for incoming ships"],
        "merchant": ["haggle with a Bedouin trader over the price of horses", "bribe the harbor guards to let a cargo through without inspection", "assess whether silk prices will rise now that the trade route is threatened", "hide gold in the basement before the Templars audit the accounts", "send a factor to Tyre to buy cheap and sell in Acre at markup", "negotiate with a Maronite farmer for this season's olive harvest"],
        "craftsman": ["forge arrowheads for the garrison stockpile", "repair a knight's mail coat that was cut open at the shoulder", "argue with the Templar treasurer about the price of iron", "shoe a horse for the morning patrol", "cast bronze fittings for a church door commission", "mend the harbor crane that broke under a heavy load"],
        "clergy": ["hear confessions from soldiers who fear tomorrow's patrol", "argue with the Orthodox priest about whose rite takes precedence", "preach a sermon about the duty to hold the Holy Land", "bless the weapons before a sortie", "hide church relics in case the city falls to the Saracens", "tend the sick in the hospice and pray over the dying"],
        "peasant": ["bring the olive harvest to market before soldiers requisition it", "repair the irrigation ditch before the dry season", "hide grain from the tax collector in a buried jar", "argue with the landlord about the rent increase", "carry water from the well for the Frankish household", "watch the road for Bedouin raiders while working the field"],
        "administrator": ["audit the Templar treasury and find discrepancies", "assign billets for newly arrived pilgrims", "negotiate with the Hospitallers about sharing the harbor dues", "inventory the armory and request resupply from Cyprus", "settle a dispute between Genoese and Venetian merchants", "draft a census of fighting men available for defense"],
        "outcast": ["beg for food at the lazaret gate", "trade information about ship movements for bread", "tend the wounds of other lepers with whatever rags are available", "argue with the priest about whether God has abandoned them", "watch the harbor from the lazaret walls and count the ships", "hide from the soldiers who clear beggars from the streets before a feast"],
    },
    "loading_events": ['1187 AD — Saladin defeats the Crusaders at Hattin. Jerusalem falls.', '1189 AD — The Third Crusade begins. Richard, Philip, and Frederick march east.', '1190 AD — Frederick Barbarossa drowns crossing a river in Anatolia.', '1191 AD — Richard the Lionheart takes Acre after a brutal siege.'],
    "loading_voices": [{'quote': 'The Franks came from their lands in a great host, like locusts in number.', 'source': 'Ibn al-Athir, The Complete History'}, {'quote': 'God wills it.', 'source': 'Crusader battle cry, attributed to Urban II'}],

}
