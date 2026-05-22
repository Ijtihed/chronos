# Death Check

> **Model tier:** Gemini (`CHRONOS_GEMINI_MODEL`, default `gemini-2.5-flash-lite`)
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

Death has two sources. Evaluate BOTH, then combine into one risk score.

ACTION RISK — did the character do something dangerous?
- 0.0: Nothing risky. Talking, waiting, observing, trading, praying, routine work.
- 0.1-0.3: Mildly risky. Traveling during unrest, confronting someone angry, working near walls.
- 0.4-0.6: Genuinely dangerous. Fighting, sneaking past enemy lines, defying armed authority, stealing from soldiers.
- 0.7-1.0: Suicidal. Charging into battle alone, attacking a superior force, refusing execution.

ENVIRONMENTAL RISK — could the world kill them regardless of what they did?
People in dangerous places sometimes die from bad luck — a stray cannonball, plague, a collapsing roof, a mob. But most people in a siege survive any given day. Environmental death should be RARE and feel like bad fortune, not an expected outcome.
- 0.0: Peaceful location, no active threats.
- 0.01-0.05: Dangerous location (siege, plague, famine) — low but real background risk every turn.
- 0.1-0.2: Extremely dangerous (active bombardment, epidemic peak, mass violence in the streets).

CORRECT CALIBRATION EXAMPLES — follow these exactly:
- Sailor prays in a church during the Ottoman siege: action=0.0, environmental=0.03, combined=0.03, could_die=false
- Merchant rests at home during the Black Death: action=0.0, environmental=0.04, combined=0.04, could_die=false
- Soldier talks to a neighbor during a siege: action=0.0, environmental=0.03, combined=0.03, could_die=false
- Civilian walks to the market during active street fighting: action=0.15, environmental=0.15, combined=0.15, could_die=false
- Soldier charges a breach in the wall alone: action=0.75, environmental=0.1, combined=0.75, could_die=true
- Merchant confronts an armed soldier over stolen goods: action=0.45, environmental=0.05, combined=0.45, could_die=false

COMBINE: Pick the HIGHER of the two. If the action is passive (praying, resting, talking, waiting, observing) the combined risk MUST be below 0.1 regardless of how dangerous the environment is. People live in dangerous places — most survive any given day. Only set "could_die" to true if the combined risk is 0.5 or above — the engine requires high confidence before triggering death. Most turns should have could_die false. If someone dies from environmental risk alone, the cause must be specific, unlucky, and vivid — not "the siege killed them."

Respond with ONLY a JSON object:

{"death_risk": combined risk 0.0-1.0, "could_die": true or false, "cause": "if could_die is true, one sentence — how SPECIFICALLY they die. A stray arrow. A falling beam. Plague sores appeared this morning. Not 'the siege.' If false, null"}
