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

**Goal:** A complete single run is possible from start to finish. Player is generated, makes unconstrained macro decisions, finds NPCs, dies, fades from memory, run ends. Everything is text. No map yet.

### What exists at the end of this phase

- **Total player agency:** No action menus, no suggestions, no hand-holding. The player types any decision at any scale. The game never tells the player what to do.
- **Macro decision scale:** Decisions operate at weeks/months/years — alliances, betrayals, revolts, economic manipulation, flight. Not bar conversations or item management.
- **Selective NPC reactions:** Not every NPC reacts to every action. The game decides whose perspective genuinely matters. Most actions produce 1-3 reactions, not a firehose.
- Run initialization: random era selected from a starter set of 5, player character generated with archetype + backstory
- 8–15 NPCs seeded across multiple locations with archetypes, social classes, and relationships
- Full turn loop: player types a decision → world responds → structured state + narrative layer both update
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

- [ ] A full run can complete from character generation to erasure without soft-locks
- [ ] At least 3 different eras produce runs that feel historically distinct
- [ ] NPC perspectives feel distinct from each other (archetype, social position, bias are evident)
- [ ] The player can type anything — the game handles it without breaking
- [ ] Only genuinely affected NPCs react to any given action (not everyone nearby)
- [ ] The death + memory fade mechanic lands emotionally — the ending feels like erasure, not a game over screen

### Definition of success

A **full run** is reproducible: new run, play until **last memory dies** without cheats. The player has **total freedom** -- any typed decision is interpreted and produces consequences, at macro scale. **Travel** gates POV: you cannot read distant NPC reactions without moving. **Selective reactions**: after a player action, only **relevant** NPCs respond (not all nearby). **RAG** answers world consequence queries for at least **5** ingested eras; **3+** eras are **playably** different in practice. Emotional bar: end state reads as **fade / erasure**, not a game over.

### How to verify

1. **Run lifecycle** -- Start 3 runs (different era seeds). Each: reach **player death**, then **observation** (travel OK, no influence), then **run end** when no character remembers PC. Log turn count; ensure no soft-lock.
2. **Eras** -- Play at least **3** distinct eras end-to-end; confirm corpus/RAG loads era-specific context.
3. **Player freedom** -- Enter **5** wildly different actions (flee the city, start a revolt, hoard wealth, forge an alliance, do nothing). All should parse and produce coherent consequences.
4. **Selective NPC reactions** -- After an action, count responding NPCs. Should be **1-3**, not the full list.
5. **NPC distinction** -- Same event, **3** NPCs with different archetypes: collect POVs **after** travel; qualitatively score bias/voice differentiation.
6. **Travel-gated POV** -- Without traveling to NPC B, **no** POV from B about a remote event; after travel, POV unlocks.
7. **Anachronism** -- Input modern phrasing; outcome narrative should **not** break fourth wall.
8. **RAG v1** -- For fixed query set per era, retrieval returns **non-empty** relevant chunks from Chroma.
9. **Death and memory** -- After death, verify memory fields decay over turns; last loss triggers **run end** and UI matches **erasure** framing.

### What is explicitly NOT in this phase

- Visual map
- Diffusion-generated scene illustrations
- Fine-tuned model
- Synthetic Q&A database

---

## PHASE 2 — The Map

**Goal:** The world becomes spatial and visible. The player can see where they are, where NPCs are, and how borders have shifted as a result of their actions and world events.

### What exists at the end of this phase

- Leaflet.js map integrated into the web UI
- Base physical layer: Natural Earth GeoJSON (coastlines, rivers, terrain) — static
- Historical border layer: `aourednik/historical-basemaps` GeoJSON, selected per era at run start
- Dynamic border layer: player-influenced and world-event-influenced border changes tracked as diffs on top of base
- City and location layer: era-appropriate points of interest, NPC locations shown on map
- Travel is now spatial: the player sees their position and moves on the map
- NPC locations visible as markers — clicking one shows their name and whether you have visited them
- The map updates visually each turn to reflect world state changes
- CShapes 2.0 integrated for eras post-1886

### Success criteria

- [ ] Map loads correctly for at least 3 different eras with accurate historical borders
- [ ] Player position and NPC positions are correctly represented
- [ ] Border changes from world events are visibly reflected on the map over the course of a run
- [ ] Travel feels spatial — moving across the map takes more turns than moving locally

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

- Diffusion illustrations
- Fine-tuned model
- Illustrated map aesthetic (Leaflet + GeoJSON only, no stylized tiles)

---

## PHASE 3 — Scene Illustrations

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

### Technical note (to be decided at build time)

The diffusion model provider and whether generation is local or via API is an open decision. Evaluate Stable Diffusion (local), ComfyUI (local pipeline), and available API options at the time this phase begins. The prompt construction strategy — how world state translates into a coherent image prompt — is the core design challenge of this phase and should be prototyped before full integration.

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

**Principle:** Frontier models are a last resort, not a default. A run should cost cents, not dollars.

**Local only (Ollama):**

- NPC POV generation — highest volume call, local model is sufficient
- Autonomous character behavior on skipped turns
- Narrative layer updates each turn
- Run initialization (character backstory, NPC seeding)
- Memory decay descriptions
- Historical consequence generation (RAG retrieval + local reasoning)
- Embeddings for vector DB (`nomic-embed-text`, free, local)

**Frontier model (haiku/mini tier only — cheapest available):**

- IO layer: parsing player natural language input into a structured action — one small call per turn, ~200 tokens, fractions of a cent
- That's it. Nothing else goes to frontier unless local consistently and demonstrably fails at a specific task, tested explicitly.

**Recommended local models:**

- `llama3.1:8b` — general reasoning, NPC voices, narrative
- `mistral:7b` — fast, good for high-volume per-turn calls
- `nomic-embed-text` — embeddings, completely free

**Cost target:** $0.10–0.30 per run maximum. If a run exceeds this, the architecture is wrong.

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

---

## OPEN QUESTIONS THAT AFFECT THE ROADMAP

> These must be resolved before the phase they impact begins.

- **Session length target** — affects pacing design in Phase 5. A 30-minute run and a multi-day run are fundamentally different.
- **Diffusion model provider** — affects Phase 3 architecture. Resolve at Phase 3 kickoff.
- **NPC relationship graph granularity** — affects Phase 5 scope significantly. Resolve before Phase 5 begins.

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

*(no entry yet)*

### Phase 2

*(no entry yet)*

### Phase 3

*(no entry yet)*

### Phase 4

*(no entry yet)*

### Phase 5

*(no entry yet)*
