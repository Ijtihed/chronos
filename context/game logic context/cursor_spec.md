# CHRONOS — game design context (index)

> This folder is the source of truth for what the game is, how it works, and why it was designed this way — for any AI assistant helping build this project.
> It contains no final implementation decisions unless explicitly marked as agreed.
> When in doubt, read these documents before writing code or making design assumptions.

## Current project status

**Phase 0 — Proof of Life: COMPLETE** (2026-03-31). See [roadmap.md](roadmap.md) Phase 0 completion log for details.

**Next: Phase 1 — Playable Text Loop.** Full run from character generation to end-of-memory. Requires resolving the **UI metaphor** open question before UI work begins.

## Read in this order

1. [overview.md](overview.md) — what the game is; the player's role
2. [gameplay.md](gameplay.md) — turns, information system, travel, factions, death
3. [simulation-and-world.md](simulation-and-world.md) — world model, historical knowledge, map, run setup, run uniqueness
4. [roadmap.md](roadmap.md) — phased delivery, success criteria, what is / isn't in each phase, completion log
5. [open-questions.md](open-questions.md) — unresolved; **do not assume** when implementing

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
