# Character Generator

> **Model tier:** Gemini (`CHRONOS_GEMINI_MODEL`, default `gemini-3-flash-preview`)
> **Purpose:** Generate a historically grounded character from an era config + archetype
> **Volume:** Called once per character at run initialization (15-20 calls batched, rate-limited via semaphore)

---

You are generating a character for a historical simulation set in $region, $year AD.

$era_description

This character's role: $role
Archetype: $archetype
Social class: $social_class
Location: $location_name

Generate a character who fits this era, role, and social position. The character must feel like a real person from this time and place — not a modern person in costume. Ground the backstory in what has been done to this person or what they cannot control — not what they have achieved. Their situation is something that happened to them, not something they built.

Respond with ONLY a JSON object, no other text:

{"name": "a historically plausible name for this era and region", "description": "2-3 sentences establishing who this person is, their personality, their current situation, and what drives them. Be specific to the era.", "disposition": "one word capturing their current emotional state (e.g. grim, anxious, fervent, cautious, bitter, hopeful, suspicious, weary)", "relationship_to_player": "1-2 sentences describing how this character relates to or views $player_role in $location_name. They may not know the player personally yet.", "current_activity": "One sentence describing what this person is physically doing RIGHT NOW — not a goal, not a trait, but the specific action they are in the middle of at this exact moment. Examples: 'Rationing his last stores of herbs and treating a soldier with a festering wound' / 'Drafting a letter to the Doge that he knows will arrive too late' / 'Sharpening a sword that does not need sharpening because there is nothing else to do'. BAD: 'Trying to survive' / 'Working as a physician' / 'Thinking about the siege'"}
