# CHRONOS — game design context (index)

> This folder is the source of truth for what the game is, how it works, and why it was designed this way — for any AI assistant helping build this project.
> It contains no final implementation decisions unless explicitly marked as agreed.
> When in doubt, read these documents before writing code or making design assumptions.

## Current project status

**Phase 0 — Proof of Life: COMPLETE** (2026-03-31).
**Phase 1 — Playable Text Loop: BUILT but needs simulation-first rebuild.** Core systems work (eras, travel, death, RAG, persistence) but the turn loop is player-centric. See `context/other/lessons-learned.md`.
**Phase 2 — The Map: COMPLETE** (2026-04-01). 2D Leaflet map with historical borders, visited/unvisited NPC markers.
**Next: Simulation-first rebuild of the turn loop + Phase 2.5 (HCE + map intelligence).**

**Core design:** CHRONOS is a simulation observed through one person's perspective. NPCs are autonomous subagents — they travel, interact, act independently. The player is a lens, not a protagonist. The narrative is dominated by world activity, not player actions. Sometimes nobody cares what the player did.

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
| `context/other/` | Lessons learned, architectural post-mortems, design mistakes to avoid |
| `.cursor/rules/chronos-design.mdc` | Short design constraints + pointer back here |
| `.cursor/rules/chronos-ai-dev-protocol.mdc` | How the AI collaborator works: confirm tasks, open questions, context upkeep, prompt templates, never-do list |
| `.cursor/rules/chronos-roadmap.mdc` | Phase gates, success criteria vs task lists, updating `roadmap.md` when phases complete |
| `.cursor/rules/chronos-model-tier.mdc` | Local-first (Ollama), frontier only for agreed cases; justify every LLM/embed call |
