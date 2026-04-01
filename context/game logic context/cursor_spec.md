# CHRONOS — game design context (index)

> This folder is the source of truth for what the game is, how it works, and why it was designed this way — for any AI assistant helping build this project.
> It contains no final implementation decisions unless explicitly marked as agreed.
> When in doubt, read these documents before writing code or making design assumptions.

## Current project status

**Phase 0 — Proof of Life: COMPLETE** (2026-03-31). See [roadmap.md](roadmap.md) Phase 0 completion log.

**Phase 1 — Playable Text Loop: COMPLETE** (2026-04-01). Full run lifecycle: 5 eras, LLM character generation, travel, death (hybrid aging + consequence), memory decay to erasure, RAG/HKE v1, SQLite persistence, unified turn endpoint, narrative-only UI with total player agency. See [roadmap.md](roadmap.md) Phase 1 completion log.

**Phase 2 — The Map: COMPLETE** (2026-04-01). 3D globe (Three.js), historical borders from aourednik/historical-basemaps, player + NPC markers with visited/unvisited distinction, toggle with narrative, cache-busted state sync. Terrain view deferred. See [roadmap.md](roadmap.md) Phase 2 completion log.

**Design principles locked in:** Total player agency (no hand-holding), macro decision scale, selective NPC reactions (game decides who cares), present-tense stream UI, character assignment with ruler bias, family as NPCs, structural difficulty levers, HCE (Events DB + ground-level context).

## Read in this order

1. [overview.md](overview.md) — what the game is; the player's role; character assignment distribution
2. [gameplay.md](gameplay.md) — turns, information system, travel, factions, death
3. [simulation-and-world.md](simulation-and-world.md) — world model, family, difficulty, historical knowledge, map, run setup
4. [historical-context-engine.md](historical-context-engine.md) — HCE: Events DB + ground-level context generation, distinct from HKE
5. [roadmap.md](roadmap.md) — phased delivery, success criteria, what is / isn't in each phase, completion log
6. [open-questions.md](open-questions.md) — unresolved; **do not assume** when implementing

## Where this lives in the repo

| Location | Role |
|----------|------|
| `context/game logic context/` | Full design narrative (this index + linked files); **living** — update when design decisions are made |
| `backend/` | Python server (FastAPI) — action parser, NPC engine, world state, LLM client, death engine, world engine, HKE, persistence |
| `frontend/` | Browser UI (vanilla HTML/JS, Three.js globe via CDN) |
| `frontend/geo/` | Map data: coastlines, era border GeoJSON files, sources.md provenance record |
| `prompts/` | LLM prompt templates — design artifacts, reviewed separately from code |
| `tests/` | Automated test suite + manual test cases (`tests/manual/`) |
| `.cursor/rules/` | AI collaborator rules: design, protocol, roadmap, model tier |
