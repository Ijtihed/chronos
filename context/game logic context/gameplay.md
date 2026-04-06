# Gameplay

## Player agency

The player has **total freedom**. There is no action menu, no suggested moves, no list of options. The game never tells the player what to do. The player types whatever they decide — any action, any scale, any ambition — and the simulation interprets it.

This means the player can:

- Negotiate alliances with foreign powers
- Abandon their city and flee south
- Hoard grain and manipulate the economy
- Start a revolt
- Do nothing and let events overtake them
- Speed up the passage of time and watch the world unfold
- Anything else they can articulate

The game does not constrain the vocabulary or scope of player decisions. It interprets freely and responds with consequences — or with silence, if nobody cares.

## Decision scale

Decisions are **macro** — big life choices that shape the trajectory of a character and the world around them. This is not a game about talking to a bartender or picking up items. It is a game about deciding whether to betray an ally, flee a siege, align with an invading army, or sacrifice your wealth to feed refugees.

The simulation operates at the level of weeks, months, and years. Each turn represents meaningful elapsed time. The player's choices should match that scale — strategic, consequential, irreversible.

## How a turn works

Every turn runs a 7-stage autonomous pipeline:

1. **Structural drift** (no LLM) — tension escalates and spreads between locations, NPC dispositions drift toward archetype baselines, NPC needs decay, rumors propagate from high-tension locations to neighbors.
2. **Scheduled consequences** (no LLM) — delayed effects from past actions fire. A betrayal on turn 5 might spread as a rumor on turn 7, shift NPC dispositions on turn 9, and increase tension on turn 12. Invalid consequences (target died, world diverged) are cancelled.
3. **World events** (no LLM, probabilistic) — skirmishes erupt at high-tension locations with soldiers, civilian unrest breaks out where there are no soldiers, tension spreads to neighbors, trade routes are cut during sieges, refugees flee to safer locations, peaceful towns attract merchants.
4. **NPC autonomous actions** (LLM) — every NPC acts every turn. NPCs at the player's location get a full LLM call with rich context. All other NPCs get a lighter LLM call with their dominant need and local tension. The world is always alive everywhere. The utility scoring system picks what each NPC does based on their inner needs; the LLM narrates how they do it.
5. **Player input** (optional) — if the player typed something, it is parsed, applied, and consequences scheduled. If not, this stage is skipped.
6. **Narrative assembly** — what the player sees is composed from ambient NPC activity + world events + player action consequences.
7. **Persistence** — state saved to SQLite.

Stages 1-4 run whether or not the player does anything. The player's input is one optional slice.

**Sometimes nobody cares.** If the player does something minor in a place where nothing is at stake, the world may not react at all. A grain deal in a peaceful town produces no drama. The same deal during a siege changes lives.

**Inaction is a valid decision.** If the player types something like "wait" or "do nothing" or speeds up time, the character acts autonomously based on their archetype, personality, and current needs. The world does not pause. Time passes regardless. Events unfold.

**Time acceleration.** The player can skip 1-30 turns at once (`POST /api/run/{id}/skip`). The pipeline runs stages 1-4 for each skipped turn. After all ticks complete, a re-grounding passage describes where the player is, who is nearby, and the current year. No recap of what happened — that information must be gathered by traveling and talking to NPCs.

**Anachronistic language is silently interpreted.** If a player uses modern phrasing — "broker a deal," "go viral," "DM the general" — the game translates this into era-appropriate action without correcting or breaking immersion. The intent is preserved; the language is adapted.

## Consequence queue

Significant actions schedule delayed effects that fire on future turns. This gives the world momentum — past decisions haunt the present. Effect types: tension shifts, rumors, trade disruptions, NPC arrivals, event spawns, material changes, disposition shifts, and need pressure.

Consequences are validated when they fire, not just when they're scheduled. If the world has diverged (the target NPC died, the location was destroyed, the player changed history), obsolete consequences are cancelled. The queue is cleaned up each turn.

## NPC autonomy

NPCs are not reactive to the player. They are autonomous agents with inner lives. Every NPC has:

**Personality traits** — five core traits (ambition, compassion, courage, piety, pragmatism) rolled randomly within archetype-specific ranges at creation. No two soldiers are identical. A high-compassion soldier behaves differently from a high-ambition one.

**Inner needs** — 17 need types (survival, safety, family, social, trade, profit, power, reputation, honor, duty, loyalty, faith, knowledge, order, community, harvest, stability) calculated from archetype + personality traits. Needs decay every turn. When a need drops below 30 it becomes urgent; below 15 it becomes critical and overrides all other behavior.

**Need-driven decisions** — the world advertises opportunities at each location (trade caravan, siege threat, food shortage, peaceful conditions, etc.). Each NPC scores these against their depleted needs using Maslow-style urgency curves — survival needs spike exponentially when critical. The NPC picks from the top-3 scoring options with weighted random selection (deliberate imperfection). The LLM's job is to narrate this decision, not to make it.

**Event-driven shifts** — witnessing death spikes survival needs. Betrayal permanently lowers loyalty. Prolonged hunger permanently increases pragmatism and decreases compassion. These shifts are logged in the NPC's needs history.

Every turn:

- Every NPC in the game gets an LLM call — the world is alive everywhere, not just at the player's location
- NPCs at the player's location get a full LLM call with rich context — the player witnesses their activity as ambient narrative
- NPCs elsewhere get a lighter LLM call with their dominant need and local tension — they still act genuinely
- NPCs travel between locations on their own, following trade routes, military orders, religious pilgrimages, or flight from danger
- NPCs interact with each other — alliances form, conflicts emerge, trust builds or breaks — independently of the player
- When multiple NPCs target the same entity, archetype-priority conflict resolution determines who proceeds

NPC behavior is grounded in historical context and driven by their inner state. A centurion with critical duty needs defends the walls. A merchant with critical survival needs abandons trade and flees. A refugee with depleted safety automatically moves toward lower-tension locations. Their decisions are what would most plausibly happen given who they are, what they need, and what's happening around them.

The player may influence NPCs through their actions, but NPCs are not waiting for the player to do something. They have their own lives.

## Voice and tone

NPCs speak like real people, not like characters in a historical novel. A soldier curses. A merchant complains about money. A priest moralizes but is still a flawed human. A refugee is scared and blunt. Nobody speaks in flowery prose or epic narration.

The language adapts to the era and character naturally — a Roman centurion doesn't use modern slang, and a 1990s shopkeeper doesn't speak in verse — but the register is always **conversational and human**. Swearing, crude language, and emotional bluntness are appropriate when they fit the character. The goal is two normal people talking, not a dramatic reading.

This applies to all NPC output: POV reactions, autonomous activity narration, and perception text.

## NPC perception

When the player focuses on an NPC (hovering on the map or encountering them in the narrative), they see their character's **subjective impression** of that person. This is not a stat sheet. It is what the player character thinks and feels about them, colored by:

- Previous interactions
- The character's own archetype and biases
- What others have said about this NPC
- The character's social class and worldview

A soldier sees the deacon differently than a merchant does. The same NPC produces different impressions depending on who is looking.

## Word definitions

When the player highlights any word in the narrative, a small overlay shows the dictionary definition. This is not a game mechanic — it is a reading aid. The narrative uses era-specific language, titles, place names, political terms, and cultural concepts that a modern player may not recognize. The overlay makes the world legible without breaking immersion or cluttering the UI.

The definition comes from a dictionary API (not LLM), instant response. It appears on highlight and disappears when the selection clears.

## The information system

There is no UI that tells the player what is happening in the world. No map annotations, no event log, no diplomatic screen, no suggested actions.

The only source of information is **other characters**. Significant events generate perspectives from the characters who were touched by them — but those perspectives are locked behind geography. You have to travel to a character to hear how they interpreted what you did.

This means:

- Information has location. A farmer in the next village doesn't know what a court official in the capital knows.
- Characters have incomplete, biased, rumor-filtered perspectives. They don't have perfect information either.
- The player is always operating with partial knowledge, just like a real person in history would be.

This is not a frustration mechanic — it is the core of the game. Seeking out perspectives is how you play.

## Travel

Travel is itself a decision and costs turns. Moving between locations means time passes, which means the world keeps moving without you. There is an inherent tradeoff between staying and acting locally versus traveling to gather information or reach new characters.

The player decides where to go in natural language. The game resolves travel time and what changes in the world while the player is in transit. NPCs who have traveled may no longer be where you left them.

## Factions

There is no explicit faction system. Factions emerge from character relationships — who trusts whom, who is loyal to whom, who shares interests. If enough characters in a region are aligned around a common interest, that becomes a de facto faction. But it is never labeled or formalized by the game. The player has to infer it from the perspectives they collect.

## The death mechanic

When the player dies, the run does not end. The world keeps going.

The player enters an observation mode. They can still travel between locations but cannot act or influence anything. They watch the world they shaped continue without them.

The run ends when the last character who remembers the player forgets them — or dies. Memory fades over time. Characters who interacted with the player more recently, or who were more deeply affected, hold on longer. Eventually, even they move on. When that last memory is gone, the player is truly erased from history. That is the end of the run.

This mechanic is thematically central. The game is about people history forgot. The ending makes you feel what that means.

## Future: perspective switching

The simulation is a single coherent world. The player character is one lens into it. In the future, the same simulation could be experienced through different characters' perspectives — the same events, different understanding. This is not a current feature, but the architecture should support it. The simulation is the truth. The perspective is the filter.
