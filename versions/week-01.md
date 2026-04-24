# CHRONOS — Week 1 Snapshot

**Date:** April 6, 2026
**Phases complete:** 0, 1, 2

---

## What exists

Turn-based text simulation. FastAPI Python backend, SQLite database, vanilla HTML/JS/CSS frontend. Player submits natural language input, world responds, NPCs react. Everything is player-triggered — nothing happens unless the player acts.

### Core loop

Player types → Action parser (local Ollama) converts to structured action → World engine simulates consequences → NPCs at player's location generate POV responses → Narrative returned to frontend → Player reads and types again.

### Built systems

- **5 playable eras:** Roman Late Empire (~410), Viking Age (~870), Crusader States (~1190), Black Death (~1348), Fall of Constantinople (~1453)
- **Run initialization:** Random era selection, Llama 70b generates player character with archetype + backstory, 8–15 NPCs seeded at starting locations
- **Turn loop:** `simulate_turn()` in `world_engine.py` — action parsing, NPC autonomous actions (but only when player acted), NPC POV generation, death check, narrative assembly
- **Death mechanic:** Hybrid aging + consequence. On death, player enters observation mode — input disabled, world continues, memory of player decays (0.0–1.0 per NPC). When last NPC forgets player, erasure sequence triggers.
- **Erasure sequence:** Final chronicle passage, "begin again?" prompt
- **3D globe:** Three.js sphere with Natural Earth coastlines, era-specific historical borders from `aourednik/historical-basemaps`, player marker, NPC markers with visited/unvisited distinction. Toggle with M key.
- **Historical borders:** GeoJSON from `aourednik/historical-basemaps`, 5 era border sets, `CShapes 2.0` for post-1886
- **RAG pipeline:** Gutenberg + Wikipedia texts chunked and embedded in Chroma with `nomic-embed-text`, used to ground NPC responses and consequence generation
- **HCE Events DB:** SQLite table of canonical historical events sourced from Wikidata SPARQL + Wikipedia descriptions, classified by type/significance
- **Knowledge Matrix:** Archetype × event type × geographic distance filtering — what a farmer knows vs a scribe vs a general
- **Consequence queue:** `ScheduledConsequence` on WorldState, fires delayed effects each turn
- **Ground Context Generator:** Runs at initialization, queries Events DB, filters through Knowledge Matrix, generates lived-experience opening via local LLM
- **Player Knowledge Agent:** `build_player_view()` in `player_knowledge.py` — filters full WorldState down to only what the character could plausibly know before sending to frontend
- **Pydantic LLM schemas:** `ActionParserResponse`, `AutonomousActionResponse`, `DeathCheckResponse`, `NPCPOVResponse`, `GroundContextResponse` — validated on every LLM call
- **Turn logs:** Append-only SQLite table — player input, parsed action, NPC responses, state diff, narrative output, player view snapshot per turn
- **NPC voice system:** Raw, archetype-calibrated, period-accurate language including vulgarity and slurs where contextually accurate
- **99+ tests** covering the full pipeline

### UI

Dark parchment aesthetic — Georgia serif, dark background, scrollable narrative column, text input bar at the bottom, hamburger menu (Map toggle, New Run, Run Status). Phase 0 quality — functional scaffolding, not a designed UI.

---

## What is NOT built yet

- Autonomous world tick — world only moves when player acts
- NPC personality traits and needs system
- Structural drift (tension, disposition, rumor propagation without LLM)
- Probabilistic world events
- Utility AI scoring for NPC autonomous decisions
- Per-session asyncio locks
- SQLite WAL PRAGMAs
- Region knowledge API endpoint
- Event markers on map
- Player actions scheduling consequences
- Historical divergence tracking wired to action parser
- NPC prompt injection of `ground_context`
- Word definitions overlay
- Full UI rebuild

---

## The fundamental limitation

The world is reactive, not autonomous. NPCs only act when the player acts. Nothing happens in the background. The simulation feels like a sophisticated chatbot with historical flavor rather than a living world. The player is structurally the protagonist even though the design says they shouldn't be.
