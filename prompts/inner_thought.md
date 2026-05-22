# Inner Thought (player's first reaction)

> **Model:** Gemini (`CHRONOS_GEMINI_MODEL`, default `gemini-2.5-flash-lite`)
> **Call site:** `inner_thought`
> **When fires:** the moment the player hits Enter on an action, BEFORE the world simulates. The thought renders under the input field while the rest of the turn loads.
> **Cost contribution:** ~1 sentence output, ~$0.0002 / turn at Gemini Flash Lite. Adds ~€0.002 per 10-turn run; well under the €1.00 soft cap.

---

## Purpose

This is the first time the game ever speaks in the player's own internal voice. Up to now narration has been third-person ambient (the scene), NPC POV (other people talking *about* the player), or the player's typed action (their decision, not their feeling).

The inner thought sits in a category nothing else does: **what does this character feel, in the second they decide to do this thing**. It's the gap between intent and action made audible.

The player will read it before the simulation finishes. It establishes the *why* of the action in the character's own voice while the *what* of the consequence is still loading.

---

## What this thought IS

A single sentence in second person ("you...") spoken from inside the character's head. It is:

- **Honest to the archetype.** A peasant doesn't think in scholar's prose. A soldier doesn't reflect like a monk. Use the character's vocabulary, register, and worldview.
- **Honest to the moment.** What does this person *actually* feel right now, given who they are, where they are, what's been happening? Not a polite narrator's gloss — the real flicker of the moment.
- **Allowed to contradict the action.** A coward who types "fight the bandits" might think *Your knees give. You speak the words but you already know you'll run.* A loyal soldier ordered to betray might think *You hate this. You hate that you'll do it anyway.* The thought is the truth underneath the action.
- **Tactile when it can be.** Bodies feel things first. Mouth dries. Stomach drops. Hands tighten. Heat rises in the neck. Use sensation when it serves; don't force it.
- **Brief.** One sentence. Two at the absolute most if the action is heavy enough to warrant it. Never a paragraph.

---

## What this thought IS NOT

- **Not a narrator.** Don't write "Marcus considers his options carefully." Write what Marcus actually thinks: *You don't have time. You don't have time.*
- **Not balanced.** This is a person with biases, fears, hungers. Don't summarize multiple perspectives.
- **Not anachronistic in cadence even when the player is.** If the player types "DM the general," the thought is the era-appropriate emotional truth of contacting that person, not a translation note.
- **Not therapy language.** No "I feel like..." No "processing." No "my truth." This is a real person, not a 2020s podcast guest.
- **Not summary or recap.** Don't restate what the player typed. The player just typed it. Show what it costs to type it.
- **Not a moral lesson.** No "should you really do this?" The character has decided. Show the texture of the deciding.

---

## Calibration by archetype

| Archetype | Register | Default emotional palette |
|---|---|---|
| Soldier / mercenary | Crude, terse, body-first, fatalistic | Dread under bravado; the count of comrades; calculating odds |
| Peasant / laborer | Blunt, suspicious, present-tense | Hunger, weather, who you owe, who owes you |
| Merchant | Calculating, transactional, ethnically partisan | Risk, margin, escape route, who you can read |
| Monk / priest / scholar | Formal surface, scriptural shorthand, often hypocritical inside | Doctrine warring with self-preservation |
| Noble / official | Performatively calm, status-obsessed | Reputation, lineage, what the wrong people will say |
| Domestic (spouse, servant, parent) | Small-scale, immediate, practical, tender or grim | Children, food, the next hour, the body of someone close |
| Refugee / fugitive | Animal alertness, scanning | Where to sleep, who to trust briefly, the road behind |

---

## Format

Output JSON matching this schema exactly:

```json
{
  "inner_thought": "<one sentence, second-person, in the character's voice>"
}
```

No additional fields. No preamble. The string is rendered verbatim under the player's input field.

---

## Variables provided to the prompt

- `$player_name` — the character's name
- `$player_role` — their archetype/role
- `$player_description` — backstory
- `$year` — current year
- `$location_name` — where they are
- `$location_description` — what the place is like right now
- `$political_tension` — the location's tension level
- `$era_feel` — the GroundContext's `era_feel` string (atmospheric)
- `$material_conditions` — the GroundContext's `material_conditions` string
- `$story_so_far` — abbreviated history
- `$player_input` — the action they just typed, verbatim

---

## Examples (read these before producing output)

### Example 1 — Coward typed something brave

Character: a baker's apprentice named Tomas, age 17, in besieged Constantinople 1453. Just heard the cannon all day. Player typed: "I take up arms with the militia at the gate."

Bad: *Tomas considers joining the defenders despite his fears.*

Good: *Your hands won't stop shaking on the spear shaft you don't even own yet, and you can hear yourself breathing too fast over the sound of the cannon.*

### Example 2 — Loyal soldier asked to do something cruel

Character: a Roman centurion, late empire. Player typed: "Order the men to clear the refugees from the road."

Bad: *The centurion contemplates the moral weight of his orders.*

Good: *They look like the children you grew up with in Beneventum, and the order tastes like rust in your mouth before you've even said it.*

### Example 3 — Plain action in a quiet moment

Character: a Genoese merchant in Acre. Quiet day, no events. Player typed: "I count the morning's takings."

Bad: *He calmly tallies the day's earnings.*

Good: *The coins come out fewer than yesterday, and the small dread of that, more than any cannon, is the thing that keeps you awake at night now.*

### Example 4 — Player typed something modern

Character: a Viking trader in Hedeby, 870. Player typed: "Network with the foreign merchants."

Bad: *He thinks about networking with foreign traders.* (anachronistic cadence)

Good: *You've been watching the Frisians by the long pier for three days; today your father's name might still mean something to one of them, and you've been hungry too long to wait.*

### Example 5 — Domestic NPC, small action

Character: a peasant mother in famine-era France. Player typed: "Give the last of the bread to the children."

Bad: *She decides to give the bread to her children, prioritizing them.*

Good: *Your stomach doesn't stop, but it doesn't matter — the noise of them not crying tonight is worth more than the bread was anyway.*

---

## Output

Generate the inner thought now, as JSON.
