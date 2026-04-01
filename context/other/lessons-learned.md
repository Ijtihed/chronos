# Lessons Learned

> What went wrong and why, so we don't repeat it. This is not a changelog — it documents structural mistakes in thinking, not bugs.

---

## Phase 0–2: Player-centric architecture (wrong)

### What happened

The first three phases were built around a player-centric model: the player acts, the world reacts, NPCs comment on what the player did. The entire turn loop was structured as:

1. Player types action
2. Action is parsed
3. World state mutates based on the action
4. NPCs at the player's location generate POV reactions to the action
5. Response is returned

This produced a game that felt like a text adventure. The player was the protagonist. NPCs were reactive — they only spoke when the player did something, and only about what the player did. The world was inert between player actions.

### What was wrong

The design intent (documented in overview.md and gameplay.md from the start) was always that NPCs have their own lives and the player experiences the world through their perspectives. But the code architecture contradicted this:

- **NPCs only acted during travel ticks** — the world engine ran NPC autonomous actions during time advancement (travel), but not during regular turns. When the player was at a location, NPCs were frozen until the player did something.
- **The turn response centered on the player** — the API returned `parsed_action` (what the player did) as the primary data, with `npc_responses` as secondary reactions. The UI rendered the player's action first, NPC voices second. This framing made the player the center.
- **NPC relevance filtering was too aggressive** — the `relevant: true/false` flag on npc_impacts meant usually only 1 NPC spoke per turn. Combined with the player-centric framing, this made the game feel like talking to one person.
- **No ambient activity** — there was no mechanism for NPCs to do things in the player's presence that weren't reactions to the player. No NPC-on-NPC interactions. No background events. The world was silent unless you poked it.
- **NPCs were static** — they didn't move between locations, didn't change goals, didn't interact with each other. They were generated at run start and then sat at their assigned location waiting for the player to visit.

### What the design actually requires

The game is a **simulation observed through a perspective**. The architecture should be:

1. The world advances (NPCs act, events unfold, things happen everywhere)
2. The player witnesses what's happening at their location (ambient activity)
3. The player optionally acts (their action is one thread among many)
4. The world responds to everything — the player's action is not privileged over NPC actions
5. The narrative is dominated by world activity, not player activity

NPCs are autonomous subagents. They travel, make decisions, interact with each other, and have their own arcs. The player is a camera that sometimes intervenes.

### What needs to change

- The world engine must run every turn, not just during travel
- The turn response must include ambient NPC activity alongside (or instead of) reactions to the player
- NPCs must be able to move between locations autonomously
- NPC-on-NPC interactions must be visible when the player is present
- The narrative framing must foreground the world, not the player
- The relevance filter needs tuning — more NPCs should be active, not fewer
- NPC perception on hover must exist (character's subjective impression)

### Root cause

The mistake was building code that matched a traditional game loop (player acts → world reacts) instead of code that matched the design (world simulates → player observes and sometimes acts). The design documents said the right things from the start, but the implementation defaulted to the familiar pattern.

**Lesson: when the design says "the world is the story and the player is just in it," the turn loop must start with the world, not with the player.**
