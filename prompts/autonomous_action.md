# Autonomous Action

> **Model tier:** LOCAL (Ollama llama3.1:8b)
> **Purpose:** Generate what a character does when the player skips a turn, or what NPCs do during world advancement ticks
> **Volume:** Called per-NPC per advancement tick — must be lightweight

---

You are deciding what $character_name does next. They are $character_role in $location_name, $year AD.

$era_description

Their personality: $character_description
Their current state of mind: $character_disposition

What has been happening:
$story_so_far

Based on their personality, role, and the current situation, what does $character_name do this turn? They act according to their nature — a soldier patrols or drills, a merchant trades or hoards, a priest prays or tends the flock, a refugee seeks shelter.

Respond with ONLY a JSON object:

{"action": "one sentence describing what they do", "effect": "one sentence describing the immediate consequence"}
