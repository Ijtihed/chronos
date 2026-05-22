# CHRONOS — Iteration Roadmap

> Each phase is a **shippable, testable milestone**. A phase is only complete when its **success criteria** are met — not when its tasks are checked off.
> No phase should begin until the previous phase's success criteria are confirmed.
> This document is a **living record**. When a phase completes, note what actually happened vs. what was planned.

Each phase below includes **Definition of success** (what “done” means in one place) and **How to verify** (concrete checks to run before marking success criteria complete). Verification can mix **manual** playtesting, **scripted** tests, and simple **measurements** — document which you used in the phase completion log.

---

## PHASE 0 — Proof of Life

**Goal:** Prove the core loop works end to end. The scaffolding connects. At least one NPC responds to a player action with a historically grounded POV.

### What exists at the end of this phase

- A basic web app (minimal UI, no styling required)
- A text input field where the player types an action in natural language
- The game converts that input into a structured action and updates a world state object
- At least one NPC in the scene generates a POV response to the player's action
- The world state and NPC response are visible in the UI (raw or lightly formatted is fine)
- One hardcoded era: whichever has the richest Project Gutenberg source material at time of build (evaluate at build time — strong candidates: Roman Late Empire, Viking Age, Byzantine Empire)
- No map, no character generation, no memory system — all hardcoded or stubbed

### Success criteria

- [x] Scaffolding compiles and all layers connect end to end
- [x] At least one NPC POV response is generated after a player action
- [x] The response feels historically plausible, not generic
- [x] World state object updates correctly after the action

### Definition of success

The **full path** from browser → backend → action representation → world mutation → **local** NPC generation → UI runs without manual glue. A human can play one “turn” and see **both** an updated world state and an NPC reaction that **could not** be produced without the models (parser + Ollama). The POC **proves** layering and model-tier split (frontier parser only if/when enabled; everything else local per **MODEL TIER POLICY**).

### How to verify

1. **Build & run** — From a clean clone: install deps, set `.env` if using a frontier parser, start Ollama with agreed local model; start frontend + API per README or scripts. Confirm no runtime errors on load.
2. **Happy path** — Enter a natural-language action; confirm UI shows **structured action** (JSON or equivalent), **updated world state** (diff or full object), and **NPC POV** text within one response cycle.
3. **World state correctness** — Compare state **before** and **after**: at least one field should change in a way that matches the parsed intent (e.g. location, disposition, a stub “event” field). Spot-check with 2–3 different phrasings of the “same” intent.
4. **Plausibility spot-check** — Read NPC POV blind (or ask a second person): it should reference **era-appropriate** framing from hardcoded prompt/context, not pure modern boilerplate. “Fails” if N generic fantasy lines out of M trials (pick M small, e.g. 5).
5. **Tier check** — Grep or trace: **no** frontier/API LLM usage except the **documented** parser call; NPC + narrative paths stay on **Ollama** (or stub clearly labeled if pre-LLM spike).
6. **Regression** — Repeat happy path after a trivial code change to ensure wiring still holds (optional CI: one smoke test hitting `/health` + turn endpoint if backend exists).

### What is explicitly NOT in this phase

- Visual map
- Random era or character generation
- Memory/death mechanic
- RAG / historical knowledge engine (LLM context injection via hardcoded prompt is fine)
- Any styling or polish

---

## PHASE 1 — Playable Text Loop

**Goal:** A living historical simulation that the player observes through one character's perspective. NPCs are autonomous agents with their own lives. The player's actions are one thread among many. A complete run goes from character assignment to erasure. Everything is text. No map yet.

### What exists at the end of this phase

- **Simulation-first architecture:** The world advances every turn. NPCs act autonomously -- traveling, trading, arguing, fleeing -- whether or not the player does anything. The player witnesses what unfolds at their location. Their actions are one thread among many. Sometimes nobody cares.
- **NPCs are autonomous subagents:** They have goals, they move between locations, they interact with each other. Their behavior is grounded in historical context and their archetype. They are the simulation.
- **Player as perspective:** The narrative is always from the player character's subjective POV. The player is a lens into the simulation, not its center. NPC perception on hover shows the character's subjective impression.
- **Total player agency:** No action menus, no suggestions. The player types any decision at any scale. The game never tells the player what to do.
- **Ambient world activity:** Every turn shows what NPCs are doing around the player, not just reactions to the player's action. The narrative is dominated by world activity.
- Run initialization: random era selected from a starter set of 5, player character generated with archetype + backstory
- 8–15 NPCs seeded across multiple locations with archetypes, social classes, and relationships
- Full turn loop: world advances (NPCs act) then player optionally acts → world responds → structured state + narrative layer both update
- Inaction: if the player types "wait" or "do nothing," their character acts autonomously based on archetype
- Travel mechanic: player can move between locations, costing turns, with world advancing in transit. NPCs at the destination react to arrival.
- POV system gated by geography: only NPCs at the player's current location respond
- Anachronism handling: modern language silently mapped to era-appropriate intent
- Memory system: NPCs track memory of the player (0.0–1.0), decay begins on player death
- Death mechanic: hybrid aging + consequence. After death, player enters observation mode (travel only). Run ends when last NPC memory reaches 0.
- Historical Knowledge Engine v1: RAG over Gutenberg + Wikipedia corpus, Chroma local vector DB
- Starter eras: Roman Late Empire (~410), Viking Age (~870), Crusader States (~1190), Black Death (~1348), Fall of Constantinople (~1453)
- SQLite session persistence
- Present-tense stream UI: blank text input, location bar with travel links, death/observation/erasure states

### Success criteria

- [x] A full run can complete from character generation to erasure without soft-locks
- [x] At least 3 different eras produce runs that feel historically distinct
- [x] NPC perspectives feel distinct from each other (archetype, social position, bias are evident)
- [x] The player can type anything — the game handles it without breaking
- [x] Only genuinely affected NPCs react to any given action (not everyone nearby)
- [x] The death + memory fade mechanic lands emotionally — the ending feels like erasure, not a game over screen

### Definition of success

A **full run** is reproducible: new run, play until **last memory dies** without cheats. The **world is alive** -- every turn, NPCs act autonomously (visible as ambient narrative), travel between locations, and interact with each other. The **player is one thread** -- their action produces consequences but the narrative is dominated by world activity. **Sometimes nobody cares**. Travel gates information. RAG grounds responses for **5+** eras. Emotional bar: end state reads as **fade / erasure**, not a game over.

### How to verify

1. **World is alive** -- Start a run. Do nothing for 3 turns. Confirm NPCs are visibly acting each turn (ambient narrative shows NPC activity, not silence).
2. **NPC movement** -- Play 5+ turns. Confirm at least one NPC has moved to a different location than where they started (check via map or state).
3. **Player is one thread** -- Take an action. Confirm the turn response includes both the player's consequence AND ambient NPC activity (not just reaction to the player).
4. **Nobody cares** -- Take a minor action (observe, wait). Confirm the response shows world activity but little or no reaction to the player specifically.
5. **NPC perception** -- Hover over an NPC. Confirm a subjective impression appears, colored by the character's archetype.
6. **Run lifecycle** -- Complete a run to erasure. Confirm no soft-locks.
7. **Eras** -- Play 3 different eras. Confirm they feel distinct.
8. **Travel** -- Travel to a new location. Confirm the world advanced during transit and NPCs at the destination are doing their own things.
9. **Death and memory** -- After death, confirm memory decay and erasure framing.

### What is explicitly NOT in this phase

- Visual map
- Diffusion-generated scene illustrations
- Fine-tuned model
- Synthetic Q&A database

---

## PHASE 2 — The Map

**Goal:** The world becomes spatial and visible. The player can see where they are, where NPCs are, and how borders have shifted as a result of their actions and world events.

### What exists at the end of this phase

- 2D Leaflet.js map integrated into the web UI, toggles with the narrative view via M key
- Natural Earth 110m coastlines + era-specific historical borders from aourednik/historical-basemaps
- Player marker (gold) at current location, NPC markers with visited/unvisited distinction
- Visited NPCs: named markers with role on hover. Unvisited NPCs: anonymous dots. This is the information-is-geography mechanic made visible.
- visited_locations tracking in world state -- grows as the player travels
- 5 border GeoJSON files (400, 900, 1200, 1300, 1400 AD) sourced, simplified, documented in frontend/geo/sources.md
- Locations in all 5 era configs have lat/lon coordinates
- GET /api/geo/{era_key} endpoint serves border GeoJSON per era

### Success criteria

- [x] Map loads correctly for at least 3 different eras with accurate historical borders
- [x] Player position and NPC positions are correctly represented
- [ ] Border changes from world events — deferred (borders are static per era in Phase 2; dynamic borders are a future feature)
- [x] Travel feels spatial — moving across the map takes more turns than moving locally

### Definition of success

The **map is authoritative** for place: player marker, NPC markers, and **historical borders** match run era at start; **dynamic** border deltas (from sim + events) **visibly** update across turns. **Travel** consumes more turns for long hops than local moves, and the avatar position matches narrative location. **3+** eras load correct basemap + border layers without mix-ups.

### How to verify

1. **Layer smoke** — For **3** eras: load run, confirm Natural Earth base + `historical-basemaps` (or CShapes for ≥1886) render; no blank map, no wrong-era file (checksum or logged layer ID).
2. **Positions** — Cross-check **3** NPCs: map coordinates vs structured state locations; move player via text command; marker updates **same** turn.
3. **Border drift** — Script or scenario: trigger **2** world events that change control; verify GeoJSON diff or styled layer updates **between** screenshots or state dumps N turns apart.
4. **Travel cost** — Local move vs cross-region move: assert `turns_spent` (or equivalent) for long leg **>** short leg; narrative + marker jump align.
5. **Marker UX** — Click NPC: name + visited flag; must not show full POV (still travel/narrative rules from Phase 1).
6. **Performance** — Pan/zoom usable on a mid laptop; document target FPS or “no >500ms jank” for a canned scenario.
7. **Post-1886** — One run in CShapes era; borders source switches without error.

### What is explicitly NOT in this phase

- Terrain / relief view (deferred to future phase)
- Clickable map interactions (travel is typed in the narrative)
- Region knowledge on hover/click (deferred to Phase 2.5)
- Event markers on map (deferred to Phase 2.5)
- Diffusion illustrations (Phase 3)
- Dynamic border changes from player actions (borders are static per era)

---

## PHASE 2.5 -- Map Intelligence + Historical Context Engine (COMPLETE)

**Goal:** The map becomes a knowledge surface. Clicking a region shows what the character knows and has heard. Significant events appear on the map, filtered by character awareness. The Historical Context Engine (Events DB + Ground Context Generator) ships as the data backbone.

**Status (2026-04-21):** COMPLETE. All five success criteria met. Events DB, ground context, region knowledge on click, loading screen from Events DB, time-skip UI, word definitions overlay, event markers on map, and historical divergence detection all shipped. One carryover from criterion 5: divergence is visible in state but not yet propagated to NPC POVs or narrative text (see open-questions.md, "Divergence visibility to NPCs and narrative").

### What exists at the end of this phase

- **HCE Events DB** -- a SQLite table of canonical historical events indexed by year and region, populated by a build-time script from Wikipedia + Wikidata + structured datasets. One DB covers all eras. **Current coverage:** Fall of Constantinople 875, Roman Late Empire 303, Viking Age 152, Crusader States 237, Black Death 182 — **1,749 total events** across all 5 starter eras. Build script defines 43 era windows covering 0–2000 AD for future expansion.
- **Ground Context Generator** -- at run initialization, generates a GroundContext object (era_feel, what_your_character_knows, local_rumors, material_conditions) from the Events DB + RAG corpus. Injected into world state and NPC prompts.
- **Region knowledge endpoint** -- GET /api/run/{id}/region/{polity_name} returns character-filtered knowledge (known facts + rumors) for any region the player clicks on the map. Generated on demand via local LLM, cached per region per turn.
- **Event markers on map** -- GET `/api/run/{run_id}/events/visible` returns events filtered through the Knowledge Matrix (only events the character plausibly knows about) with coordinates resolved via a hand-curated centroid YAML (`backend/geo/region_centroids.yaml`) and a compound-string normalizer. 97.2% of the 1,569 canonical events resolve to a centroid. Rendering: witnessed and known tiers use a colored pin plus a circle (witnessed gets a small white dot overlay); rumor_reliable and rumor_unreliable tiers render as plain circles at reduced opacity with a dashed border for unreliable; broad regions (≥1000 km radius) render as circles only, no pin. Color mapping: war red, epidemic green, famine orange, political blue, religious purple, economic yellow, natural_disaster brown, cultural grey.
- **Knowledge awareness model** -- determines what a character knows about a region based on: distance, archetype/social class, trade routes, NPC-sourced info, and era common knowledge.
- **Historical divergence tracking** -- game-generated events marked canonical: false in the Events DB. When player actions contradict canonical history, subsequent canonical events flagged as superseded.
- **Build-time agent** -- scripts/build_events_db.py populates the Events DB per era from Wikipedia + Wikidata + structured sources via local LLM.
- **Time-skip UI** -- frontend button in the bottom bar for triggering POST /api/run/{id}/skip. Ships the time-acceleration feature that was backend-only in Phase 1.
- **Loading screen from Events DB** -- era preview endpoint (POST /api/run/preview) returns loading_events drawn from the Events DB, replacing the hardcoded per-era config data from Phase 1.
- **Word definitions overlay** -- highlighting any word in the narrative shows a dictionary definition as a small popup. Uses a dictionary API (not LLM), instant response. Reading aid for era-specific language, titles, and concepts.

### Success criteria

- [x] Events DB has 20+ events per era within 50-year window of run start — all 5 eras far exceed 20 (minimum 152 for Viking Age)
- [x] Region knowledge on click feels character-appropriate -- a farmer knows less than a scholar
- [x] Event markers appear only for events the character is plausibly aware of — shipped via Knowledge Matrix filtering in `/api/run/{id}/events/visible` with centroid resolution at 97.2% coverage
- [x] Ground context at run start makes NPC voices more grounded and era-specific than Phase 1
- [x] Historical divergence: player actions that contradict canonical events produce coherent (not contradictory) NPC responses — **met in plumbing, narrative carryover.** Divergence detection fires end-to-end, writes to `state.historical_divergences`, and invalidates queued canonical consequences. NPC POV and narrative propagation is deferred to a future phase (see open-questions.md, "Divergence visibility to NPCs and narrative")

### Definition of success

The map is no longer just geography -- it is **the character's understanding of the world**. Clicking a region produces **knowledge the character would have** and **rumors they have heard**, not an encyclopedia entry. Event markers appear **only when the character has plausible awareness**. The HCE Events DB provides the **historical spine** that NPC voices and consequences draw from. Ground context at run start makes the opening feel **lived-in**, not generic.

### How to verify

1. **Events DB coverage** -- For each of 5 eras: count events in 50-year window. Must be >= 20. Spot-check 5 events per era for factual accuracy.
2. **Region knowledge asymmetry** -- Same region, two runs with different archetypes (scholar vs farmer). Scholar's knowledge should be richer and more specific. Farmer's should be vague or rumor-heavy.
3. **Event marker filtering** -- Start a run. Confirm no distant events visible. Travel to a new location. Confirm events near that location now appear. Confirm no events appear that the character has no plausible awareness of.
4. **Ground context quality** -- Compare NPC first-turn responses with and without GroundContext. With context, responses should reference era-specific material conditions and rumors.
5. **Divergence** -- Trigger a player action that contradicts a canonical event (e.g. defend Constantinople). Subsequent NPC responses should reflect the changed world, not the canonical outcome.

### What is explicitly NOT in this phase

- Diffusion illustrations (Phase 3)
- Fine-tuned consequence model (Phase 4)
- Full NPC-to-NPC relationship graph (Phase 5) -- but basic NPC-on-NPC interactions should be visible
- Terrain / relief map view
- Perspective switching

---

## PHASE 2.6 — Spatial Substrate (manuscript depth + globe + war-table)

**Goal:** The player handles the world as a physical, dimensional thing. The manuscript becomes a 3D stack of memories, the map becomes a globe, and a regional war-table view with real terrain becomes available. Three surfaces, all dimensional, all still partial-knowledge filtered. No new gameplay verbs — this is the *spatial substrate* for everything Phase 2.5 already shipped.

**Why this exists between 2.5 and 3:** Re-opens two previously-closed roadmap decisions. The 3D globe was cut from Phase 2 in a design session (original cut reasoning unknown to the 2026-05-04 session that re-opened it). The tilted relief / war-table view was deferred from `open-questions.md`. Both are now in scope. The manuscript-as-3D-artifact is a wholly new design statement, documented in [manuscript-as-artifact.md](manuscript-as-artifact.md).

### What exists at the end of this phase

- **Manuscript-as-stack** — the narrative is a depth-stacked 3D artifact. Older turns recede into z, atmospheric haze marks distance in time, scrolling pulls the camera back through the stack, hovering a deep block lifts it forward. Memory decay reads as both word loss and atmospheric distance. CSS 3D transforms only — no WebGL.
- **Globe** — the flat Leaflet map is replaced by a 3D globe (Three.js). All Phase 2 / 2.5 functionality preserved: era-correct historical borders, character-aware event markers, region-knowledge-on-click, NPC perception popups, save-view restoration, visited/unvisited NPC distinction. Earth is dark grey-black per the existing palette, atmosphere is a subtle blue limb glow, not photoreal.
- **War-table** — a separate dimensional view of the era's region, toggleable from the globe with `T`. Real DEM terrain (NASA SRTM 30m, downsampled). Markers cast shadows. Borders extrude vertically. Per-era heightmaps pre-built offline, served as PNG via a new endpoint.
- **Feature flags** — each surface is independently toggleable. `?flat=1` URL param disables the manuscript stack and falls the map back to Leaflet. `T` key toggles war-table from globe. Any single piece can be backed out without touching the others.
- **Flat Leaflet retired (but kept in tree)** — `frontend/map.js` stays as a fallback behind `?flat=1` until the globe is proven across an extended playtest. After that it can be removed.

### Success criteria

- [ ] Manuscript-as-stack: 30+ turn run reads as a coherent depth stack; older turns visibly recede; hover-to-recover still works; zoom-out becomes a pull-back through the stack; all existing memory-decay behavior preserved.
- [ ] Globe: era switch loads correct borders; player + NPC + event markers project at correct lat/lon; click handlers fire region/event/perception panels identically to the flat map; save-view restoration works.
- [ ] War-table: 5 era DEMs built; terrain renders at 60fps on M4 Max; all marker click behavior matches the globe; `T` round-trips cleanly.
- [ ] All Phase 2 / 2.5 success criteria still pass under the globe (this is a substrate change, not a regression).
- [ ] No backend simulation, prompt, or LLM cost changes.

### Definition of success

The world has **volume** the player can handle. Manuscript scrolls in z, not just y. Map orbits as a sphere, not a plane. Region presents as a tilted physical table with real terrain. None of these surfaces add information the player wasn't supposed to have — the Knowledge Matrix, region-knowledge filtering, and event-tier rendering are all unchanged. What changes is the **physical dimensionality of how the player engages**. The artifact is a stack. The earth is a sphere. The region is a table.

### How to verify

1. **Manuscript stack** — Play 30+ turns. Confirm: each turn-block recedes one z-step from the next; opacity ramp + blur ramp visible; hovering a deep block lifts it forward and clears its blur; the zoom-out (`Z` key) becomes a parallax pull-back through the stack rather than a 2D scale; observation mode (`observation-muted` filter) still composes correctly with the depth filters; `?flat=1` URL param falls back to the pre-stack manuscript.
2. **Globe** — For each of 5 eras: load run, confirm correct borders project on the sphere; place 3 NPC markers and cross-check coordinates against the structured state; click a region, confirm region-knowledge panel; click an event marker, confirm event panel; click an NPC marker, confirm perception popup; confirm save-view restoration across reload; `?flat=1` falls back to Leaflet.
3. **War-table** — Press `T` from the globe. Confirm: terrain rises from a DEM heightmap at the era's regional bounding box; markers cast shadows; borders extrude; click handlers fire identically to the globe; `T` again or `Esc` returns to the globe; era label appears massive and faint behind the table.
4. **Performance** — Long-run perf: 100+ turn-block manuscript stays interactive on M4 Max; globe + full marker set holds 60fps; war-table holds 60fps with DEM loaded.
5. **No regressions** — Full Phase 2 / 2.5 verification checklist passes under the new substrate.

### What is explicitly NOT in this phase

- 3D scenes generated for events (a future Phase 3 pivot conversation; deferred 2026-05-04).
- Marginalia (Pass 7, separate session).
- Pinboard (separate session).
- Any backend simulation, LLM, or prompt changes.
- Removal of `frontend/map.js` — kept as `?flat=1` fallback until the globe is proven.
- Any test reorganization — frontend has no module system, that's acknowledged tech debt out of scope here.

---

## PHASE 2.8 — The corridor manuscript (CANCELLED, 2026-05-07)

> **Status: cancelled and rolled back.** Phase 2.8 shipped a 3D corridor as the primary manuscript view across 2026-05-04 to 2026-05-07. It worked technically (TubeGeometry threads, draggable pages, persisted board state) but failed the design intent: the player had to fly a 3D camera to read paragraphs of text, and the spatial metaphor obscured rather than enhanced the reading experience. Player verdict: "lets get this game finished e2e." On 2026-05-07 the entire corridor was deleted (corridor.js, the WebGL canvas, body class, ~290 lines of CSS, the `WorldState.board_state` and `cut_threads` fields, the `/board` endpoint, and `tests/test_board_endpoint.py`).
>
> **What replaced it:** Phase 2.9 — a flat 2D pinboard panel beside the legacy scrollable manuscript. The depth-stack from Phase 2.6 (z-recession on past turn-blocks) **stays alive** as the legacy manuscript's recession metaphor; only the *corridor* surface and its persisted state were deleted.
>
> **What was kept:** the globe and war-table from Phase 2.6 stayed (those are good 3D surfaces — the map is a place; the manuscript is text). Three open questions on Phase B (cut semantics, persistence model, NPC memory consistency) carry forward to Phase 2.10 unchanged — the simulation-rewinds-when-cut decision is still pending.
>
> **Lesson:** 3D is the right metaphor for the world (globe, war-table) and the wrong metaphor for the run record. The chronicle reads flat; the player's own annotations are spatial. That split is what Phase 2.9 ships.

---

## PHASE 2.9 — The pinboard

**Goal:** Replace the failed 3D corridor with a flat 2D pinboard that lives next to the legacy scrollable manuscript. The player highlights text in the manuscript, the highlighted passage becomes a pin on the right-hand panel, and the player drags / connects / cuts pins as they curate their own reading of the run. Spatial interaction without flying a camera through paragraphs.

**Why this exists:** Phase 2.8 proved that forcing 3D camera control on text reading hurts more than it helps. Phase 2.9 keeps the manuscript flat (where it should be) and gives the player a separate, lightweight, deterministic surface for the spatial work. **The manuscript answers what happened; the pinboard answers what the player thinks it means.** Design intent in [manuscript-as-artifact.md](manuscript-as-artifact.md).

This phase ships in two halves:
- **Phase A — quiet pinboard** (this round). Player highlights, pins, drags, draws connections, cuts. No system-proposed connections. No LLM call. Pure DOM + SVG.
- **Phase B — propose / agree / edit / reject + before/after** (next round, Phase 2.10). System auto-proposes connections from `PlayerView`-only data (information-as-geography: nothing the character couldn't plausibly know). A new Gemini call site (`connection_proposal`) generates the before/after preview text. Player agrees, edits the label and the meta, or rejects. **Simulation rewinds remain blocked by the same three open questions** (carried forward from Phase 2.8 Phase B); the propose/edit flow ships without them.

### What exists at the end of Phase 2.9 Phase A

- **Pinboard panel** — vanilla DOM + SVG, no Three.js. Always visible, fixed 60/40 split (manuscript left, pinboard right). Pins are absolutely-positioned cards; connections are SVG `<line>` elements that update live as the player drags pins.
- **Pin-by-selection** — native `selectionchange` listener on `#manuscript`. After 150ms of stable selection (>3 chars), a small **Pin this** floater appears near the selection. Click → POST `/api/run/{id}/pin` → server classifies the pin's `source_confidence` (observed / told_by / rumor / inferred) by reading `PlayerView` for the source turn → returns the classified pin → frontend renders it on the panel.
- **Player-perspective classification.** Pin `source_confidence` is the first persisted-state field in CHRONOS that explicitly encodes "what the character knew at the time of recording" rather than ground truth. The pinboard renders each pin's border style by confidence, so the player sees uncertainty as soon as they pin (solid = observed; dashed = told by an NPC; dotted = rumor; faint = inferred from atmosphere/narration). See `open-questions.md` Phase 2.9 entry.
- **Drag, connect, cut.** Drag any pin to reposition (persists to `WorldState.pins[].position`). Click pin A then pin B → a player-drawn connection. Click any connection → `cut: true` (persists; Phase B / 2.10 simulation rewinds still blocked).
- **Persistence.** New `WorldState.pins: List[Pin]` and `WorldState.pin_connections: List[PinConnection]` fields. New `POST /api/run/{id}/pinboard` endpoint with partial-update semantics. New `POST /api/run/{id}/pin` endpoint that creates+classifies a pin. Old `/board` returns 410 Gone with a message pointing at `/pinboard`.
- **3D corridor deleted.** `frontend/corridor.js`, the corridor canvas/container, the `chronos-corridor-manuscript` body class, ~290 lines of corridor CSS, the `WorldState.board_state` and `cut_threads` fields, the `/board` endpoint, and `tests/test_board_endpoint.py` are removed in this same commit.

### Success criteria

- [ ] On a fresh run, the manuscript renders normally and the pinboard panel appears empty on the right.
- [ ] Selecting >3 chars of manuscript text for >150ms shows a "Pin this" floater. Clicking it creates a pin server-side and renders it on the pinboard.
- [ ] Pins render with the correct `source_confidence` border style (solid/dashed/dotted/faint) based on what the player's character could know about the source text.
- [ ] Pins drag smoothly; positions persist across reload.
- [ ] Player can draw a connection (click pin A, click pin B) and cut a connection (click the line).
- [ ] No regression in legacy manuscript behavior (memory decay, hover-recover, depth-stack recession, inner thought, observation mode, erasure).
- [ ] Old runs with `board_state` / `cut_threads` load cleanly via Pydantic `extra="ignore"` and the next save rewrites without them.
- [ ] No 3D corridor code paths fire on any URL combination.

### Definition of success

After playing 10 turns, the player has a pinboard with 4–8 pins they curated themselves, several connections they drew, and a clear visual sense of "what mattered to me in this run." The manuscript reads cleanly on its own; the pinboard reads cleanly as the player's working notes. **Reading and curating are two distinct surfaces, and both feel right.**

### How to verify

1. **Build & run.** Manuscript renders; pinboard panel appears empty.
2. **Pin creation.** Select a passage of text; "Pin this" floater appears within 200ms; click it; pin lands on the panel.
3. **Confidence classification.** Pin a passage from an NPC's speech (told_by); pin a passage from the player's first-person turn (observed); pin a passage from an ambient_activity description (rumor). Confirm the pin border styles differ visibly.
4. **Drag.** Drag any pin to a new position; reload; pin is in the new position.
5. **Connect.** Click pin A, click pin B; a line appears. Reload; the line is still there.
6. **Cut.** Click the line; it visually marks cut. Reload; cut state persists.
7. **Old run migration.** Load a session created during Phase 2.8 (board_state + cut_threads); confirm no 500 error; the next save rewrites the row without those fields.
8. **`/board` 410.** `curl -X POST /api/run/<id>/board` returns 410 with the message redirecting to `/pinboard`.

### What is explicitly NOT in Phase 2.9

- **Auto-proposed connections.** Phase 2.10. Plumbing is ready (`PinConnection.kind = "auto"` is a valid value), but no proposer fires.
- **LLM-generated before/after preview.** Phase 2.10. New Gemini call site, requires explicit user review of the prompt template per `chronos-model-tier.mdc`.
- **Connection labels.** Phase 2.10 — player-drawn connections in 2.9 have no label.
- **Connection cuts that affect simulation.** Same three Phase B open questions still block; carried forward from 2.8.
- **3D pinboard.** No.
- **Drag-to-resize the divider.** Fixed 60/40 split; future commit can add resize.
- **Pinboard search / filter.** Future commit.
- **Pin-from-arbitrary-text** (no manuscript selection). Pins are always rooted in a manuscript passage in 2.9; "free notes" is a future commit.

---

## PHASE 2.10 — The pinboard becomes active (propose / agree / edit / reject)

**Goal:** The pinboard stops being a quiet curation surface and starts proposing connections the player adjudicates. After each turn (gated), the system suggests one or more links between same-turn pins; the player agrees, edits, or rejects.

**Why this exists right after 2.9:** Phase 2.9 shipped the pinboard as a *passive* surface — the player can pin and connect, but the system never participates. That made the pinboard feel inert: a notepad, not a sub-agent. Phase 2.10 wakes it up. The pinboard now reads what you pinned and offers an interpretation, which you accept, rewrite, or refuse.

### What exists at the end of this phase

- **Auto-proposer endpoint.** `POST /api/run/{id}/pinboard/propose_connections`. The frontend triggers it after each turn when the gate condition is met (≥3 unconnected pins, ≥2 turns since last proposal). Server walks same-turn pin pairs (no cross-turn fishing), skips already-connected and tombstoned pairs, capped at 8 LLM calls per request. Each surviving pair gets one Gemini Flash Lite call for a one-sentence claim.
- **New `PinConnection.kind = "auto_proposed"`** state, distinct from `player` (solid emerald) and `auto` (solid amber). Renders as a faint dashed yellow line with a small `?` marker at the midpoint.
- **Adjudicate popup.** Click an `auto_proposed` line or its `?` marker → popup at the line midpoint showing the claim + Agree / Edit / Reject buttons. Esc closes; Enter agrees (when not in textarea).
- **Three transitions.** Agree → `kind` becomes `auto`, label preserved. Edit → `kind` becomes `auto`, label replaced with player text, `meta.was_edited = true`. Reject → connection hard-deleted AND pin pair tombstoned in `WorldState.rejected_pin_pairs` so the pair is never re-suggested.
- **New `WorldState.rejected_pin_pairs: List[List[str]]`** for tombstones. Cascade-dropped on pin delete. Reverse-pair equivalence (`(A,B)` and `(B,A)` count as the same rejection).
- **New `WorldState.last_propose_turn: int`** so the gate can read it.
- **New LLM call site `connection_proposal`** (Gemini Flash Lite). Per `chronos-model-tier.mdc` flagged for explicit review; prompt template in `prompts/connection_proposal.md`. Per-call ~$0.00006; per typical 10-turn run ~$0.0001–$0.0003. Far below cost cap.
- **NoOp / failure path.** If Gemini returns NoOp / circuit-breaker is open / JSON parse fails → empty claim → no proposal written for that pair → pinboard never blocks → no banner, no error.

### Success criteria

- [ ] After playing 6+ turns with ≥3 same-turn pins on the pinboard, a faint dashed yellow line with a `?` marker appears between two of them.
- [ ] Clicking the line or marker opens an adjudicate popup with the claim text and three buttons.
- [ ] Agree → line turns solid amber; reload → line is still solid amber.
- [ ] Edit → textarea replaces claim; Agree saves the edited text + `meta.was_edited`. Reload preserves both.
- [ ] Reject → line vanishes; same pair never re-proposed even after 5+ further turns.
- [ ] Cross-turn pin pairs are NEVER proposed.
- [ ] Already-connected pairs (any kind, any cut state) are NEVER proposed.
- [ ] Per-run cost contribution from `connection_proposal` stays under €0.001 across a 30-turn playtest.
- [ ] Phase 2.9 success criteria still pass (no regressions on pin create / drag / connect / cut / restore).

### Definition of success

The pinboard now feels like a co-author. The player pins what mattered to them; the system reads those pins back and proposes how they relate; the player adjudicates. The flow is honest: the system says "this is what I think connects them," and the player has full authority to accept, rewrite, or refuse.

### What is explicitly NOT in this phase

- **Simulation rewinds when a player edits a connection.** Phase B. Still blocked by three open questions in `open-questions.md` ("Phase 2.10 Phase B blockers"). Carried forward unchanged from cancelled Phase 2.8 Phase B.
- **Counterfactual / before-after narration.** Claim-only output. The "what would change without this connection" framing was deliberately rejected because it would lie about Phase B (the simulation isn't actually going to rewind).
- **Cross-turn proposals.** Same-turn-only scope rule.
- **Multiple pending proposals visible at once.** One popup at a time.
- **Proposal history / audit log.** Rejected pairs are tombstoned; we don't keep a per-rejection log.
- **Player-typed labels on player-drawn lines.** Only system-proposed lines have labels in 2.10. Free-form labeling is a future commit.

---

## PHASE 3b — The diorama (stylized 3D scenes for major events)

**Goal:** When the player makes a high-significance decision (`parsed_action.significance_score >= 0.85`), a **stylized 3D vignette** is inserted inline in the manuscript, between turn-blocks. Silhouette characters, low-poly setting, slow camera orbit, amber-on-black palette. Reads like a memory — not a record of what happened, but the character's recollection of what mattered. The diorama is rendered live in WebGL (Three.js, already loaded for globe + war-table). No external 3D assets; geometry is built procedurally from primitives. The scene **spec** (location_kind, characters, camera, mood) is generated by a new Gemini Flash Lite call site (`scene_director`) reading the turn data; the **renderer** is deterministic given the spec.

**Why before Phase 3a:** Phase 3a's photoreal FLUX stills are technically expensive (60s/image, asset-pipeline-heavy) and visually saturated (a photoreal still tells the player exactly what they saw). Phase 3b is cheaper (no GPU image gen, no 60s wait), composes more cleanly with the manuscript's existing typography, and asserts a different design statement: **the player is a lens, not a camera.** Stylized geometry rendered live is the right metaphor for memory; photoreal stills would be the right metaphor for a journalistic chronicle, and CHRONOS is not that.

### What exists at the end of this phase

- **`Diorama` Pydantic model** in `backend/world_state.py`: `{id, source_turn_id, location_kind, characters: List[CharacterFigure], camera: CameraSpec, mood: MoodSpec, created_at}`. Each `CharacterFigure` has a kind ("standing", "robed", "kneeling", "horseback", "seated") and a position; `CameraSpec` has an orbit type ("low_orbit_slow", "high_static", "dolly_in"); `MoodSpec` is a small enum + amber/silver palette toggle.
- **`WorldState.dioramas: List[Diorama]`** with a cap of 30 per run (large but bounded; the 0.85 threshold means most runs hit 1-3).
- **POST `/api/run/{id}/diorama/{turn_id}`** endpoint. Reads the turn-log row, calls `generate_scene_spec` (the new LLM call site), saves the diorama to state, returns it. Refuses on hard-cap; refuses if a diorama already exists for the turn (idempotent).
- **New LLM call site `scene_director`** (Gemini Flash Lite, ~$0.0001 per call, ~$0.0002 per typical run). Prompt template in `prompts/scene_director.md`. NoOp fallback returns a minimal default spec so the renderer can still place a generic silhouette diorama if Gemini is down.
- **`frontend/diorama.js`** — the renderer. Three.js scene per inset. Procedural geometry library (4-6 character archetypes, 6-8 setting kits) built from primitives. Slow auto-orbit when not interacting; drag-to-orbit override; no other interactivity in 3b.
- **Inline manuscript placement.** When a turn fires with significance >= 0.85, app.js POSTs `/diorama/{turn_id}`, gets back the spec, and mounts a `<div class="diorama-inset">` between turn-blocks. The inset is ~250px tall, full reading-column width, scrolls with the manuscript. Smooth fade-in.
- **Composition with existing systems:** dioramas tint with `observation-muted` filter post-death. Memory decay does NOT yet degrade older dioramas (queued for Phase 6 polish; flagged honestly). Pinning a diorama as a `Pin` (composing with Phase 2.9/2.10) is queued for Phase 3b.5.

### Success criteria

- [ ] A 10-turn run with at least one significance-0.85+ action shows exactly one diorama inset in the manuscript at that turn, between turn-blocks.
- [ ] The diorama auto-orbits slowly (~5° per second). Dragging the canvas overrides the orbit; releasing the drag resumes the auto-orbit after 2s of idle.
- [ ] Silhouettes are recognizable as characters (head + body + limbs) but rendered black-on-amber so they read as figures, not portraits.
- [ ] The location kit matches the turn's location category (cloister vs market vs throne hall vs road).
- [ ] Reload preserves the diorama (it's persisted in WorldState; the renderer rebuilds the scene from the spec).
- [ ] No diorama is rendered for low-significance turns (filler, ambient).
- [ ] The hard cost cap refuses new dioramas: `state.cost_cap_state == "hard"` returns 402.
- [ ] Per-run cost contribution from `scene_director` stays under €0.001 across a 30-turn playtest.
- [ ] Phase 2.9 and 2.10 still pass (no regressions on pin create / drag / connect / cut / propose / agree / edit / reject).

### Definition of success

The player makes a hard decision; a small 3D scene appears between paragraphs of their manuscript, glowing amber, characters in silhouette around them. The camera circles slowly. They drag to look from a different angle. They scroll past it and the next turn-block continues the text. The diorama is a **memory glued in** — the run remembers itself, in scenes the character could plausibly have lived.

### What is explicitly NOT in Phase 3b

- **Photoreal stills.** Phase 3a stays deferred; this is a different visual language.
- **Generative 3D from text.** No NeRF, no text-to-3D model. Geometry is procedural from primitives.
- **Memory decay on dioramas.** Phase 6 polish item; flagged.
- **Diorama-as-pin.** The pinboard does not yet accept diorama references; future commit.
- **Per-character animation.** Silhouettes are static in their poses; the camera moves, not the figures.
- **Audio.** No.
- **External 3D models / GLTF.** Everything is built in Three.js geometry constructors. Zero asset pipeline.

### How to verify

1. **Build & run.** Submit a turn with high significance (e.g. "betray the praetor to the legions"). Confirm a diorama appears inline in the manuscript, between turn-blocks.
2. **Auto-orbit.** Watch the diorama for 5 seconds. Confirm the camera moves slowly around the scene.
3. **Drag override.** Drag the diorama. Confirm the camera follows the cursor; release; after ~2s, the auto-orbit resumes.
4. **Threshold gate.** Submit several low-significance turns ("I look around"). Confirm no new diorama is added.
5. **Reload.** Refresh the page. Confirm the diorama is still there.
6. **Cost.** Check chronosDiag() for the run's cumulative cost. Confirm scene_director's contribution is in the noise.
7. **Hard cap.** Force `state.cost_cap_state = "hard"` (manual SQL). Confirm POST `/diorama/{turn_id}` returns 402.

---

## PHASE 3a — Photoreal scene illustrations (FLUX, deferred)

**Status (2026-05-07):** Deferred behind Phase 3b. Originally Phase 3; renamed when 3D dioramas (Phase 3b) was elevated ahead of it. The POC, the candidate model selection, and the design intent below all stand; we just aren't shipping this yet. Phase 3b ships the *stylized 3D diorama* layer first because it composes more cleanly with the manuscript's existing rhythm and earns its weight at lower technical risk. The two visual languages — photoreal first-person stills (3a) and stylized 3D dioramas (3b) — are **not redundant**; they would compose in a final product (3a is "what the character is seeing right now"; 3b is "what they are remembering"). See visuals.md for the rule.

**Goal:** When the player experiences a major event — their character's defining moment, an encounter with a key NPC, a turning point in the run — a diffusion-generated scene illustration renders what they are experiencing.

### What exists at the end of this phase

- A scene illustration pipeline: when a major world event is flagged, a prompt is constructed from the world state (era, location, character archetype, event description, time of day, mood) and sent to a diffusion model
- The illustration renders in the UI alongside the narrative text for that event — not replacing text, augmenting it
- Illustration style is consistent within a run (same style prompt anchored to the era)
- Illustrations are generated for: run-start scene (who you are, where you are), significant player actions, first encounter with a major NPC, player death scene, and the final memory-fade moment
- No illustration on every turn — reserved for moments of narrative weight

### Success criteria

- [ ] Illustrations feel era-appropriate and grounded in the scene, not generic fantasy art
- [ ] The style is consistent within a single run
- [ ] Illustrations enhance the emotional weight of key moments — they don't interrupt the flow
- [ ] The death scene and memory-fade illustration are the most impactful in the run

### Definition of success

**Flagged** narrative moments produce **one** on-model illustration **alongside** text, never replacing it. Triggers fire for **start**, **heavy** actions, **first** major NPC meeting, **death**, and **final memory fade** — not every turn. **Style** (prompt anchor) is **stable** within a run and **period-flavored** (not default “generic fantasy stock”).

### How to verify

1. **Trigger audit** — Log every turn: `illustration_trigger` true/false + reason. Full run should hit **exactly** the intended trigger classes (no spam; no misses on forced golden path).
2. **Golden path replay** — Scripted run: assert **5** key frames (start, 1 big action, first major NPC, death, fade) each produce **image URL/blob** in UI within SLA (document seconds).
3. **Style consistency** — Blind sort: **5** images from one run vs **5** from another run (different seed); raters prefer within-run pairing for style (or embed cosine similarity if pipeline supports).
4. **Era grounding** — Checklist per image: costume/architecture/mood vs era label; fail if majority anachronistic (designer rubric).
5. **UX** — Narrative readable **without** scrolling past image; image load failure **must not** block text (error state).
6. **Cost / latency** — Log generation time + \$ per run; stays within project budget assumptions (see **MODEL TIER POLICY** for LLM; diffusion budget set at Phase 3 kickoff).

### Technical note (candidate selected 2026-04-22, not yet integrated)

The provider decision has been narrowed by a POC in `scripts/imagegen_poc/` (run 2026-04-22). Candidate: `mflux` on Apple Silicon with FLUX.2 Klein 9B distilled, 4 steps, Q8 quantization. Measured at ~60 seconds per image at 1024x1024 on M4 Max 64 GB, with zero content filter and $0 per-run cost. All 10 CHRONOS scene types generated successfully.

This is a **soft-lock**, not a final commit. Final commitment happens at Phase 3 integration kickoff because production integration can reveal issues invisible to a 10-image POC: concurrent load with active Ollama NPC inference, seed stability, memory pressure, etc.

Named fallback if integration reveals blocking issues: `fal.ai` Flux 2 Dev API at ~$0.025 per image. A full run of ~6 images costs ~$0.15 via fallback. This violates the local-first principle but stays within acceptable cost bounds.

Design rules for CHRONOS imagery (POV, honest bodies, prompt template, style) are documented in [visuals.md](visuals.md). Refer to that doc when constructing the trigger pipeline and prompt templates at Phase 3 kickoff.

---

## PHASE 4 — Historical Knowledge Engine v2

**Goal:** The simulation's historical reasoning improves significantly. The HKE moves from pure RAG toward a model that has internalized historical causal patterns.

### What exists at the end of this phase

- Synthetic Q&A dataset extracted from accumulated run logs: `(action, historical context, consequence)` triples
- Dataset formatted as structured causal questions: "In [era/region], if [actor type] does [action], what plausibly follows?"
- A fine-tuned or heavily prompted model trained/evaluated on this dataset
- HKE queries routed to the fine-tuned model for primary consequence generation, with RAG as fallback for rare/edge contexts
- Expanded era corpus: all eras in the starter set fully ingested, plus additional eras added based on what players have actually encountered
- Consequence quality noticeably higher than Phase 1 — responses are more specific to social class, geography, and political moment

### Success criteria

- [ ] Consequence generation is measurably more historically specific than Phase 1 RAG-only output
- [ ] The fine-tuned model handles the 10 most common action types across the most-played eras without needing RAG retrieval
- [ ] Edge cases and rare eras still fall back gracefully to RAG without breaking immersion

### Definition of success

**Primary** consequence generation runs through the **fine-tuned / heavy-prompt** path for **common** actions in **common** eras; **RAG** remains the **safety net** for rare inputs. Improvement is **measurable**: same golden prompts score higher on historical-specificity rubric than Phase 1 baseline. Dataset + training/eval **artifacts** exist and are **versioned**.

### How to verify

1. **Golden prompt set** — Freeze **N** prompts (e.g. 30–50) covering **10** common action verbs × **top** eras; run **Phase 1** (RAG-only) vs **Phase 4** pipeline; **blind** human rubric or LLM-judge (document which) scores specificity (class, geography, politics).
2. **Router behavior** — For each top action type, assert **no RAG call** (or “optional”) on happy path — log router decisions; spot-check **10** traces.
3. **Edge / rare** — Construct **10** rare-era or odd-action prompts; confirm **RAG path** fires and output stays in-world (no modern anachronism escape hatch).
4. **Dataset integrity** — Tuple fields `(action, historical context, consequence)` validated schema; train/val split; **no** PII from real users if logs used (policy check).
5. **Regression suite** — CI job: golden set + max latency + cost per **100** calls within budget envelope.
6. **Ablations** — One run with FT model disabled (fallback only): quality drops, proving FT contributes (smoke, not full science).

---

## PHASE 5 — Full Era Coverage + World Depth

**Goal:** The game feels complete. All planned eras are playable. The world has depth — NPCs have relationships with each other, not just with the player. The character relationship graph is rich enough that indirect influence is possible.

### What exists at the end of this phase

- All 20 era buckets from the design doc are fully supported with ingested corpus and tested character archetypes
- NPC-to-NPC relationship graph: characters have opinions of each other, alliances, rivalries — the player can influence these indirectly through their actions
- The faction emergence system is robust: enough character relationships exist that de facto factions feel real and discoverable
- Run length and pacing feel intentional — a run has a natural arc regardless of how the player acts
- The memory decay curve is tuned: runs end at the right moment, not too fast, not dragging
- NPC interaction logging — every NPC-to-NPC interaction logs what information was exchanged, not just that an interaction occurred. This is the raw material for the Information Provenance Graph. Must be captured from the start of Phase 5, not retrofitted.
- Information Provenance Graph — replaces archetype/geography filtering as the primary mechanism for what characters know. Built on top of the NPC social graph. Each significant event has a transmission record. Ground context generation traverses the graph rather than querying the Events DB directly.

### Success criteria

- [ ] Any of the 20 eras produces a run that feels historically distinct from the others
- [ ] Players can discover and influence NPC-to-NPC relationships without being told they exist
- [ ] The average run has a felt narrative arc — setup, escalation, consequence, fade

### Definition of success

All **20** era buckets are **playable** with ingested corpus + smoke-tested archetypes; a naive player can tell eras apart **without** reading filenames. **NPC–NPC** edges are real in state (not staged copy): indirect actions **move** relationship metrics that surface **only** through POV/travel, matching design (no faction UI). **Pacing** matches resolved **session-length** target from open questions: runs have a **felt** arc and memory fade **neither** ends at Turn 5 **nor** drags past the target band (document target in completion log).

### How to verify

1. **Era matrix** — One **full** run (or standardized midpoint) in **each** of **20** buckets; checklist: distinct political flavor + voice + map/border correctness (where applicable). **Fail** if ≥2 buckets feel interchangeable in blind A/B.
2. **NPC–NPC graph** — Inspect save/state: **≥** threshold of non–player edges per region (define threshold at Phase 5 kickoff). Player action with **no** direct talk to C still shifts C’s opinion of D (logged delta); confirm via **two** POVs, not a debug panel in shipping UI.
3. **Factions emergent** — Playtest script: **no** explicit “faction” words in UI; after **N** turns, **3/3** blind readers infer at least one **coherent bloc** from **dialogue-only** exports.
4. **Indirect discovery** — New player (!in-house): **60+ min** session; can articulate one **third-party** relationship they **inferred** without tutorial (qualitative pass/fail).
5. **Arc & pacing** — Log turns to death+fade for **10** runs; distribution should match session-length policy (e.g. median ± band defined when **Session length target** is closed). **Memory curve** A/B: old vs tuned decay; designer sign-off on “too fast / too slow / right.”
6. **Regression** — Phase **1–4** golden paths still pass; cost per run still in **MODEL TIER POLICY** envelope.
7. **Cost & perf** — Stress: **max** NPC count × **20** eras corpus **index** builds in CI; load-time budget documented.

---

## MODEL TIER POLICY (Agreed — applies to all phases)

**Principle:** Gemini for all LLM calls. A run should cost cents, not dollars.

### All-Gemini runtime (2026-04-23)

The historic fast/quality tier split has been retired. Ollama is no longer used at runtime.
All call sites route to `call_llm()` which dispatches to Gemini
(`CHRONOS_GEMINI_MODEL`, default `gemini-2.5-flash-lite` -- the stable / GA model that
matches the pricing constants in `backend/config.py`. Set the env var to
`gemini-3-flash-preview` if your AI Studio key has preview access, but update the
pricing constants in the same change so cost accounting stays honest).

The `tier` parameter on `call_llm` is accepted for backward compatibility but is a no-op.
Do not add new `tier` routing logic.

Call sites:

- `action_parser` -- NL to structured JSON action
- `autonomous_action_light` -- one-sentence offscreen NPC activity
- `autonomous_action` -- full NPC autonomous actions (active tier, player skip-turn, arrival)
- `death_check` -- short structured JSON
- `region_knowledge` -- one-line map-click note
- `npc_perception` -- one-line NPC hover note
- `historical_context` -- 2-3 sentence passage explainer (map/text highlight)
- `memory_fade` -- one-sentence fade framing each observation turn
- `npc_pov` -- NPC reactions to player actions (highest-impact prose in the game)
- `character_gen` -- player + 8-15 NPCs at run start (concurrency capped by semaphore)
- `ground_context` -- HCE ground context at run start and on arrival
- `erasure` -- final narrative passage when the run ends (fires exactly once per run)

Build-time only (not runtime): Events DB population script; embeddings (`nomic-embed-text`, local).

### NoOp fallback

When Gemini is unavailable, all calls return `("...", cost=$0)` and the turn continues
with degraded prose. This keeps turns alive on transient failures.

NoOp triggers when:

- `GEMINI_API_KEY` is unset (ERROR log)
- the Gemini circuit breaker is open (3 failures in 60s -> 5 minutes open; WARNING log)
- a single Gemini call raises after retries (WARNING log; circuit records the failure)

### Current runtime status (2026-04-23)

All-Gemini provider active (default `gemini-2.5-flash-lite`; `gemini-3-flash-preview`
is opt-in via the env var when the key has preview access). The two-tier
(Gemini quality + Ollama fast) configuration is retired. Ollama is no longer in the
runtime path. The two-tier migration itself replaced the previous Ollama-only architecture
because 70b auto-selection on capable hardware produced ~6 min per turn, blocking
playtest-driven iteration. The all-Gemini migration followed because Ollama's fast-tier
calls were the cause of `_parse_error` failures on every player action in the
2026-04-24 playtest.

Concurrency: `GEMINI_MAX_CONCURRENT_CEILING = 20` (hard constant, cannot be exceeded
by env var). `CHRONOS_GEMINI_MAX_CONCURRENT` default 15. Paid tier (300 RPM) absorbs this.

### Per-run cost ceiling

- **~EUR 0.022 median per 10-turn run** (gemini-2.5-flash-lite pricing: $0.10 / $0.40 per M input/output)
- **EUR 1.00 soft cap** -- UI banner, dismissible, once per run; turns continue
- **EUR 2.00 hard cap** -- turn endpoints reject further advances with `402` + `code: cost_cap_hard`; player can still observe the world and end the run manually

Internal accounting is USD (Gemini bills USD). EUR is rendered via `config.USD_TO_EUR`
(default 0.92, update from ECB reference rate periodically; if EUR/USD moves by +-5%,
recompute caps or switch accounting to USD).

---

## FINAL PRODUCT

**What the game is at completion:**

A single-player, turn-based historical simulation. You are assigned a random minor figure in a random era after 0 AD. You make unconstrained macro decisions in natural language. The game never tells you what to do. The world responds based on historically grounded AI reasoning. The only way to understand your impact is to travel and find the people you affected. When you die, the world forgets you slowly. Every run is unique. The map is real. The illustrations are generated from your specific moment. The history is not scripted.

**The stack at completion (as agreed):**

- Web app, single player
- Leaflet + GeoJSON historical maps
- RAG + fine-tuned HKE for historical consequence generation
- Diffusion-generated scene illustrations for major moments
- Full era coverage: post 0 AD, 20 era buckets minimum

**Current stack (as built through Phase 2.5):**

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | Vanilla JS + HTML + Tailwind CSS (CDN) | No framework |
| Map | Leaflet 2D + GeoJSON | Natural Earth coastlines + aourednik historical borders |
| Backend | FastAPI + Uvicorn | Python 3.11 |
| Database | SQLite (WAL mode, aiosqlite) | Sessions, Events DB, turn logs (with `turn_cost_usd`), consequence queue |
| Embeddings | ChromaDB + nomic-embed-text | Local, free |
| LLM | Gemini (`CHRONOS_GEMINI_MODEL`, default `gemini-2.5-flash-lite`; `gemini-3-flash-preview` opt-in if preview access) via `google-genai` | all call sites; ~EUR 0.022 median per 10-turn run |
| LLM fallback | NoOp ("...") | `GEMINI_API_KEY` unset or circuit breaker open (3 fails/60s -> 5 min); keeps turns alive on transient failure |
| Cost ceiling | €1.00 soft / €2.00 hard per run | Tracked in USD, displayed in EUR; persisted in `WorldState.cumulative_cost_usd` and `turn_logs.turn_cost_usd` |

---

## OPEN QUESTIONS THAT AFFECT THE ROADMAP

> These must be resolved before the phase they impact begins.

- **Session length target** — affects pacing design in Phase 5. A 30-minute run and a multi-day run are fundamentally different.
- **Diffusion model provider** — affects Phase 3 architecture. Candidate selected 2026-04-22 (mflux + FLUX.2 Klein 9B distilled, POC in `scripts/imagegen_poc/`). Final commit at Phase 3 kickoff. See [visuals.md](visuals.md) and Phase 3 Technical note.
- **NPC relationship graph granularity** — affects Phase 5 scope significantly. Resolve before Phase 5 begins.

**Closed in Phase 2.6 kickoff (2026-05-04):** the 3D globe (re-opened from Phase 2 cut) and the tilted relief / war-table view (closed from `open-questions.md` General). Both now in scope as Phase 2.6 (Spatial Substrate). Original Phase 2 cut reasoning for the globe is unknown to the re-opening session; recorded honestly in the Phase 2 completion log.

---

## Phase completion log

When a phase is **done** (all applicable **success criteria** met and verified — not only tasks checked off), add an entry under that phase.

Use this shape:

- **Completed:** YYYY-MM-DD
- **Success criteria:** Met / partial — one-line evidence
- **Planned vs actual:** what shipped vs what this doc predicted
- **Carryover:** risks or debt that affect the next phase

### Phase 0

- **Completed:** 2026-03-31
- **Success criteria:** All four met.
  - *Scaffolding end-to-end:* 85 automated tests pass (70 offline + 15 live with Ollama). Full path browser → FastAPI → action parser → world state mutation → NPC POV → UI runs without manual glue. Verified by 6-turn manual playtest.
  - *NPC POV generated:* Two NPCs (Lucius Gallus, centurion; Deacon Paulus, Christian deacon) respond every turn with substantive first-person perspectives.
  - *Historically plausible:* Gallus uses military framing, oaths by Roman gods, suspicion of civilians. Paulus frames events through Augustinian theology, divine judgment. No modern terms detected across 12 NPC responses in the manual playtest. Confirmed by automated anachronism check (live test).
  - *World state updates:* Turn counter, event log, NPC dispositions, and political tension all update correctly. LLM-judged `npc_impacts` allow indirect actions (e.g. hoarding grain) to shift dispositions of non-targeted NPCs. Verified by unit tests and live tests.
- **Planned vs actual:**
  - *Frontier parser:* Planned as frontier haiku/mini-tier. Shipped as local Ollama stub per user decision — frontier swap point clearly labeled in `backend/action_parser.py` and `prompts/action_parser.md`.
  - *Era:* Planned "evaluate at build time." Chose Roman Late Empire, 410 AD (Ariminum) — richest Gutenberg coverage (Gibbon, Ammianus Marcellinus, Augustine).
  - *Not originally planned but added:* (1) Story-so-far context in both prompts — NPC and parser are aware of full game history, not just last action. (2) LLM-judged `npc_impacts` in the action parser output — the model determines per-NPC sentiment (positive/negative/neutral) for every action, allowing disposition shifts for NPCs not directly targeted. (3) 85-test automated suite covering unit, integration (mocked LLM), and live (real Ollama) layers.
- **Carryover:**
  - Disposition model is richer than planned (LLM-judged impacts) but still uses a fixed shift ladder. Phase 1 will need more nuanced relationship tracking.
  - NPC responses occasionally exceed the 2-4 sentence prompt constraint. Prompt tuning or model-level enforcement needed.
  - All NPCs respond every turn (no travel gating) — correct for Phase 0 (everyone in same location), but Phase 1 must enforce geography-gated POVs.
  - Game state is in-memory only. Server restart resets everything. Phase 1 needs session persistence.
  - Python 3.9 on the build machine required `Optional[str]` instead of `str | None` for Pydantic models.

### Phase 1

- **Completed:** 2026-04-01 (rebuilt simulation-first), **Autonomous world simulation added:** 2026-04-06
- **Success criteria:** Core systems built and turn loop rebuilt to simulation-first architecture. Autonomous world systems added: 7-stage pipeline, NPC personality/needs, structural drift, probabilistic events, utility scoring, consequence queue, time-skip.
  - *Infrastructure:* 5 eras, character generation, travel, death/aging, memory decay, erasure, RAG/HKE v1, SQLite persistence (WAL mode, per-session locking), unified turn endpoint — all working.
  - *Simulation-first rebuild:* World simulates every turn via 7-stage pipeline (drift → consequences → events → NPC actions → player → narrative → save). Player input is one optional stage. NPCs act autonomously at all locations every turn via LLM calls. NPC perception endpoint built.
  - *Autonomous world systems (2026-04-06):*
    - NPC personality traits (ambition/compassion/courage/piety/pragmatism) generated from archetype ranges
    - 17 NPC needs that decay each turn with Maslow-style urgency curves
    - Event-driven need shifts with permanent trait changes
    - Scheduled consequence queue on WorldState (delayed effects fire on future turns)
    - Structural drift: tension spreads, dispositions drift to archetype baselines, needs decay, rumors propagate
    - Probabilistic world events: skirmishes, civilian unrest, trade disruption, refugee flight, merchant attraction
    - Utility scoring: NPCs choose actions based on needs vs situation; LLM narrates the decision
    - Time-skip endpoint: POST /api/run/{id}/skip advances 1-30 turns
    - Conflict resolution: archetype-priority when NPCs target the same entity
    - Expanded disposition chain (13 states) so all archetype baselines are reachable
    - 493 tests, 0 failures
  - *What was wrong initially:* Turn loop was player-centric (player acts, world reacts). Rebuilt to world-simulates-then-player-acts. See context/other/lessons-learned.md.
- **Planned vs actual:**
  - All mechanical systems shipped as planned.
  - The simulation-first architecture was not in the original plan — it emerged from playtesting feedback. The initial build felt like a text adventure, not a simulation.
  - NPC autonomy (travel, NPC-on-NPC interaction, ambient activity) added in the rebuild.
  - Two-step loading flow (era preview instant, characters in background) added to fix empty loading screen.
  - Autonomous world systems (personality, needs, drift, events, utility scoring, consequence queue) added 2026-04-06 — not in original Phase 1 plan but architecturally foundational.
- **Carryover:**
  - NPC autonomy needs playtesting — is 2-4 NPCs acting per turn at the player's location enough? Too many? Too few?
  - NPC-on-NPC interactions are generated but shallow — they name an interaction partner but don't track persistent NPC-NPC relationships yet (Phase 5).
  - Relevance filter for player action reactions may still need tuning.
  - Loading screen events/voices are hardcoded per era config — should eventually come from HCE Events DB.
  - Frontend has no skip/time-advance button yet — endpoint exists but no UI.
  - Utility scoring opportunities are hardcoded — may need era-specific opportunity sets.

### Phase 2

- **Completed:** 2026-04-01
- **Success criteria:** Core criteria met. Map loads for all 5 eras with correct borders. Player and NPC positions represented. Visited/unvisited marker distinction works from world state. Toggle works.
  - *Border drift* not tested (borders are static per era in Phase 2).
  - *Post-1886* not tested (no post-1886 eras in current set).
- **Planned vs actual:**
  - *3D globe* planned. Shipped as **2D Leaflet** per design session pivot. Globe/terrain deferred. **Re-opened 2026-05-04** as Phase 2.6 (Spatial Substrate). Original cut reasoning is unknown to the session that re-opened it; flagged honestly so future readers know.
  - *aourednik/historical-basemaps* confirmed as primary source. 5 files pulled, simplified, documented in sources.md.
  - *visited_locations* tracking added to world state model (not originally planned -- required for marker design requirement).
  - 27 map-specific tests + 126 total offline tests.
- **Carryover:**
  - Region knowledge on hover and event markers deferred to Phase 2.5 (HCE dependency).
  - Terrain view deferred to future phase (see open questions).
  - Border accuracy gaps documented in frontend/geo/sources.md (48-year gap for Black Death, 53-year for Constantinople).

### Phase 2.5

- **Completed:** 2026-04-21 (partial 2026-04-10, closed 2026-04-21)
- **Success criteria:** 5 of 5 met; criterion 5 met in plumbing with narrative propagation as carryover.
  - *Events DB coverage:* Met — 1,569 canonical events across 5 eras, minimum 152 per era (Viking Age), all far exceed the 20-event threshold.
  - *Region knowledge:* Met — endpoint returns character-filtered content, archetype affects output.
  - *Event markers:* Met — GET `/api/run/{id}/events/visible` ships Knowledge Matrix filtering and centroid resolution; frontend renders with type/tier-appropriate treatment. 97.2% of events resolve to a centroid.
  - *Ground context quality:* Met — NPC voices reference era-specific material conditions and rumors from Events DB.
  - *Historical divergence:* Met in plumbing. Detection fires end-to-end (verified by integration test against Sack of Rome 410), `state.historical_divergences` records the event, queued canonical consequences are invalidated. NPC POV and narrative do not yet read the divergence signal (new open question).
- **Planned vs actual:**
  - *Time-skip UI:* Added to frontend bottom bar — not originally in Phase 2.5 plan but fills the Phase 1 carryover.
  - *Loading screen events:* Preview endpoint now draws from Events DB instead of hardcoded config.
  - *Word definitions overlay:* Shipped.
  - *Event markers on map:* Shipped. Originally deferred pending coordinate resolution, closed in Fix 6 via centroid YAML + normalizer.
- **Closure pass (2026-04-21) — Fixes 1-6:**
  - *Fix 1:* Action parser canonical vocabulary. 17-type routing contract between parser and downstream. In-code ALIASES map normalizes known LLM synonym drift (inquiry → speak, barter → trade, etc.). Player-facing freedom unchanged.
  - *Fix 2:* Consequence dispatch refactor. If/elif chain replaced by dispatch table; every canonical action type at significance ≥ 0.5 now schedules at least one specific consequence. New `backend/event_vocab.py` centralizes event-type frozensets used by `npc_personality._detect_opportunities` and `world_events` rules. Divergence type_map expanded to cover 14 of 17 action types (speak, flee, other intentionally excluded).
  - *Fix 3:* `prompts/action_parser.md` constrained to canonical vocabulary with three few-shot examples. Live test assertion relaxed from exact-string match to structural invariant (conversational phrasings never route to hostile / travel / inaction).
  - *Fix 4:* Divergence verified end-to-end via integration test against Sack of Rome 410. Target-miss fallback added to hostile / betray / save handlers (rumor at player location, turn+2) so target-less high-significance actions never silently no-op. Two new open questions surfaced: narrative propagation and supersession strictness.
  - *Fix 5:* Word definitions overlay polish. Bottom-edge clamp in `positionAt()`, last-rect anchoring for multi-line selections via `range.getClientRects()`, captured-endpoint fallback for scroll-aware context panel positioning via live Node+offset reconstruction.
  - *Fix 6:* Event markers on map. `backend/geo/region_centroids.yaml` hand-curated centroid table, `backend/geo/centroids.py` loader with normalization fallback, GET `/api/run/{id}/events/visible` endpoint with Knowledge Matrix filtering, frontend renderer with type color / tier opacity / witnessed indicator / broad-region circle-only treatment. 97.2% region coverage (86.9% exact, 10.3% normalized, 2.8% dropped long-tail).
- **Carryover:**
  - ~~Ground context is static for the full run.~~ **Resolved** 2026-04-20.
  - ~~Event marker coordinate resolution unresolved.~~ **Resolved** 2026-04-21 (Fix 6).
  - ~~Word definitions overlay not started.~~ **Resolved** (shipped during Phase 2.5, polished 2026-04-21 Fix 5).
  - **New carryover (2026-04-21):** Divergence visibility to NPCs and narrative layer. Detection fires, state records, queue invalidates. POV prompts and narrative text do not yet see the divergence signal. Future narrative-propagation work.
  - **New carryover (2026-04-21):** Stage 2 supersession validation strictness. `_validate_consequence` accepts/rejects on shallow target-exists checks; deeper world-state divergence (e.g., "the siege you prevented no longer applies as a consequence source") is not modeled. Resolve alongside narrative propagation.
  - **New carryover (2026-04-21):** Prompt coverage gap. Fix 1 and 3 hardened only `prompts/action_parser.md`. The other ~10 prompts were never audited for similar vocabulary / output-shape drift resistance.
  - **New carryover (2026-04-21):** Byzantine Empire centroid is era-ambiguous. Current YAML entry is median-period (39.0°N, 32.0°E, 1200 km radius); geographically wrong for 5th-century events. Future ingestion with era-keyed centroid sub-entries would fix this.
  - **New carryover (2026-04-21):** `polity_context` column in `historical_events` is architecturally planned as a centroid-resolution fallback but NULL across all 1,569 rows. Dead code path until future ingestion populates it.

### Gameplay redesign: Addressed mode, NPC drift, character-study UX (2026-04-27)

Three changes shipped together based on post-playtest diagnosis ("feels like a chatbot"):

1. **Addressed mode (Change 1)** -- `prompts/npc_addressed.md` + `generate_npc_addressed`.
   When `parsed.target` names an NPC at the player's location, that NPC produces a
   direct reply (`reply` + optional `internal` thought) instead of a private monologue.
   All other nearby NPCs stay in Ambient mode (`npc_pov.md`). Net new calls: zero.

2. **NPC narrative drift (Change 3)** -- `current_preoccupation` field on NPC model,
   initialized at character_gen from per-archetype pools (`ARCHETYPE_PREOCCUPATIONS`
   in `npc_personality.py`), rotates every 6 turns via `tick_preoccupation_drift`.
   `$player_actions_toward_you` replaces verbatim `stored_povs` injection -- the NPC
   now sees a structured summary of what the PLAYER DID, not its own prior output.
   Self-plagiarism (wet boot, King Harald's hair) eliminated at the source.

3. **Character-study UX (Change 2)** -- Input placeholder: "What do you do, think, or
   say?" Opening narration: description-first, name subordinated as "Your name is X."

New prompt: `prompts/npc_addressed.md`. New schema: `NPCAddressedResponse`.
New NPC fields: `player_interactions`, `current_preoccupation`, `last_preoccupation_shift_turn`.
New test file: `tests/test_addressed_mode.py` (17 tests).

### Post-playtest audit fixes (2026-04-27)

Not a phase boundary -- cross-cutting quality fixes based on a structured playtest
audit of run `17565bdc41f7` (2026-04-24). Five problems diagnosed, five fixes shipped.

1. **Action parser routing confirmed (Fix 1)** -- `action_parser` confirmed Gemini-routed.
   The `test_action_parser_uses_local_ollama` test was stale after the all-Gemini
   migration; renamed and updated to assert Gemini config.

2. **NPC memory pipeline completed (Fix 2)** -- `stored_povs` (last 3) and
   `memory_of_player` float now injected into `npc_pov.md` as `$prior_player_interactions`
   and `$memory_level`. Previously both were collected but never consumed by any prompt.

3. **NPC voice retuned for Gemini (Fix 3)** -- `npc_pov.md` VOCABULARY RULES extended
   with explicit bans on similes, metaphors, and parallel literary structures. A BANNED
   phrases list targets patterns Gemini defaults to that llama3.1:8b did not produce.
   JSON markdown fence stripping added to `npc_engine.py` (Gemini wraps JSON in
   triple-backtick fences; llama did not).

4. **Frontend visual hierarchy (Fix 4)** -- Scene (ambient NPC activity) and Voices
   (NPC reactions to player) are now visually separated with section headers and
   distinct opacity levels. Fallback `era_description` placeholder is suppressed in
   the renderer.

5. **Scene context in NPC POV (Fix 5)** -- `generate_npc_pov()` now receives
   `this_turn_events` (other NPCs' ambient actions this turn, capped at 4). Each
   NPC's reaction can reference the shared scene without a dedicated weaver call.

**Test count:** 736 offline + 13 live = 749 total. 23 new tests added.
Zero regressions against the pre-fix baseline.

### Phase 2.6

*(in flight — kickoff 2026-05-04)*

### Phase 3

*(no entry yet)*

### Phase 4

*(no entry yet)*

### Phase 5

*(no entry yet)*
