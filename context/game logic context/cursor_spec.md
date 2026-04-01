# CHRONOS — game design context (index)

> This folder is the source of truth for what the game is, how it works, and why it was designed this way — for any AI assistant helping build this project.
> It contains no final implementation decisions unless explicitly marked as agreed.
> When in doubt, read these documents before writing code or making design assumptions.

## Current project status

**Phase 0 — Proof of Life: COMPLETE** (2026-03-31).
**Phase 1 — Playable Text Loop: BUILT** — full run lifecycle, 5 eras, travel, death, memory decay, erasure, RAG, persistence. Pending playtesting.
**Phase 2 — The Map: COMPLETE** (2026-04-01). 2D Leaflet map with historical borders, visited/unvisited NPC markers, toggle with narrative.
**Next: Phase 2.5 — Map Intelligence + HCE.** Events DB, region knowledge on click, event markers filtered by character awareness.

**Design principles:** Total player agency, macro decisions, selective NPC reactions, present-tense stream UI. Character assignment reflects era demographics with bias toward historically significant figures. Map region knowledge filtered by character worldview (known facts + rumors). Map events filtered by character awareness (no god-view).

## Read in this order

1. [overview.md](overview.md) — what the game is; the player's role; character assignment distribution
2. [gameplay.md](gameplay.md) — turns, information system, travel, factions, death
3. [simulation-and-world.md](simulation-and-world.md) — world model, family, difficulty, historical knowledge, map, run setup
4. [historical-context-engine.md](historical-context-engine.md) — HCE: Events DB + ground-level context generator (distinct from HKE)
5. [roadmap.md](roadmap.md) — phased delivery, success criteria, what is / isn't in each phase, completion log
6. [open-questions.md](open-questions.md) — unresolved; **do not assume** when implementing

## Where this lives in the repo

| Location | Role |
|----------|------|
| `context/game logic context/` | Full design narrative (this index + linked files); **living** — update when design decisions are made |
| `backend/` | Python server (FastAPI) — action parser, NPC engine, world state, LLM client |
| `frontend/` | Browser UI (vanilla HTML/JS) |
| `prompts/` | LLM prompt templates — design artifacts, reviewed separately from code |
| `tests/` | Automated test suite (unit, integration with mocked LLM, live with Ollama) |
| `.cursor/rules/chronos-design.mdc` | Short design constraints + pointer back here |
| `.cursor/rules/chronos-ai-dev-protocol.mdc` | How the AI collaborator works: confirm tasks, open questions, context upkeep, prompt templates, never-do list |
| `.cursor/rules/chronos-roadmap.mdc` | Phase gates, success criteria vs task lists, updating `roadmap.md` when phases complete |
| `.cursor/rules/chronos-model-tier.mdc` | Local-first (Ollama), frontier only for agreed cases; justify every LLM/embed call |
