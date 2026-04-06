# Simulation and world

## The world model

The world is maintained as two parallel representations:

**Structured state** — a machine-readable record of who is where, what has happened, what borders look like, what relationships exist between characters, and what the current political situation is. This is what the simulation runs on.

**Narrative layer** — a human-readable interpretation of that state. This is what the player sees. Every event has a narrative description. Every character has a voice. The world is always experienced as story, not as data.

Both layers are updated every turn. The structured state is the truth; the narrative layer is how that truth is expressed.

## The historical knowledge engine

The game is grounded in real historical context. It draws on a corpus of public domain texts — primary sources, chronicles, travelogues, academic writing — to inform how the world responds to player actions.

When something happens, the game asks: *given this era, this region, this social context, what would plausibly follow?* The answer is drawn from historical patterns, not scripted outcomes. This is what makes every run feel historically authentic even when the specific events are entirely invented.

The knowledge engine does not try to predict what actually happened in history. It predicts what *plausibly could* happen — consistent with the economic, social, and political logic of the time and place.

Source material: Project Gutenberg (public domain primary sources), Wikipedia (era/region/event summaries), open academic papers.

## The map

Historical maps exist as open data and are a core layer of the game. The physical world — coastlines, rivers, terrain — is static. The political world — borders, territories, cities — is seeded from real historical GIS data for the era, then diverges as the simulation runs and player actions change things.

The map is not decorative. It is the geography of information. Where you are determines what you can know.

### Region knowledge on the map

When the player selects a region on the map, the game generates what the character would plausibly know about that region. This is not an encyclopedia entry — it is the character's own understanding, filtered through who they are.

Knowledge has two tiers:

- **Known facts** — things the character would reasonably know given their archetype, social class, location, and era. A Genoese merchant in Acre knows the trade routes to Constantinople. A farmer outside Siena knows nothing about what lies beyond the next hill.
- **Rumors** — things the character has heard but cannot verify. A trader mentioned the Rus. A pilgrim said Jerusalem has fallen. A soldier claims the Emperor is dead. Rumors are presented as uncertain — the player sees them but knows they may not be true.

What a character knows about a region depends on:
- **Distance** — nearby regions are better known
- **Archetype and social class** — a scholar knows about distant civilizations from texts; a peasant does not
- **Trade and travel routes** — a merchant knows destinations their goods flow to
- **NPC conversations** — things other characters have told the player during the run
- **Common knowledge for the era** — everyone in 1453 Constantinople knows the Ottoman army is outside the walls

Region knowledge is generated on demand when the player selects a region, as the character "recalling" what they know. Results are cached per region per turn.

### Events on the map

Significant events — sieges, plagues, army movements, famines — appear on the map as visual markers at their location. These are **filtered by character awareness**: an event only appears on the map if the character has plausible knowledge of it. A siege 500 miles away does not show until someone tells the player about it (through NPC conversation or travel).

Events come from two sources:
- **The HCE Events DB** — canonical historical events that the character would be aware of given their position and social class
- **The world engine** — gameplay events (NPC autonomous actions, tension changes, player-caused consequences) promoted to map events when significant enough

This means the map is always a partial view. It shows the world as the character understands it, not as it actually is. The gap between what the map shows and what is actually happening is part of the game.

## Autonomous world systems

The world runs whether the player does anything or not. Three LLM-free systems operate every turn before NPC actions:

### Structural drift

Every turn, the world shifts structurally without any LLM calls:

- **Tension drift** — every 3 turns, a random location's tension escalates one step. Critical-tension locations have a 15% chance to spread tension to adjacent locations.
- **Disposition drift** — every 5 turns, each NPC's disposition drifts one step toward their archetype baseline. A soldier forced into "warming" toward an enemy gradually returns to "guarded." A refugee scared into "hostile" drifts back to "fearful."
- **Needs decay** — all NPC needs decay every turn at type-specific rates. Survival/safety decay fastest (3-5 per turn + tension bonus). Social/trade/duty decay at medium rate (2-4). Knowledge/power/faith decay slowest (1-2). Higher local tension accelerates survival/safety decay.
- **Rumor propagation** — every 3 turns, locations with high tension or recent events schedule rumors at adjacent locations 1-2 turns in the future.

### Probabilistic world events

Every turn, location-level and NPC-level rules fire independently:

- Armed skirmishes (30% at critical tension with soldiers present)
- Civilian unrest (20% at high tension without soldiers)
- Tension spreading to neighbors (15% from critical locations)
- Food shortage rumors (25% where famine events exist)
- Trade route disruption (40% during sieges, delayed 2 turns)
- Merchant attraction (20% at peaceful locations)
- Refugee flight (50% for refugee-archetype NPCs in high-tension locations, toward lowest-tension neighbor)

### Disposition chain

NPCs have 13 possible dispositions in a coherent chain: hostile → fearful → wary → grim → guarded → suspicious → cautious → neutral → reserved → formal → engaged → fervent → commanding → warming. Shifts move one step at a time. Each archetype has a baseline disposition they drift toward over time.

## Run initialization

Each run seeds from a randomly selected historical era (post 0 AD). The game generates:

- A player character with an archetype appropriate to that era and a short backstory
- A starting region with 8-15 characters, their archetypes, locations, and relationships
- A political situation drawn from the real historical context of that era
- A map layer based on real historical borders for that period

The player is given their backstory and their immediate surroundings. Nothing else. They figure out the rest.

## Family

Family members — spouse, children, heirs — are named NPCs with their own archetypes, locations, and memory of the player. They are POV characters like any other and must be physically visited to hear their perspective. They are not given to the player as information; the player has to find them.

Family members hold memory of the player longer than strangers after death, meaning they are typically among the last NPCs to forget the player during the observation/erasure phase. Children do not persist beyond the run they are born in. There is no cross-run family lineage.

## Difficulty

Difficulty in CHRONOS is structural, not mechanical. It is never achieved by degrading AI output quality or making the interface harder to use. The following levers are the agreed design space for difficulty:

- **Memory decay rate** — faster decay means the player's observation window after death is shorter and erasure comes sooner
- **Information opacity** — on harder settings NPC perspectives are more biased, rumor-filtered, and culturally specific, making the world harder to read
- **Autonomy weight on inaction** — on harder settings the character takes riskier autonomous actions when the player skips turns
- **Era volatility** — some historical periods are structurally more dangerous and chaotic than others; era selection is itself a difficulty axis
- **Character assignment tier** — being assigned someone with less social power means a structurally smaller action space regardless of player intent

The goal of difficulty is to change how much the world cares that the player exists, not to make the systems feel broken.

## Era coverage

The game covers all of post-0 AD history, including the modern period. Eras are not limited to the ancient or medieval world. The 1800s, 1900s, and 2000s are valid settings — a run could place you as a factory worker in Victorian Manchester, a soldier in the trenches of WWI, a dissident in Cold War Prague, or a shopkeeper in 1990s Mogadishu.

The simulation mechanics are identical regardless of era. What changes is the world context, the archetypes, the technology available, and the scale of events the player can influence. A 2003 Baghdad run uses the same turn loop as a 410 AD Italia run — the world simulates, NPCs act, the player observes and sometimes intervenes.

Current starter set (Phase 1): Roman Late Empire (~410), Viking Age (~870), Crusader States (~1190), Black Death (~1348), Fall of Constantinople (~1453). Modern eras (1800s, 1900s, 2000s) are planned for expansion. Border data for post-1886 eras uses CShapes 2.0 (see `frontend/geo/sources.md`).

## What makes each run unique

- The era is random
- The player character is random within that era
- The NPCs and their relationships are generated fresh
- The player's decisions diverge from real history immediately, creating a world that is historically grounded but never historically determined
- The memory decay rate, the characters who survive, the way the world interprets your actions — all of it compounds into something that will never repeat
