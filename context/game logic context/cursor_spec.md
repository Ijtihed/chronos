# CHRONOS — game design context (index)

> This folder is the source of truth for what the game is, how it works, and why it was designed this way — for any AI assistant helping build this project.
> It contains no final implementation decisions unless explicitly marked as agreed.
> When in doubt, read these documents before writing code or making design assumptions.

## Current project status

**Phase 0 — Proof of Life: COMPLETE** (2026-03-31).
**Phase 1 — Playable Text Loop: COMPLETE** (2026-04-01, autonomous world rebuild 2026-04-06). 7-stage pipeline, NPC personality/needs, structural drift, probabilistic events, utility scoring, consequence queue, time-skip.
**Phase 2 — The Map: COMPLETE** (2026-04-01). 2D Leaflet map with historical borders, visited/unvisited NPC markers, toggle with narrative.
**Phase 2.5 — Map Intelligence + HCE: COMPLETE** (2026-04-21). Events DB (1,569 canonical events across 5 eras), ground context generator, region knowledge on click, loading screen from Events DB, time-skip UI, word definitions overlay, event markers on map (Knowledge Matrix filtering + centroid resolution at 97.2% coverage), historical divergence detection.
**Next: Phase 3 — Scene Illustrations.** Provider decision soft-locked 2026-04-22: `mflux` + FLUX.2 Klein 9B distilled (POC evidence in `scripts/imagegen_poc/`). Design rules in [visuals.md](visuals.md).

**Core design:** CHRONOS is a historical simulation observed through one person's perspective. NPCs are autonomous subagents with personality traits and inner needs — they travel, interact, act independently every turn based on utility scoring against their situation. The player is a lens, not a protagonist. The narrative is dominated by world activity, not player actions. Sometimes nobody cares what the player did. The player can speed up time. Every NPC gets an LLM call every turn — the world is always alive everywhere, not just at the player's location. In the future, the same simulation can be viewed through different characters' perspectives.

## Read in this order

1. [overview.md](overview.md) — what the game is; perspective not protagonist; character assignment
2. [gameplay.md](gameplay.md) — turns, NPC autonomy, NPC perception, voice and tone, information system, travel, factions, death
3. [npc-voice-system.md](npc-voice-system.md) — how NPCs speak: archetype voice reference, what they never do, required content when contextually accurate
4. [simulation-and-world.md](simulation-and-world.md) — world model, map (region knowledge + event markers), family, difficulty, run setup
5. [historical-context-engine.md](historical-context-engine.md) — HCE: Events DB + ground-level context generator (distinct from HKE)
6. [visuals.md](visuals.md) — scene illustration rules: first-person POV, honest bodies, the v3 prompt template, style, current candidate provider
7. [roadmap.md](roadmap.md) — phased delivery, success criteria, what is / isn't in each phase, completion log
8. [open-questions.md](open-questions.md) — unresolved; **do not assume** when implementing

## Where this lives in the repo

| Location | Contents | Files |
|----------|----------|------:|
| `context/game logic context/` | Full design narrative (this index + linked files); **living** — update when design decisions are made | 9 |
| `context/other/` | Lessons learned, architectural post-mortems, design mistakes to avoid | 1 |
| `backend/` | Python server (FastAPI) — action parser, NPC engine, world engine, NPC personality/needs, world drift, world events, world state, death engine, character gen, HCE, HKE, persistence, player knowledge, event vocabulary | 28 |
| `backend/eras/` | Era config modules (5 eras + `__init__.py`) | 6 |
| `backend/geo/` | Region centroid resolution for event markers — hand-curated YAML + normalizer | 3 |
| `backend/hke/` | Historical Knowledge Engine — RAG ingest, retrieval, vector store | 5 |
| `frontend/` | Browser UI (vanilla JS + HTML + Tailwind CSS), Leaflet map | 4 |
| `frontend/geo/` | GeoJSON border files (5 eras), coastlines, sources documentation | 7 |
| `prompts/` | LLM prompt templates — design artifacts, reviewed separately from code | 11 |
| `scripts/` | Build-time tools (`build_events_db.py`) | 1 |
| `seeds/` | Backbone event seed files per era (JSON) | 5 |
| `tests/` | Automated test suite (unit, integration with mocked LLM, live with Ollama) | 24 |
| `data/` | Runtime data (SQLite DB, Chroma embeddings) — **gitignored**, generated locally | — |
| `.cursor/rules/` | AI collaborator rules: design constraints, dev protocol, roadmap gates, model tier policy | 6 |
