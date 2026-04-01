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

Every turn, the world moves forward. NPCs act autonomously — they pursue their own goals, react to events around them, travel between locations, interact with each other. This happens continuously as background activity. The player witnesses what unfolds at their location.

The player types one decision in natural language. The simulation interprets it. The consequences ripple outward — but the player's action is one thread among many. The narrative is dominated by what is happening in the world, not by the player's action in isolation.

**Sometimes nobody cares.** If the player does something minor in a place where nothing is at stake, the world may not react at all. A grain deal in a peaceful town produces no drama. The same deal during a siege changes lives.

**Inaction is a valid decision.** If the player types something like "wait" or "do nothing" or speeds up time, the character acts autonomously based on their archetype, backstory, and current situation. The world does not pause. Time passes regardless. Events unfold.

**Anachronistic language is silently interpreted.** If a player uses modern phrasing — "broker a deal," "go viral," "DM the general" — the game translates this into era-appropriate action without correcting or breaking immersion. The intent is preserved; the language is adapted.

## NPC autonomy

NPCs are not reactive to the player. They are autonomous agents living their own simulated lives. Every turn:

- NPCs at the player's location act in the background — the player witnesses their activity as ambient narrative
- NPCs elsewhere make their own decisions based on their archetype, goals, and the current state of the world
- NPCs travel between locations on their own, following trade routes, military orders, religious pilgrimages, or flight from danger
- NPCs interact with each other — alliances form, conflicts emerge, trust builds or breaks — independently of the player

NPC behavior is grounded in historical context. A centurion follows military logic. A merchant follows trade logic. A refugee follows survival logic. Their decisions are what would most plausibly happen given who they are, where they are, and what's happening around them.

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
