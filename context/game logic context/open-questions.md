# Open questions

> Unresolved design decisions. **Do not assume** these when building. When one is resolved in chat, mark it closed here and record the decision in the relevant context file before implementing.

## General (not yet tied to a roadmap phase gate)

- Does multiplayer ever make sense? (Multiple players assigned different characters in the same world, experiencing the same events from different sides)
- Is there any meta-progression across runs? (Does anything carry over, or is each run truly isolated?)
- **Terrain view (Phase 2.5 or 3):** A tilted 3D relief/war-table view of the era's region. Cut from Phase 2. Decide when to add.
- **Perspective switching:** The ability to switch which character you're observing the simulation through — same world, different lens. Architecturally supported by the simulation-first design. Not currently scoped to any phase.

## Roadmap-blocking — resolve before the phase listed

Per [roadmap.md](roadmap.md) **OPEN QUESTIONS THAT AFFECT THE ROADMAP**:

| Topic | Resolve before |
|--------|----------------|
| **UI metaphor** for the text interface (Journal? Dispatch? Stream of consciousness?) | **Phase 1** UI work |
| **Diffusion model provider** (local vs API, stack choice) | **Phase 3** kickoff |
| **Session length target** (short vs multi-day runs) | **Phase 5** pacing |
| **NPC relationship graph granularity** (NPC–NPC ties, indirect influence) | **Phase 5** scope |

Bullets for tracking resolution in prose (move to “Closed” subsection below when done):

- [x] UI metaphor for the text interface
- [ ] Diffusion model provider and hosting (local / API)
- [ ] Session length target
- [ ] NPC relationship graph granularity

## Observations from Phase 0 (not blocking, but worth tracking)

- **NPC response length compliance:** The `llama3.1:8b` model frequently exceeds the "2-4 sentences" constraint in the NPC POV prompt. May need stronger enforcement (e.g. `max_tokens`, structured output, or prompt rewording) if this persists in Phase 1.
- **Disposition shift granularity:** Phase 0 uses a fixed ladder (`grim → cautious → warming`, etc.) driven by LLM-judged sentiment. Phase 1's richer NPC relationships may need continuous values or multi-dimensional disposition (trust, fear, respect) rather than a single label.

## Closed

- [x] **Phase 0 era selection** — Roman Late Empire, ~410 AD (Ariminum). Chosen for richest Project Gutenberg coverage. (2026-03-31)
- [x] **Phase 0 model tier for action parser** — Local Ollama (`llama3.1:8b`) as frontier stub. Frontier swap point labeled in code; will enable when/if local parsing proves insufficient. (2026-03-31)
- [x] **UI metaphor** — Present-tense stream. The world advances, pauses at decision points (game-initiated or player-initiated). No journal/dispatch framing. (2026-03-31)
- [x] **Death mechanism** — Hybrid aging + consequence. Turns advance the calendar; the player ages toward a lifespan ceiling. Risky actions can kill early. Both paths must feel narratively earned. (2026-03-31)
- [x] **Phase 1 starter eras** — Roman Late Empire (~410), Viking Age (~870), Crusader States (~1190), Black Death (~1348), Fall of Constantinople (~1453). (2026-03-31)
- [x] **Player agency model** — Total freedom, no suggested actions, no menus, no hand-holding. Player types any decision at any scale. The game never tells the player what to do. (2026-03-31)
- [x] **Decision scale** — Macro-level. Big life choices: alliances, betrayals, fleeing, revolting, sacrificing wealth. Not bar conversations or item pickups. Turns represent weeks/months/years. (2026-03-31)
- [x] **NPC reaction filtering** — The game decides whose perspective matters per action. Not every NPC reacts to everything. Only characters genuinely affected by the action respond. (2026-03-31)
- [x] **Ruler/king mechanics** — Rulers are mechanically identical to other characters. The action space is larger because the character has more real-world power (a king can declare war, a merchant cannot), not because the game grants special mechanics. Same input, same interpretation, same travel-to-understand loop. (2026-04-01)
- [x] **Character assignment distribution** — Reflects realistic era demographics with a small persistent bias toward historically significant figures including rulers. Not earned or unlocked. (2026-04-01)
- [x] **Family as NPCs** — Family members are named NPCs with their own archetypes, locations, and memory. They hold memory longer after death. No cross-run lineage. (2026-04-01)
- [x] **Difficulty model** — Structural, not mechanical. Levers: memory decay rate, information opacity, autonomy weight, era volatility, character assignment tier. Never degrades AI quality or interface usability. (2026-04-01)
- [x] **Map region knowledge** — Click/hover a region shows what the character knows (facts) and has heard (rumors), filtered by archetype, social class, distance, and NPC conversations. Generated on demand per region. Not an encyclopedia — it's the character's worldview. (2026-04-01)
- [x] **Map event visualization** — Events (sieges, plagues, armies) appear on the map only if the character has plausible awareness. No god-view. Sources: HCE Events DB (canonical) + world engine (gameplay). The map is always a partial view. (2026-04-01)
- [x] **Word definitions overlay** — Highlighting any word in the narrative shows a dictionary definition as a small overlay. Dictionary API, not LLM. Instant, no click required, disappears on deselect. Reading aid for era-specific language, not a game mechanic. (2026-04-01)
- [x] **NPC autonomy model** — NPCs are autonomous subagents, not reactive. They act every turn, travel between locations, interact with each other, pursue their own goals grounded in historical context. The world happens whether or not the player does anything. (2026-04-01)
- [x] **Player as perspective, not protagonist** — The narrative is always from the player character's subjective perspective. The simulation doesn't revolve around the player. Sometimes nobody cares what you did. The player is a lens into the simulation, not its center. (2026-04-01)
- [x] **NPC perception on hover** — Focusing on an NPC shows the player character's subjective impression of them, colored by interactions, archetype, and biases. Not a stat sheet. (2026-04-01)
- [x] **Ambient world activity** — Every turn, NPCs act as background. The player witnesses activity at their location. The narrative is dominated by what is happening in the world, not by the player's action alone. (2026-04-01)
- [x] **Time acceleration** — The player can speed up time passage, letting the simulation run forward. Reinforces that this is a simulation observed, not a story directed. (2026-04-01)
