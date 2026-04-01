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

## Run initialization

Each run seeds from a randomly selected historical era (post 0 AD). The game generates:

- A player character with an archetype appropriate to that era and a short backstory
- A starting region with 15–30 characters, their archetypes, locations, and relationships
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

## What makes each run unique

- The era is random
- The player character is random within that era
- The NPCs and their relationships are generated fresh
- The player's decisions diverge from real history immediately, creating a world that is historically grounded but never historically determined
- The memory decay rate, the characters who survive, the way the world interprets your actions — all of it compounds into something that will never repeat
