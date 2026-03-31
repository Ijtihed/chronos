# Character Generator

> **Model tier:** LOCAL (Ollama llama3.1:8b)
> **Purpose:** Generate a historically grounded character from an era config + archetype
> **Volume:** Called once per character at run initialization (15-20 calls batched)

---

You are generating a character for a historical simulation set in $region, $year AD.

$era_description

This character's role: $role
Archetype: $archetype
Social class: $social_class
Location: $location_name

Generate a character who fits this era, role, and social position. The character must feel like a real person from this time and place — not a modern person in costume.

Respond with ONLY a JSON object, no other text:

{"name": "a historically plausible name for this era and region", "description": "2-3 sentences establishing who this person is, their personality, their current situation, and what drives them. Be specific to the era.", "disposition": "one word capturing their current emotional state (e.g. grim, anxious, fervent, cautious, bitter, hopeful, suspicious, weary)", "relationship_to_player": "1-2 sentences describing how this character relates to or views $player_role in $location_name. They may not know the player personally yet."}
