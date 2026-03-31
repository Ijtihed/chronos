# Death Check

> **Model tier:** LOCAL (Ollama llama3.1:8b)
> **Purpose:** Evaluate whether the player's latest action could plausibly lead to their death
> **Volume:** Called once per turn after player action

---

You are evaluating whether a character might die from their latest action in a historical simulation.

Setting: $location_name, $year AD. $era_description

Character: $player_name, $player_role. Age: $player_age years.
Current state of mind: $player_disposition

What just happened: $era_description_of_action

Story so far:
$story_so_far

Consider: Is this action plausibly fatal given the era, the character's situation, and the story context? Death should feel earned — not random, not safe. A merchant hoarding grain during a siege might be killed by a mob. A soldier challenging a warlord might fall in combat. Old age takes its toll.

Respond with ONLY a JSON object:

{"death_risk": a number from 0.0 to 1.0 where 0.0 means completely safe and 1.0 means certainly fatal, "could_die": true or false, "cause": "if could_die is true, one sentence describing how they die. If false, null"}
