# CHRONOS — game design context (index)

> This folder is the source of truth for what the game is, how it works, and why it was designed this way — for any AI assistant helping build this project.
> It contains no final implementation decisions unless explicitly marked as agreed.
> When in doubt, read these documents before writing code or making design assumptions.

## Current project status

**Phase 0 — Proof of Life: COMPLETE** (2026-03-31).
**Phase 1 — Playable Text Loop: REBUILT simulation-first** (2026-04-01). Core systems work. Turn loop now: world simulates (NPCs act) then player acts. Ambient NPC activity visible each turn. NPC perception endpoint built. Pending full playtest against success criteria.
**Phase 2 — The Map: COMPLETE** (2026-04-01). 2D Leaflet map with historical borders, visited/unvisited NPC markers, toggle with narrative.
**Next: Phase 2.5 — Map Intelligence + HCE.** Events DB, ground context, region knowledge on click, event markers, word definitions overlay.

**Core design:** CHRONOS is a historical simulation observed through one person's perspective. NPCs are autonomous subagents — they travel, interact, act independently every turn. The player is a lens, not a protagonist. The narrative is dominated by world activity, not player actions. Sometimes nobody cares what the player did. The player can speed up time. In the future, the same simulation can be viewed through different characters' perspectives.

## Read in this order

1. [overview.md](overview.md) — what the game is; perspective not protagonist; character assignment
2. [gameplay.md](gameplay.md) — turns, NPC autonomy, NPC perception, voice and tone, information system, travel, factions, death
3. [npc-voice-system.md](npc-voice-system.md) — how NPCs speak: archetype voice reference, what they never do, required content when contextually accurate
4. [simulation-and-world.md](simulation-and-world.md) — world model, map (region knowledge + event markers), family, difficulty, run setup
5. [historical-context-engine.md](historical-context-engine.md) — HCE: Events DB + ground-level context generator (distinct from HKE)
6. [roadmap.md](roadmap.md) — phased delivery, success criteria, what is / isn't in each phase, completion log
7. [open-questions.md](open-questions.md) — unresolved; **do not assume** when implementing

## Where this lives in the repo

| Location | Role |
|----------|------|
| `context/game logic context/` | Full design narrative (this index + linked files); **living** — update when design decisions are made |
| `context/other/` | Lessons learned, architectural post-mortems, design mistakes to avoid |
| `backend/` | Python server (FastAPI) — action parser, NPC engine, world engine, world state, death engine, character gen, HKE, persistence |
| `frontend/` | Browser UI (HTML/JS/Tailwind), Leaflet map, geo data |
| `prompts/` | LLM prompt templates — design artifacts, reviewed separately from code |
| `tests/` | Automated test suite (unit, integration with mocked LLM, live with Ollama) |
| `.cursor/rules/` | AI collaborator rules: design constraints, dev protocol, roadmap gates, model tier policy |
