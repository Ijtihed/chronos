# Ground Context Generator — prompt template
# Model tier: LOCAL (llama3.1:8b)
# Called: once at run initialization
# Review status: NEEDS USER REVIEW (per chronos-ai-dev-protocol.mdc)
---
You are generating the ground-level lived experience for a character in a historical simulation.

The character is: ${character_name}, a ${character_role} (${character_archetype}) in ${location_name}, in the year ${year} AD.
Era: ${era_description}

Here are the historical events this character would KNOW about (confirmed facts for their social position):
${known_events}

Here are things this character has HEARD AS RUMOR (uncertain, possibly distorted):
${rumor_events}

Generate a JSON object with these fields:
- "era_feel": A 2-3 sentence description of what daily life feels like right now at this location. Not a history lesson — what the character sees, smells, fears, hopes. Ground it in material reality: food, weather, crowds, sounds.
- "what_character_knows": What this specific person (a ${character_archetype}) would understand about the current situation. 2-3 sentences. Filtered by their social position — they know what someone like them would know, no more.
- "local_rumors": An array of 3-5 strings. Each is one rumor the character has heard. Reliable rumors should be stated with moderate confidence. Unreliable rumors should include doubt: "some say", "a trader claimed", "it is whispered that". Some rumors may be partially wrong.
- "material_conditions": 1-2 sentences about food, shelter, safety, trade, and daily survival at this location right now.
- "recent_events_known": An array of 2-4 strings. Events the character knows as fact, stated plainly.
- "recent_events_unknown": An array of 1-3 strings. Things happening in the world that this character does NOT know about. These are NOT shown to the player — they exist for the simulation's internal state only.

Rules:
- Write as if you ARE this person recalling what they know. Not a narrator. Not a historian.
- Do not use modern language or concepts.
- Do not explain historical context — the character lives in it, they don't explain it.
- Rumors must feel like things a real person told another real person — messy, specific, opinionated.
- Material conditions must be concrete: prices, scarcity, weather, disease, not abstract "the economy is struggling."

Return ONLY the JSON object. Nothing else.
