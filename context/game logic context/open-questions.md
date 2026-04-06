# Open questions

> Unresolved design decisions. **Do not assume** these when building. When one is resolved in chat, mark it closed here and record the decision in the relevant context file before implementing.

## General (not yet tied to a roadmap phase gate)

- Does multiplayer ever make sense? (Multiple players assigned different characters in the same world, experiencing the same events from different sides)
- Is there any meta-progression across runs? (Does anything carry over, or is each run truly isolated?)
- **Terrain view:** A tilted 3D relief/war-table view of the era's region. Cut from Phase 2. Decide when to add — could be a standalone enhancement or bundled with a future phase.
- **Perspective switching:** The ability to switch which character you're observing the simulation through — same world, different lens. Architecturally supported by the simulation-first design. Not currently scoped to any phase.

## Roadmap-blocking — resolve before the phase listed

| Topic | Resolve before |
|--------|----------------|
| **Diffusion model provider** (local vs API, stack choice) | **Phase 3** kickoff |
| **Session length target** (short vs multi-day runs) | **Phase 5** pacing |
| **NPC relationship graph granularity** (NPC-NPC ties, indirect influence) | **Phase 5** scope |

Tracking:

- [ ] Diffusion model provider and hosting (local / API)
- [ ] Session length target
- [ ] NPC relationship graph granularity

## Observations (not blocking, worth tracking)

- **NPC response length compliance:** The `llama3.1:8b` model frequently exceeds the "2-4 sentences" constraint. May need `max_tokens` or prompt rewording.
- **Ambient activity volume:** The simulation-first rebuild generates 2-4 NPC actions per turn at the player's location. This may need tuning — too few feels dead, too many feels noisy.
- **Loading screen generation time:** Character generation via Ollama takes 1-2 minutes. The two-step loading flow (preview instant, characters in background) mitigates this but the wait is still long.
- **Turn latency with all-NPC LLM calls:** Every NPC now gets an LLM call every turn (full for nearby, light for offscreen). With 12 NPCs this means 12 concurrent Ollama calls per turn. Latency depends on `OLLAMA_NUM_PARALLEL` setting and available VRAM. May need to swap Ollama for vLLM/SGLang if turns take >15s.
- **Utility scoring opportunity set:** The 10 hardcoded world opportunities (trade_caravan_passing, siege_threat, etc.) may need era-specific variants. A 1990s run shouldn't advertise "siege_threat" in the same way as a medieval one.
- **Consequence queue growth during time-skip:** Skipping 30 turns generates rumor consequences every 3 turns at high-tension locations. Queue cleanup runs each turn but the event list grows linearly. May need event list pruning for very long runs.
- **Frontend skip button:** The `/api/run/{id}/skip` endpoint exists but the frontend has no UI for it. Needs a time-advance button or keyboard shortcut.

## Closed

- [x] **Phase 0 era selection** — Roman Late Empire, ~410 AD (Ariminum). Chosen for richest Project Gutenberg coverage. (2026-03-31)
- [x] **Phase 0 model tier for action parser** — Local Ollama (`llama3.1:8b`) as frontier stub. Frontier swap point labeled in code. (2026-03-31)
- [x] **UI metaphor** — Present-tense stream. The world advances, pauses at decision points. No journal/dispatch framing. (2026-03-31)
- [x] **Death mechanism** — Hybrid aging + consequence. Turns advance the calendar. Risky actions can kill early. Both paths must feel narratively earned. (2026-03-31)
- [x] **Phase 1 starter eras** — Roman Late Empire (~410), Viking Age (~870), Crusader States (~1190), Black Death (~1348), Fall of Constantinople (~1453). (2026-03-31)
- [x] **Player agency model** — Total freedom, no suggested actions, no menus, no hand-holding. Player types any decision at any scale. The game never tells the player what to do. (2026-03-31)
- [x] **Decision scale** — Macro-level. Big life choices. Turns represent weeks/months/years. (2026-03-31)
- [x] **NPC reaction filtering** — The game decides whose perspective matters per action. Not every NPC reacts to everything. Only characters genuinely affected respond. (2026-03-31)
- [x] **Ruler/king mechanics** — Rulers are mechanically identical to other characters. Action space is larger because of real-world power, not special game mechanics. (2026-04-01)
- [x] **Character assignment distribution** — Reflects realistic era demographics with a small persistent bias toward historically significant figures including rulers. Not earned or unlocked. (2026-04-01)
- [x] **Family as NPCs** — Family members are named NPCs with their own archetypes, locations, and memory. They hold memory longer after death. No cross-run lineage. (2026-04-01)
- [x] **Difficulty model** — Structural, not mechanical. Levers: memory decay rate, information opacity, autonomy weight, era volatility, character assignment tier. Never degrades AI quality. (2026-04-01)
- [x] **Map region knowledge** — Click a region shows what the character knows (facts) and has heard (rumors), filtered by archetype, social class, distance, and NPC conversations. Generated on demand. Not an encyclopedia — it's the character's worldview. (2026-04-01)
- [x] **Map event visualization** — Events appear on the map only if the character has plausible awareness. No god-view. Sources: HCE Events DB + world engine. The map is always a partial view. (2026-04-01)
- [x] **Word definitions overlay** — Highlighting any word shows a dictionary definition. Dictionary API, not LLM. Instant, disappears on deselect. Reading aid for era-specific language. (2026-04-01)
- [x] **NPC autonomy model** — NPCs are autonomous subagents. They act every turn, travel between locations, interact with each other, pursue their own goals grounded in historical context. The world happens whether or not the player does anything. (2026-04-01)
- [x] **Player as perspective, not protagonist** — The narrative is always from the player character's subjective perspective. The simulation doesn't revolve around the player. Sometimes nobody cares. The player is a lens, not the center. (2026-04-01)
- [x] **NPC perception on hover** — Focusing on an NPC shows the player character's subjective impression. Colored by interactions, archetype, and biases. Not a stat sheet. (2026-04-01)
- [x] **Ambient world activity** — Every turn, NPCs act as background. The player witnesses activity at their location. The narrative is dominated by world activity, not player action alone. (2026-04-01)
- [x] **Time acceleration** — The player can speed up time passage, letting the simulation run forward. Reinforces that this is a simulation observed, not a story directed. (2026-04-01)
- [x] **Simulation-first architecture** — The turn loop starts with the world (NPCs act autonomously), then the player acts. The player's action is one thread among many. Rebuilt from player-centric to simulation-first on 2026-04-01. See context/other/lessons-learned.md. (2026-04-01)
- [x] **Two-step loading flow** — Era info (events, voices, description) loads instantly via preview endpoint. Character generation happens in background. Prevents empty loading screen. (2026-04-01)
- [x] **NPC voice and tone** — NPCs speak like real people, not poets or narrators. Blunt, messy, emotional, sometimes crude. Swearing is fine when it fits. Two normal people talking, not a dramatic reading. Language adapts to era naturally but register is always conversational. (2026-04-01)
- [x] **Era coverage expansion** — The game covers all post-0 AD history including 1800s, 1900s, and 2000s. A run in 2003 Baghdad uses the same mechanics as 410 AD Italia. Modern eras planned for expansion beyond the current 5-era starter set. CShapes 2.0 for post-1886 borders. (2026-04-01)
- [x] **Disposition shift granularity** — Expanded from 7 to 13 dispositions in a coherent chain (hostile → fearful → wary → grim → guarded → suspicious → cautious → neutral → reserved → formal → engaged → fervent → commanding → warming). All archetype baselines are now reachable. Drift toward baseline every 5 turns. The needs system provides the multi-dimensional inner state (17 needs) that the old fixed ladder lacked. (2026-04-06)
- [x] **NPC autonomy internals** — NPCs now have personality traits (5), inner needs (17), utility scoring against world opportunities, and event-driven permanent trait shifts. Decisions are made by the scoring system; the LLM narrates. Every NPC gets an LLM call every turn — no rule-based shortcuts. (2026-04-06)
- [x] **Time acceleration mechanism** — Player-triggered via POST /api/run/{id}/skip with ticks 1-30. Runs stages 1-4 of the pipeline per tick. Returns a re-grounding passage (sensory, present-tense, who is nearby). No recap. Frontend button not yet built. (2026-04-06)
- [x] **Autonomous world pipeline** — 7-stage pipeline: drift → consequences → events → NPC actions → player input → narrative → persistence. Stages 1-4 run without the player. Structural drift (tension, disposition, needs, rumors) and probabilistic events (skirmishes, unrest, trade disruption, refugee flight) are LLM-free. (2026-04-06)
- [x] **Consequence queue** — Actions schedule delayed effects on WorldState. 8 effect types: tension_shift, rumor, trade_disruption, npc_arrival, event_spawn, material_change, disposition_shift, need_pressure. Validated at fire time. Cleaned up after processing. (2026-04-06)
- [x] **SQLite performance** — WAL mode + synchronous=NORMAL + busy_timeout=5000 + 64MB cache + temp_store=MEMORY. Per-session asyncio lock on turn/skip endpoints prevents double-submit. (2026-04-06)
