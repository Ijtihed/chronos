# CHRONOS -- Project Handoff Document

> This document is the complete onboarding guide for a new AI assistant with zero prior context. It is self-contained. Reading only this file should be sufficient to understand everything needed to continue building.

---

## 1. What CHRONOS Is

CHRONOS is a single-player historical simulation where you are randomly assigned a minor figure in a random era after 0 AD. You type decisions in natural language -- any scale, any ambition -- and the world interprets them through historically grounded AI reasoning. NPCs are autonomous agents with their own goals, personalities, and inner needs; they act every turn whether or not you do anything. The simulation runs on a 7-stage pipeline where the first four stages advance the world before the player ever acts. When you die, the run does not end -- you enter observation mode and watch the world continue. NPC memories of you decay each turn. When the last person forgets you, you are erased from history. That is the ending. The emotional arc is not heroism or victory; it is the quiet experience of being one person in a world that does not revolve around you, and the slow realization that history forgets almost everyone.

---

## 2. What's Been Built (Current State)

**Project phase:** Phase 2.5 (Map Intelligence + HCE) is COMPLETE as of 2026-04-21. All five success criteria met (criterion 5 "historical divergence produces coherent NPC responses" met in plumbing; narrative propagation is carryover). Phases 0, 1, and 2 are done. Next: Phase 3 (Scene Illustrations).

### Backend files (`backend/`)

| File | Lines | What it does |
|------|------:|--------------|
| `main.py` | 970 | FastAPI entry point. All API endpoints. Turn handler, skip handler, travel handler, observation/death handler, NPC perception, region knowledge, historical context highlight, run management. Session locking via asyncio. |
| `world_engine.py` | 904 | The 7-stage simulation pipeline. `simulate_turn()` runs stages 1-4. Tiered NPC actions (active/adjacent/distant). Conflict resolution. Consequence queue processing. Travel advance. Skip advance. |
| `world_state.py` | 554 | Pydantic data models: `WorldState`, `PlayerCharacter`, `NPC`, `Location`, `Era`, `Event`, `ScheduledConsequence`, `PersonalityTraits`, `NpcNeeds`. State mutation (`apply_action`), disposition shift logic, story summary builder, hardcoded Roman Late Empire test state. |
| `persistence.py` | 523 | SQLite layer (aiosqlite, WAL mode). Tables: `sessions`, `turn_logs`, `historical_events`, `consequence_queue` (DB table deprecated for runtime -- queue lives on WorldState). State diff computation. Narrative output builder. |
| `player_knowledge.py` | 599 | Knowledge Matrix. Filters WorldState into PlayerView (what the character can plausibly know). Archetype knowledge tiers (high/medium/low). Event classification (witnessed/known/rumor_reliable/rumor_unreliable/unknown). Region-to-location hint mapping. Rumor accuracy calculation. |
| `npc_personality.py` | 476 | Personality trait generation from archetype ranges. 17-need system with Maslow-weighted urgency curves. Need decay per tick. Event-driven need/trait shifts. Utility scoring: NPCs score world opportunities against depleted needs; top-3 weighted random selection. |
| `npc_engine.py` | 102 | NPC POV generation. Loads `npc_pov.md` template, injects ground context + historical RAG + NPC state, calls local LLM, validates via `NPCPOVResponse` schema, scrubs leaked numbers. |
| `character_gen.py` | 188 | Run initialization. Generates player + 8-15 NPCs from era config via LLM. Concurrent NPC generation. Assigns personality traits and needs. Generates ground context and schedules canonical consequences. |
| `death_engine.py` | 238 | Death check (aging + LLM-judged consequence risk). Memory decay after death (base 0.08/turn with interaction-depth modifier). Observation mode. Erasure narrative generation. |
| `hce.py` | 279 | Historical Context Engine. Ground context generator (queries Events DB, filters through Knowledge Matrix, calls LLM). Canonical consequence scheduler at run start. |
| `llm_schemas.py` | 273 | Pydantic response schemas for every LLM call: `ActionParserResponse`, `AutonomousActionResponse`, `DeathCheckResponse`, `CharacterGenResponse`, `NPCEffect`, `NPCPOVResponse`, `GroundContextResponse`. Number leak detection and scrubbing. |
| `llm.py` | 104 | Shared Ollama client. Model selection: prefers `llama3.1:70b` if available, falls back to `llama3.1:8b`. `CHRONOS_MODEL` env override. `load_prompt()` strips metadata headers. 300s timeout. |
| `action_parser.py` | 89 | Parses player natural language into structured action. Local LLM call via `action_parser.md` template. Fallback on parse failure. |
| `world_drift.py` | 180 | LLM-free structural drift: tension escalation every 3 turns, disposition drift toward archetype baselines every 5 turns, needs decay every turn, rumor propagation every 3 turns. |
| `world_events.py` | 230 | LLM-free probabilistic events: armed skirmishes (30% at critical+soldiers), civilian unrest (20% at high-no soldiers), tension spread (15%), food shortage rumors (25%), trade disruption during sieges (40%), merchant attraction (20%), refugee flight (50%). Ground context stale flag set on armed skirmish and civilian unrest. |
| `utils.py` | 52 | Shared utilities: BFS graph distance, tension level helpers. |

### Backend subdirectories

**`backend/eras/`** -- 5 era config modules + `__init__.py` (37 lines). Each defines: name, year_start, region, description, years_per_turn, lifespan_turns, locations (with lat/lon/neighbors/trade_routes/material_conditions), player_archetypes, npc_archetypes, npc_opportunities (era-specific opportunity descriptions by archetype), loading_events, loading_voices.

| Era | File | Lines | Year | Region |
|-----|------|------:|------|--------|
| Roman Late Empire | `roman_late_empire.py` | 92 | ~410 | Italia |
| Viking Age | `viking_age.py` | 122 | ~870 | Scandinavia/England |
| Crusader States | `crusader_states.py` | 107 | ~1190 | Levant |
| Black Death | `black_death.py` | 125 | ~1348 | Northern Italy/Provence |
| Fall of Constantinople | `fall_of_constantinople.py` | 107 | ~1453 | Byzantine/Ottoman |

**`backend/hke/`** -- Historical Knowledge Engine (RAG corpus):
- `sources.py` (76 lines) -- ERA_SOURCES dict mapping era keys to Gutenberg text IDs and Wikipedia article titles
- `ingest.py` (275 lines) -- Downloads, chunks, embeds. Hierarchical chunking for Gutenberg (parent 1200 tokens / child 300 tokens). Section-based chunking for Wikipedia. CLI: `python -m backend.hke.ingest --all`
- `store.py` (184 lines) -- ChromaDB persistent client. nomic-embed-text via Ollama (falls back to default). Batch add, query with parent-child resolution.
- `retrieve.py` (87 lines) -- `retrieve_context(era_name, query)` returns formatted historical chunks for prompt injection. Child-to-parent resolution for richer context.

### Frontend files (`frontend/`)

| File | Lines | What it does |
|------|------:|--------------|
| `index.html` | 464 | 6 screens: start, loading, transition, game, erasure, plus hamburger panel, notes panel, map container, skip popup, observation input, death marker. Tailwind CSS via CDN. Leaflet via CDN. |
| `app.js` | 1143 | Game loop. Screen management, run lifecycle, turn submission, word-by-word streaming, staggered NPC response rendering, turn dimming, death/observation/erasure handling, time-skip control, notes panel with localStorage persistence, selection overlays (word definition via dictionary API + historical context via LLM), progress bar, scroll-to-bottom, M key map toggle. |
| `map.js` | 425 | Leaflet 2D map. `ChronosMap` namespace. Natural Earth coastlines + era-specific historical borders. Player marker (gold), visited NPC markers (named, with perception on click), unvisited NPC dots (anonymous). Region knowledge on polygon click. Dark theme tiles. |
| `styles.css` | 889 | Dark theme. Custom scrollbar. Word-stream animation. Turn dimming via CSS custom property. Stagger-item animations. Death marker styling. Observation mode muting. Erasure dim layer with 8s fade. Tooltip and context panel styling. Clock element. Notes panel. |

**`frontend/geo/`** -- 5 GeoJSON border files (borders_roman_late_empire.geojson, etc.) + coastlines.geojson + sources.md documenting provenance (aourednik/historical-basemaps, Natural Earth 110m).

### Prompt templates (`prompts/`)

| Prompt | Lines | LLM call | JSON output | Purpose |
|--------|------:|----------|-------------|---------|
| `action_parser.md` | 49 | Local, per turn | `ActionParserResponse` | Parse player natural language into structured action with significance score and NPC impacts. Constrained to 17 canonical action types (speak, trade, petition, threaten, betray, attack, steal, negotiate, defend, fight, siege, alliance, hoard, prevent, save, flee, other) with 3 few-shot routing examples; `backend/action_parser.py` normalizes LLM synonym drift via an in-code ALIASES map. |
| `npc_pov.md` | 99 | Local, per relevant NPC per turn | `NPCPOVResponse` | NPC's first-person reaction. Includes archetype voice rules, vocabulary rules, bad/good examples. The longest and most heavily specified prompt. |
| `autonomous_action.md` | 55 | Local, 2-4 per turn (active NPCs) | `AutonomousActionResponse` | Full NPC autonomous action with rich context. Must connect to urgent need and current situation. |
| `autonomous_action_light.md` | 24 | Local, all offscreen NPCs per turn | `AutonomousActionResponse` | Lighter version for NPCs not at player's location. Less context, 1-sentence output. |
| `character_gen.md` | 22 | Local, 8-15 at run start | `CharacterGenResponse` | Generate historically grounded character from era + archetype. Backstory is what happened TO them. |
| `death_check.md` | 47 | Local, once per turn | `DeathCheckResponse` | Evaluate death risk from action + environment. Calibration examples enforce correct thresholds. |
| `erasure.md` | 28 | Local, once per run | Raw text | Final passage when last NPC forgets player. Pick ONE concrete detail and show it fading. Few-shot examples included. |
| `memory_fade.md` | 24 | Local, per observation turn | Raw text | One sentence of memory fading. Quiet, factual, like history forgetting someone. |
| `ground_context.md` | 32 | Local, at run init + on refresh triggers | `GroundContextResponse` | Generate ground-level lived experience: era_feel, what_character_knows, local_rumors, material_conditions. |
| `region_knowledge.md` | 24 | Local, on map click | Raw text | Character's one-sentence biased opinion of a region. |
| `npc_perception.md` | 34 | Local, on NPC click | Raw text | Player character's honest, blunt opinion of an NPC. 2 sentences max. |

### Data layer

**SQLite (`data/chronos.db`):**
- `sessions` -- run_id (PK), state_json (full WorldState blob), created_at, updated_at
- `turn_logs` -- append-only audit trail per turn: player_input, parsed_action, ambient_activity, npc_responses, state_changes (compact diff), narrative_output, player_view_snapshot
- `historical_events` -- 1,569 canonical events across 5 eras. Fields: year, region, event, significance (local/regional/civilizational), type (war/epidemic/famine/political/religious/economic/natural_disaster/cultural), affects (JSON array), canonical (bool), wikidata_qid, polity_context (column exists but is NULL for all current rows). Indexed by (year, region) and (type, significance). Unique on wikidata_qid.
- `consequence_queue` -- DB table exists but DEPRECATED for runtime. Runtime queue lives on `WorldState.consequence_queue` (List[ScheduledConsequence]) and is persisted with the session JSON blob.

**ChromaDB (`data/chroma/`):**
- Per-era collections (`era_roman_late_empire`, etc.)
- Hierarchical chunks from Project Gutenberg texts (parent 1200 tokens, child 300 tokens)
- Section-based chunks from Wikipedia articles
- Embedding model: nomic-embed-text via local Ollama (falls back to Chroma default all-MiniLM-L6-v2)

**Events DB coverage:** 1,569 canonical events across 5 starter eras, all canonical=True. Build script defines 43 era windows covering 0-2000 AD for future expansion.

---

## 3. How a Turn Works End to End

The turn loop is simulation-first. The world advances before the player acts. Here is the full pipeline:

**Stage 0: Ground context refresh** (conditional, 1 LLM call)
If `ground_context_stale` is true (set by travel arrival, armed skirmish, or civilian unrest), regenerate the GroundContext from Events DB + Knowledge Matrix + LLM. Otherwise skip.

**Stage 1: Structural drift** (no LLM)
- Tension: every 3 turns, random location tension +1 step. Critical locations have 15% chance to spread to neighbors.
- Disposition: every 5 turns, each NPC drifts 1 step toward their archetype baseline (merchant -> cautious, soldier -> guarded, etc.).
- Needs: all 17 NPC needs decay every turn. Fast decay (3-5/turn + tension bonus): survival, safety, family. Medium (2-4): social, trade, profit, duty, etc. Slow (1-2): power, knowledge, faith.
- Rumors: every 3 turns, high-tension locations schedule rumor consequences at adjacent locations 1-2 turns ahead.

**Stage 2: Scheduled consequences** (no LLM)
Fire all pending consequences where `trigger_turn <= current_turn`. Each is validated against current state (target still exists, world hasn't diverged). Invalid consequences are superseded. Fired consequences are cleaned from the queue. 8 effect types: tension_shift, rumor, trade_disruption, npc_arrival, event_spawn, material_change, disposition_shift, need_pressure.

**Stage 3: World events** (no LLM, probabilistic)
Location rules: armed skirmish (30% at critical+soldiers), civilian unrest (20% at high-no soldiers), tension spread (15% from critical), food shortage rumor (25% at famine locations), siege trade disruption (40%), merchant attraction (20% at peaceful). NPC rules: refugee flight (50% for refugee archetype in high-tension toward lowest-tension neighbor).

**Stage 4: NPC autonomous actions** (LLM, tiered)
- Utility scoring picks each NPC's action: detect opportunities at location, score against depleted needs using Maslow curves, weighted random from top-3.
- Active NPCs (at player's location): 2-4 sampled for full LLM call via `autonomous_action.md`. Rich context including ground context, story so far, nearby NPCs.
- All other NPCs (unseen active + adjacent + distant): light LLM call via `autonomous_action_light.md`. Less context, 1-sentence output.
- Conflict resolution: when multiple NPCs target the same entity, highest archetype priority proceeds (general > noble > soldier > priest > merchant > scribe > farmer > refugee).
- Effects applied: disposition shifts (bounded to +/-1), NPC travel, events logged.
- All LLM calls run concurrently via asyncio.gather.

**Stage 5: Player input** (optional, 1 LLM call for parsing + 1-3 for NPC POVs)
- If player typed something: parse via `action_parser.md` (local LLM, JSON mode).
- Travel: advance world by travel_turns ticks, move player, refresh ground context, generate arrival POVs.
- Inaction: player character acts autonomously via `autonomous_action.md`.
- Normal action: `apply_action()` logs event, applies NPC impacts (disposition shifts, memory updates). If significance >= 0.5, schedule player consequences via a dispatch table in `main._schedule_player_consequences` — every canonical action type routes to a specific handler (hostile tension, event_spawn, rumor, disposition_shift, etc.) and target-dependent handlers fall back to a rumor at player location when the target string does not resolve to an NPC. Three types (speak, flee, other) have no specific handler and rely only on the generic rumor@0.6 and tension@0.8 tiers. If significance >= 0.6, check historical divergence against the canonical Events DB.
- Death check via `death_check.md`: aging (automatic at max age) + LLM-judged risk. Threshold 0.7. If dead, transition to `dead_observing`.
- Generate NPC POVs for relevant NPCs only (filtered by `npc_impacts` relevance field). Each via `npc_pov.md` with RAG context injection.

**Stage 6: Narrative assembly** (no LLM)
Build narrative output: ambient NPC activity + player action description + NPC POV responses + travel info + death info + erasure text.

**Stage 7: Persistence** (no LLM)
Save WorldState JSON blob to SQLite. Append turn log with state diff.

**During observation mode (after death):**
Stages 1-4 still run. Memory decay runs each turn (base 0.08, modified by interaction depth). No player actions except travel. When all NPC memories reach 0, run_status -> "ended", erasure text generated.

---

## 4. The NPC System

### Generation
At run start, 8-15 NPCs are generated from era config archetype templates via `character_gen.md`. Each gets a name, description, disposition, relationship_to_player, and current_activity from the LLM. Personality traits and needs are calculated deterministically from archetype ranges (not LLM).

### State each NPC carries
- **Personality traits** (5): ambition, compassion, courage, piety, pragmatism. Integer 0-100. Generated from archetype-specific ranges (e.g., soldier courage 60-95, merchant pragmatism 50-90).
- **Needs** (17): survival, safety, family, social, trade, profit, power, reputation, honor, duty, loyalty, faith, knowledge, order, community, harvest, stability. Float 0-100. Calculated from archetype base + trait formula.
- **Disposition**: one of 13 states in a coherent chain (hostile -> fearful -> wary -> grim -> guarded -> suspicious -> cautious -> neutral -> reserved -> formal -> engaged -> fervent -> commanding -> warming). Shifts one step at a time.
- **current_activity**: physical description of what the NPC is doing right now.
- **emotional_state**: one-word mood, updated by NPC POV responses.
- **memory_of_player**: float 0-1.0. Increases on interaction (0.15 direct, 0.05 proximity). Decays after player death.
- **needs_history**: log of need shifts and critical threshold crossings.
- **stored_povs**: last 10 POV texts generated for this NPC.
- **last_simulated_turn**: turn-based throttling for tiered simulation.

### Autonomous actions
Every NPC gets an LLM call every turn. The utility scoring system makes the decision; the LLM narrates it:
1. Detect world opportunities at NPC's location (siege_threat, trade_caravan_passing, food_shortage, etc.)
2. Score each against NPC's depleted needs using Maslow urgency weights (critical < 15 = 5x weight, urgent < 30 = 3x, moderate < 50 = 1.5x)
3. Weighted random from top-3 scores (deliberate imperfection)
4. LLM receives the chosen opportunity + NPC state + world context and narrates the specific action

### POV responses
Generated via `npc_pov.md`. The prompt is heavily specified:
- Archetype voice reference table (soldier = crude/dark humor/profanity, merchant = calculating/contemptuous, priest = formal over terror, etc.)
- Information rules: mix mundane personal concerns with macro events, state rumors as fact
- Vocabulary rules: most people are illiterate, simple words, short sentences, swearing where it fits
- Anti-patterns: explicit BAD examples (AI speech, sanitized modern language)
- Good examples: specific to archetypes and situations (soldier in 1453, physician in 1191, merchant's wife in 1348, etc.)

### Event-driven permanent shifts
Witnessing death spikes survival needs. Betrayal permanently lowers loyalty. Prolonged hunger permanently increases pragmatism, decreases compassion. These are logged in needs_history.

---

## 5. The Data Layer

### Events DB
Built offline by `scripts/build_events_db.py`. Sources: Wikidata SPARQL (typed entities queried by region/year), Wikipedia REST API (2-3 sentence summaries), local LLM (classifies into flat schema). Deduplication by Wikidata QID. 43 era windows defined covering 0-2000 AD. Current coverage: 1,569 canonical events across 5 starter eras.

At runtime, events are queried by year range and region, filtered through the Knowledge Matrix (archetype tier x event type x graph distance = knowledge quality), and used for:
- Ground context generation at run init and on refresh triggers
- Region knowledge endpoint (map click)
- Loading screen events (preview endpoint)
- Canonical consequence scheduling at run start

### RAG corpus (ChromaDB)
Ingested via `python -m backend.hke.ingest --all`. Sources per era defined in `backend/hke/sources.py`:
- Project Gutenberg primary sources (Gibbon, Ammianus Marcellinus, Augustine, sagas, chronicles)
- Wikipedia articles (era overviews, key events, major figures)

Gutenberg texts use hierarchical chunking: parent chunks (1200 tokens, 150 overlap) contain child chunks (300 tokens, 50 overlap). Retrieval hits child chunks first, then assembles parent context for richer LLM input. Wikipedia uses section-based chunking (split on H2/H3, capped at 1000 tokens).

Embedding model: nomic-embed-text via local Ollama (free). Falls back to Chroma's default (all-MiniLM-L6-v2) if Ollama is unreachable.

RAG context is injected into NPC POV prompts via `retrieve_context(era_name, query)`.

### SQLite tables
- `sessions`: WorldState JSON blob per run_id. UPSERT on every save.
- `turn_logs`: append-only per turn. State diffs (not full clones). Foreign key to sessions.
- `historical_events`: canonical events. Indexed by (year, region) and (type, significance).
- `consequence_queue`: DB table exists but unused at runtime. Runtime queue is on WorldState object, persisted in the session JSON blob. DB table kept for future analytics.

Performance pragmas: WAL mode, synchronous=NORMAL, busy_timeout=5000, 64MB cache, temp_store=MEMORY. Per-session asyncio lock prevents double-submit on turn/skip endpoints.

---

## 6. The Frontend

### Screens (6 total)
1. **Start screen** (`screen-start`): "Begin" button, optional "Continue" button if a saved run exists in localStorage. Confirmation dialog before overwriting existing run.
2. **Loading screen** (`screen-loading`): Two-step flow. Preview endpoint returns era info instantly (name, year, description, Events DB loading_events). Character generation runs in background. Progress bar with exponential approach curve. When characters are ready, shows "Your life begins" with player name/role/description.
3. **Transition screen** (`screen-transition`): 3-second black screen between loading and game.
4. **Game screen** (`screen-game`): The main play surface. Manuscript scroll area, bottom bar with text input and skip button, top bar with year/location/clock. Hamburger menu slides from right (map toggle, notes, new run).
5. **Erasure screen** (`screen-erasure`): Triggered when run ends. 8-second dim fade, then erasure text appears, then restart button after 5 more seconds. Pure black background with minimal white text.
6. **Observation variant** (not a separate screen): Game screen with bottom bar hidden, observation input shown ("YOU ARE DEAD / TRAVEL ONLY"), manuscript muted to lower opacity.

### Clock/calendar element
Top bar shows year AD. Clock element shows `wk N / season` derived from turn number. Seasons cycle every 13 weeks (52 turns = 1 year). Updated on every turn.

### Notes panel
Overlay panel triggered by notes button in hamburger menu. Textarea persisted to localStorage per run_id + player_name. Timestamp button inserts `[Season YYYY AD]`. Pin button inserts diamond marker. Auto-saves on 500ms debounce.

### Skip button
Bottom bar. Short press: skip by `defaultSkipTicks` (7). Long press (400ms): opens popup with options (1/3/7/14/30 turns). Time presets above the input bar let the player change the default skip amount (labeled as hours/day/week/month/year).

### Map
Leaflet 2D. Dark CartoDB tiles. Natural Earth coastlines + era-specific historical borders (GeoJSON). Player marker (gold pulsing dot). Visited NPC markers (named, white, clickable for perception). Unvisited NPC dots (anonymous gray, smaller). Region knowledge on polygon click (fetches from `/api/run/{id}/region/{polity_name}`). Toggle with M key or hamburger menu button.

### Known issues and recent fixes
- Ground context was static for the full run. **Fixed** -- now refreshes on travel arrival and significant world events (armed skirmish, civilian unrest) via `ground_context_stale` flag.
- Skip button was backend-only. **Fixed** -- UI added to bottom bar.
- Loading screen events were hardcoded per era. **Fixed** -- preview endpoint draws from Events DB.
- Word definitions overlay: selection-based, uses free dictionary API. Single words resolve via dictionary API; multi-word selections show a "Context" button that fetches LLM-powered historical context via `POST /api/run/{id}/context`. Positioning polished 2026-04-21 (Fix 5): bottom-edge viewport clamp, last-rect anchoring for multi-line selections, live Node+offset reconstruction so the context panel tracks the original text position even if the manuscript scrolls between selection and click.
- Turn dimming: older turns fade to 35% opacity via CSS custom property.
- Word-by-word streaming: NPC POV responses stream at 35ms per word. Cancels on new submission.

---

## 7. Design Decisions That Must Not Be Changed

These are architectural and design commitments. Changing any of them would break what makes CHRONOS what it is.

1. **Player impact radius stays small.** The player is one person in a large world. Most actions affect 1-3 NPCs. The world does not revolve around the player. Sometimes nobody cares.

2. **NPCs are autonomous, not reactive.** NPCs have their own lives, goals, and needs. They act every turn whether or not the player does anything. The LLM narrates their decisions; it does not make them. The utility scoring system drives behavior.

3. **Information is earned through travel.** There is no omniscient UI -- no dashboard, no event log, no diplomatic screen, no map annotations for things the character does not know. Information comes only from being somewhere or talking to someone who was.

4. **Death is not game over.** The run continues in observation mode. Memory decays. The world keeps going. Erasure is the real ending.

5. **Erasure is the climax.** The moment the last NPC forgets the player is the emotional peak of every run. The erasure text picks one concrete detail and shows it disappearing. It must feel quiet and final, not dramatic.

6. **Zero frontier API calls at runtime.** All LLM calls run on local Ollama. The action parser has a labeled frontier swap point but it is unused. Per-run cost is $0.00 in API fees.

7. **World runs on local Llama.** Preferred: llama3.1:70b (48GB+ RAM). Fallback: llama3.1:8b (16GB). Model auto-selected at startup. CHRONOS_MODEL env var for override.

8. **Prompt templates are design artifacts.** They are reviewed separately from code. Every LLM call has a corresponding prompt file in `prompts/`. Prompt changes are design decisions, not implementation details.

9. **The simulation is the truth; the narrative is the filter.** WorldState is the machine-readable ground truth. PlayerView is what the character can plausibly know. The player never sees raw state.

10. **Total player freedom.** No action menus, no suggested moves, no constraints on vocabulary or scope. The player types anything. The game interprets faithfully.

---

## 8. Current Open Issues

### From open-questions.md (unresolved)
- **Divergence visibility to NPCs and narrative** (new as of 2026-04-21): Divergence detection fires end-to-end and writes to `state.historical_divergences` + invalidates queued canonical consequences. NPC POV prompts and narrative text do not yet read the divergence signal. An NPC in a world where the player prevented the Sack of Rome still speaks as if the sack happened.
- **Stage 2 supersession validation strictness** (new as of 2026-04-21): `_validate_consequence` checks target-exists but does not model deeper divergence (e.g., "the siege you prevented no longer applies as a consequence source"). Resolve alongside divergence-visibility work.
- **Prompt coverage gap beyond action_parser.md** (new as of 2026-04-21): Only the action parser has drift-resistant vocabulary constraints. The other ~10 prompts (npc_pov, autonomous_action, death_check, erasure, ground_context, etc.) were never audited for similar drift.
- **Byzantine Empire centroid era-ambiguous** (known limitation from Fix 6): Current YAML uses median-period position (39.0°N, 32.0°E, 1200 km); geographically wrong for 5th-century events. Future ingestion with era-keyed centroid sub-entries would fix.
- **`polity_context` column unpopulated** (known limitation from Fix 6): Events DB schema carries the field; current ingestion leaves it NULL. Architecturally planned as a centroid-resolution fallback but dead code today.
- **Information Provenance Graph distortion parameters:** How degraded does information get per hop? Calibrate through playtesting once social graph exists (Phase 5).
- **Diffusion model provider:** Local vs API for scene illustrations. Resolve at Phase 3 kickoff.
- **Session length target:** 30-minute run vs multi-day run are different games. Affects Phase 5 pacing.
- **NPC relationship graph granularity:** NPC-NPC ties for Phase 5. How much structure to track.
- **Multiplayer:** Does it ever make sense? Open, not blocking.
- **Meta-progression:** Anything carry over across runs? Open, not blocking.
- **Terrain view:** 3D relief/war-table view. Cut from Phase 2, unscheduled.

### Recently resolved (Fix 1-6, 2026-04-21)
- ~~Action parser vocabulary drift~~ → Fix 1: ALIASES map normalizes known LLM synonym drift (inquiry → speak, barter → trade, etc.) + Fix 3 added prompt-side vocabulary constraint with few-shot routing examples.
- ~~V4 consequence gap~~ → Fix 2: dispatch table in `main._schedule_player_consequences` routes every canonical action type at sig ≥ 0.5 to a specific handler. Fix 4 added target-miss fallback (rumor at player location) for the target-dependent handlers so high-sig actions with unresolved targets never silently no-op.
- ~~Pre-existing live test failure~~ → Fix 3: test asserted exact LLM output strings, which the model never produced stably. Replaced with structural invariants (conversational phrasings never route to hostile/travel/inaction).
- ~~Event markers on map deferred~~ → Fix 6: centroid YAML + normalizer + `GET /api/run/{id}/events/visible` endpoint + frontend renderer. 97.2% event region coverage.
- ~~Historical divergence end-to-end test~~ → Fix 4: integration test verifies divergence fires against Sack of Rome 410. Narrative propagation is the new open question (above).
- ~~Word definitions overlay positioning~~ → Fix 5: bottom-edge clamp, multi-line last-rect anchoring, Node+offset capture for scroll-aware context panel.

### Observations (not blocking)
- NPC response length: llama3.1:8b frequently exceeds 2-4 sentence constraint
- Ambient activity volume: 2-4 NPCs per turn at player location may need tuning
- Loading screen character generation: 1-2 minutes via Ollama
- Turn latency: 12 concurrent Ollama calls per turn with all NPCs. May need vLLM/SGLang if >15s
- Consequence queue growth: linear during time-skip, may need pruning for very long runs

---

## 9. What Comes Next

### Phase 2.5 closed 2026-04-21
All five success criteria met. Carryovers tracked in open-questions.md: divergence narrative propagation, supersession strictness, prompt coverage gap beyond action_parser.md, Byzantine centroid era-ambiguity, polity_context unpopulated.

### Phase 3: Scene Illustrations
Decision pending on local diffusion model. Leading candidate: `stable-diffusion-cpp-python` (the llama.cpp equivalent for image generation). Constraint: VRAM -- Llama 70b and a diffusion model cannot run simultaneously. Architecture would be sequential: illustration triggers pause the LLM, generate the image, then resume. Target style: photorealistic, historically accurate, gory where appropriate. Triggers: run start, character death, erasure, 2-3 major narrative moments per run. Images are ephemeral -- shown briefly then gone, never saved to disk permanently.

### Phase 4: HKE v2
Synthetic Q&A dataset from run logs. Fine-tuned or heavily prompted model for consequence generation. RAG as fallback for rare/edge contexts.

### Phase 5: Full Era Coverage + World Depth
All 20 era buckets playable. NPC-to-NPC social graph. Faction emergence from relationship data. Information Provenance Graph (replaces archetype/geography filtering). NPC interaction logging for provenance. Memory decay curve tuning.

### Five-character concurrent system (major architectural shift, not yet built)
The game is being redesigned toward a five-character concurrent simulation. The player is a ghost observer who can inhabit one of five characters simultaneously running in the same historical period but scattered geographically. When you switch away from a character they keep living -- you drop back into their present moment with no recap. Characters can die while you are away. The world runs on its own clock the player controls (hours/days/weeks/months/years). There is no turn-based loop -- the simulation ticks forward continuously while the player is present and pauses when they close the game. The whisper mechanic: the player can nudge (not command) the character they are inhabiting. NPCs are fully autonomous and do not orbit the player. This architecture is designed but not built -- the current codebase is a sophisticated single-character simulation that serves as the foundation.

### Generative archetype system
Replace hardcoded era config archetype lists with a generative system that produces contextually appropriate characters from the historical world state. A content audit found that player archetypes skew toward professionals (merchants, soldiers, scholars) rather than marginal figures (peasants, servants, captives). The long-term fix is dynamic generation, not more hardcoded configs.

---

## 10. How to Work on This Project

### The AI dev protocol
1. **Restate the task** before coding. Your first response is always a brief restatement of what you understood and how it connects to the design context. Do not start writing code until confirmed.
2. **Confirm before building.** If something is ambiguous in the context docs, surface the ambiguity and ask. Never resolve open questions with assumptions.
3. **Update context docs** when decisions land. Decisions made in chat that never land in a file don't exist. Update `context/game logic context/` files when design decisions are made.
4. **Prompt templates are design artifacts** reviewed separately. When you write a new LLM call, also write the prompt template as a standalone artifact and flag it for review before wiring it in.
5. **Model tier policy** (hard constraint): local Ollama only at runtime. Zero frontier calls. If a new frontier call is needed, justify why local is insufficient and flag for explicit user review. Default model: llama3.1:8b. Preferred: llama3.1:70b. Cost target: $0.00-$0.30 per run.
6. **Open questions:** do not assume answers. Check `open-questions.md` before implementing anything that touches an unresolved item. If a task depends on an open question, stop and flag it.
7. **Roadmap discipline:** follow the current phase. Do not implement Phase N+1 features until Phase N success criteria are verified. If existing code implements a future-phase feature while an earlier phase is unfinished, surface the conflict.

### Existing `.cursor/rules/` files
- `chronos-ai-dev-protocol.mdc` -- full dev protocol (restate, confirm, update docs, prompt review)
- `chronos-design.mdc` -- design source of truth pointers, design constraints
- `chronos-roadmap.mdc` -- phase discipline, completion log requirements, drift detection
- `chronos-model-tier.mdc` -- model tier policy enforcement

### Context docs
All in `context/game logic context/`:
- `cursor_spec.md` -- index with current project status and read order
- `overview.md` -- what the game is, player's role, perspective not protagonist
- `gameplay.md` -- turns, NPC autonomy, voice/tone, information system, travel, factions, death
- `npc-voice-system.md` -- archetype voice reference, what NPCs never do, required content
- `simulation-and-world.md` -- world model, map, region knowledge, events, family, difficulty, era coverage
- `historical-context-engine.md` -- HCE: Events DB + ground context generator
- `roadmap.md` -- phased delivery with success criteria, completion log, model tier policy
- `open-questions.md` -- unresolved design decisions, do not assume

### Communication style
The developer communicates tersely and expects dense actionable responses. No em dashes. No AI speech patterns. Conclusions over hedging. Direct correction over explanation. Everything reviewed locally before any public action.

### Running the project
```bash
# Backend
pip install -r requirements.txt
ollama pull llama3.1:8b          # minimum viable
ollama pull nomic-embed-text      # embeddings
python -m backend.hke.ingest --all  # one-time: ingest RAG corpus
python scripts/build_events_db.py --all  # one-time: populate Events DB
uvicorn backend.main:app --reload

# Frontend
# Served as static files from FastAPI. Open http://localhost:8000

# Tests
pytest tests/ -x              # offline tests (mocked LLM)
pytest tests/test_live.py -x  # requires running Ollama
```

### Competitor context
Pax Historia (YC-backed, 35k DAU) exists in the adjacent space. Top-down grand strategy -- you play as a nation. CHRONOS is bottom-up personal -- you play as a nobody. Different games aimed at different feelings. Pax Historia uses frontier models at scale (token costs are a known user complaint). CHRONOS's local-first architecture is a genuine differentiator.
