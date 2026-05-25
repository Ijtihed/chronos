# CHRONOS

[![Tests](https://github.com/Ijtihed/chronos/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Ijtihed/chronos/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Model: Gemini 2.5 Flash-Lite](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash--Lite-4285F4.svg)](https://ai.google.dev)

> A historical simulation you observe through one person's eyes.

You're dropped into a random era as a random person. The world moves whether
you act or not. NPCs have their own lives. Sometimes nobody cares what you
do. When you die, people forget you. Then it's over.

CHRONOS is a turn-based, natural-language simulation. There is no HUD, no
score, no quest log. You type what your character does; the world — a 7-stage
autonomous pipeline of personality-driven NPCs, scheduled consequences, and
historically grounded events — figures out what happens next.

## Contents

- [Screens](#screens)
- [Quick start](#quick-start-macos--linux)
- [Environment variables](#environment-variables)
- [How to play](#how-to-play)
- [Controls](#controls)
- [Eras](#eras)
- [API](#api)
- [Architecture](#architecture)
- [Design & research](#design--research)
- [Model & cost](#model--cost)
- [Project structure](#project-structure)
- [Ingest historical corpus](#ingest-historical-corpus-optional-improves-npc-grounding)
- [Run tests](#run-tests)
- [Status](#status)
- [License, contributing, security](#license-contributing-security)

## Screens

UI mockups for the in-progress redesign live in
[`docs/ui-prototypes/`](docs/ui-prototypes/) — `start_screen`,
`loading_screen_text_only`, `game_active`, `observation_mode`, `erasure`,
`hamburger_panel`, plus the
[`DESIGN.md`](docs/ui-prototypes/stitch/chronos_archive/DESIGN.md) of the
"Ink and Earth" design system. The shipped UI lives in
[`frontend/`](frontend/) and a standalone demo page in
[`demo/demo.html`](demo/demo.html).

## Requirements

- **Python 3.11** (tested on macOS M4 Max; the backend and frontend are
  cross-platform and also run on Linux and Windows)
- **Google Gemini API key** — required for all LLM calls. Get one at
  [ai.google.dev](https://ai.google.dev). Without it, all LLM calls return a
  canned NoOp response (`"..."`) and the world still ticks, but the prose
  is intentionally degraded.

## Quick start (macOS / Linux)

```bash
git clone https://github.com/Ijtihed/chronos.git
cd chronos
python3.11 -m venv .venv      # or: uv venv --python 3.11 .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set: GEMINI_API_KEY=your_key_here

uvicorn backend.main:app --reload
open http://localhost:8000   # Linux: xdg-open http://localhost:8000
```

## Quick start (Windows / PowerShell)

```powershell
git clone https://github.com/Ijtihed/chronos.git
cd chronos
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Edit .env and set: GEMINI_API_KEY=your_key_here

uvicorn backend.main:app --reload
Start-Process http://localhost:8000
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required. All LLM calls route to Gemini. Loaded from `.env` or the shell. **Never commit this.** |
| `CHRONOS_GEMINI_MODEL` | Override the Gemini model ID. Default: `gemini-2.5-flash-lite`. |
| `CHRONOS_GEMINI_MAX_CONCURRENT` | Cap on concurrent Gemini requests. Default: `15`. Hard ceiling: `20`. |

## How to play

1. Click **Begin**. A random era is assigned. Wait for character generation (1-2 min).
2. Type anything in the text box. Anything at all — negotiate, flee, hoard, revolt, wait.
3. The world simulates. NPCs do their own things. Your action is one thread among many.
4. Press **M** to toggle the map. Click visited NPC markers for your impression of them.
5. Highlight any word for a dictionary definition.
6. When you die, you observe as memories fade. When the last person forgets you, it's over.

## Controls

| Action | How |
|--------|-----|
| Submit action | Type + Enter |
| Toggle map | Press M (not in text input) |
| NPC perception | Click green marker on map |
| Word definition | Highlight a word in the narrative |
| Menu | Hamburger icon (top right) |
| Connections (NPC interaction graph) | Menu → Connections |
| New run | Menu → New Run |
| Continue saved run | Start screen → Continue |

## Eras

| Era | Year | Region |
|-----|------|--------|
| Roman Late Empire | ~410 | Italia |
| Viking Age | ~870 | Scandinavia / North Sea |
| Crusader States | ~1190 | Levant |
| Black Death | ~1348 | Northern Italy / Southern France |
| Fall of Constantinople | ~1453 | Byzantine / Ottoman frontier |

Modern eras (1800s, 1900s, 2000s) planned for future expansion.

## API

| Method | Path | What it does |
|--------|------|-------------|
| POST | `/api/run/preview` | Get era info instantly (for loading screen) |
| POST | `/api/run` | Create new run (generates characters via LLM) |
| GET | `/api/run/{id}` | Get run state |
| POST | `/api/run/{id}/turn` | Player types anything — action, travel, or inaction |
| POST | `/api/run/{id}/skip` | Advance time N ticks (1-30) without player action |
| GET | `/api/run/{id}/npc/{npc_id}/perception` | Character's subjective impression of an NPC |
| GET | `/api/run/{id}/interaction_graph` | Player-centric NPC interaction graph (read-only snapshot) |
| GET | `/api/run/{id}/events/visible` | Map event pins. Civilizational + regional events only, lifetime window, regional events constrained to era home region. |
| POST | `/api/run/{id}/reset` | Reset run |
| GET | `/api/runs` | List all runs |
| GET | `/api/geo/{era_key}` | Historical border GeoJSON for an era |
| GET | `/api/health` | Health check |

The turn endpoint handles everything. Type "go to Ravenna" and it routes to
travel. Type "wait" and your character acts on their own. Type "start a
revolt" and the simulation figures out what happens.

## Architecture

Each turn runs a 7-stage autonomous pipeline. Stages 1–4 run **without
the player** — the world is alive whether or not you type:

```
1. Structural drift — tension, dispositions, needs decay, rumors  (no LLM)
2. Scheduled consequences — delayed effects from past actions fire (no LLM)
3. World events — probabilistic skirmishes, unrest, trade disruption (no LLM)
4. NPC autonomous actions — utility-scored decisions, LLM narration for nearby NPCs
5. Player action parsed (if they typed something)
6. Narrative assembled — what the player sees
7. State saved to database
```

The player is not the center. They are one person in a living world.

### NPC autonomy

Every NPC has **personality traits** (ambition, compassion, courage, piety,
pragmatism) and **17 inner needs** (survival, safety, duty, faith, trade,
etc.) that decay each turn. When needs go critical they override normal
behavior — a merchant who normally chases profit will flee if survival
spikes during a siege. Events permanently shift traits: prolonged hunger
makes NPCs more pragmatic and less compassionate.

### Consequence queue

Significant actions schedule delayed effects. A betrayal on turn 5 might
spread as a rumor on turn 7, shift NPC dispositions on turn 9, and
increase tension on turn 12. Consequences are **validated when they
fire** — if the world has diverged (the target NPC died, the location was
destroyed), obsolete consequences are cancelled.

### Historical Knowledge Engine (HKE) + Context Engine (HCE)

Two engines feed the narrative:

- **HKE** (Historical Knowledge Engine) — Gutenberg + Wikipedia chunked
  into Chroma with `nomic-embed-text`; retrieved to ground NPC speech in
  era-appropriate detail.
- **HCE** (Historical Context Engine) — a SQLite table of **1,569
  canonical events** across the 5 eras, sourced from Wikidata SPARQL +
  Wikipedia, then filtered through a **Knowledge Matrix** (archetype ×
  event type × geographic distance) so a farmer knows what farmers know,
  not what scribes know.

When a player action contradicts a canonical event — e.g. "prevent the
Sack of Rome" in 410 — the divergence is detected end-to-end and the
matching scheduled consequences are superseded.

## Design & research

CHRONOS is built design-first. Code serves the design, not the other way
around. The design narrative is split into nine living documents:

| Doc | What it covers |
|---|---|
| [`overview.md`](context/game%20logic%20context/overview.md) | What the game is; perspective not protagonist; character assignment distribution |
| [`gameplay.md`](context/game%20logic%20context/gameplay.md) | Turn loop, NPC autonomy, perception, voice and tone, info, travel, factions, death |
| [`npc-voice-system.md`](context/game%20logic%20context/npc-voice-system.md) | How NPCs speak — archetype voice, period-accurate language, what NPCs never do |
| [`simulation-and-world.md`](context/game%20logic%20context/simulation-and-world.md) | World model, map (region knowledge + event markers), family, difficulty, run setup |
| [`historical-context-engine.md`](context/game%20logic%20context/historical-context-engine.md) | HCE: Events DB + ground-level context generator (distinct from HKE) |
| [`visuals.md`](context/game%20logic%20context/visuals.md) | Scene-illustration rules: first-person POV, honest bodies, prompt template, current candidate provider |
| [`roadmap.md`](context/game%20logic%20context/roadmap.md) | Phased delivery, success criteria, what is and isn't in each phase, completion log |
| [`open-questions.md`](context/game%20logic%20context/open-questions.md) | Unresolved design items — **do not assume** when implementing |
| [`cursor_spec.md`](context/game%20logic%20context/cursor_spec.md) | Index + current project status |

Related artifacts:

- [`prompts/`](prompts/) — every LLM call has a corresponding prompt
  template, reviewed separately from code. Adding a call site means
  adding a template.
- [`versions/`](versions/) — weekly snapshot changelogs (state of the
  project at the end of each week).
- [`context/other/lessons-learned.md`](context/other/lessons-learned.md) —
  structural mistakes in thinking and their resolution, e.g. why the
  Phase 0–2 player-centric loop had to be rebuilt simulation-first on
  2026-04-01.
- [`.cursor/rules/`](.cursor/rules/) — binding rules for any AI
  collaborator on the project: design constraints, dev protocol, model
  tier policy, roadmap gates, commit hygiene, weekly version cadence.

## Model & cost

All LLM calls dispatch to a single provider — Google Gemini
(`CHRONOS_GEMINI_MODEL`, default `gemini-2.5-flash-lite`). The historic
fast/quality tier split has been retired; Ollama is no longer used at
runtime. The full policy is in
[`.cursor/rules/chronos-model-tier.mdc`](.cursor/rules/chronos-model-tier.mdc).

**NoOp fallback.** When `GEMINI_API_KEY` is missing, or when the Gemini
circuit breaker is open (3 failures in 60 s → 5 min), calls return
`"..."` and turns continue with degraded prose. Prevents cascading
failures on transient API issues. Set the key in `.env` to enable real
prose.

**Per-run cost.** ~€0.022 median per 10-turn run. €1.00 soft cap
(dismissible banner). €2.00 hard cap (turn submission blocked).
Per-turn cost is displayed in the top bar and persisted in
`turn_logs.turn_cost_usd`.

## Project structure

```
backend/              Python server (FastAPI)
  main.py               API — unified turn endpoint, run management, map geo, NPC perception
  world_state.py        Data models, state mutation, consequence queue
  world_engine.py       Simulation engine — NPC autonomous actions, consequence processing
  npc_personality.py    Personality traits, needs system, decay, event-driven shifts
  action_parser.py      Player input → structured action (LLM)
  npc_engine.py         NPC POV generation (LLM + RAG)
  death_engine.py       Death check, memory decay, erasure
  character_gen.py      Character + NPC generation at run start (LLM)
  persistence.py        SQLite session storage (WAL mode, performance-tuned)
  llm_provider.py       Gemini dispatcher + circuit breaker + NoOp fallback + cost accounting
  config.py             Environment config — API keys, pricing constants, cost caps
  eras/                 5 era configs with locations, archetypes, coordinates
  geo/                  Region centroid resolution for event markers (YAML)
  hke/                  Historical Knowledge Engine (RAG — Chroma + Gutenberg/Wikipedia)
frontend/             Browser UI (vanilla JS + HTML + Tailwind)
  index.html, app.js, map.js, graph.js, styles.css, geo/  (GeoJSON border files + Natural Earth coastlines)
prompts/              LLM prompt templates (design artifacts; reviewed separately from code)
context/              Game design docs (source of truth; living)
docs/                 Long-form docs — UI prototype mockups, test status
versions/             Weekly snapshot changelogs
seeds/                Per-era seed data (NPC archetypes, locations)
scripts/              One-off CLI helpers (events DB builder, image-gen POC)
cache/                Wikidata / Wikipedia lookup cache (regenerated by HKE ingest)
demo/                 Standalone demo page
tests/                Automated pytest suite (~842 cases across 35 modules)
.cursor/rules/        Binding rules for AI collaborators on the project
.github/workflows/    CI (offline pytest on push + PR)
```

## Ingest historical corpus (optional, improves NPC grounding)

```bash
# macOS / Linux
source .venv/bin/activate

# One era
python -m backend.hke.ingest --era roman_late_empire

# All 5 eras
python -m backend.hke.ingest --all
```

## Run tests

```bash
# macOS / Linux
source .venv/bin/activate
pip install -r requirements-dev.txt

# Offline suite (no API key needed; this is what CI runs)
python -m pytest tests/ -m "not live" -q

# Live tests (require a real GEMINI_API_KEY; burn a small amount of API credit)
python -m pytest tests/test_live.py -v

# Everything
python -m pytest tests/ -v
```

```powershell
# Windows / PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest tests/ -m "not live" -q
```

Five tests are currently `xfail`-quarantined — they were written against
the retired Ollama mock setup. Tracking, repair plan, and root cause in
[`docs/TEST_STATUS.md`](docs/TEST_STATUS.md).

## Status

| Phase | Status | What landed |
|---|---|---|
| 0 — Proof of Life | complete (2026-03-31) | Era selection, NL action parsing, basic loop |
| 1 — Playable Text Loop | complete (2026-04-01) | 7-stage pipeline, NPC personality/needs, structural drift, probabilistic events, utility scoring, consequence queue, time-skip |
| 2 — The Map | complete (2026-04-01) | 2D Leaflet map, historical borders, visited/unvisited NPC markers |
| 2.5 — Map Intelligence + HCE | complete (2026-04-21) | 1,569-event canonical DB, ground context generator, Knowledge-Matrix-filtered event markers (97.2% coverage), divergence detection |
| 3 — Scene Illustrations | in progress | Candidate provider soft-locked: `mflux` + FLUX.2 Klein 9B Q8 distilled — POC in [`scripts/imagegen_poc/`](scripts/imagegen_poc/) |

Weekly snapshots in [`versions/`](versions/). Open design questions in
[`open-questions.md`](context/game%20logic%20context/open-questions.md).

## After pulling / updating

If you already have the repo and are pulling new changes:

```bash
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
rm -f data/chronos.db                          # schema may have changed
python -m pytest tests/ -m "not live" -q
```

```powershell
# Windows / PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Remove-Item -Force -ErrorAction SilentlyContinue data\chronos.db
python -m pytest tests/ -m "not live" -q
```

The database is recreated automatically on first run. Existing save games
from before the schema change are not compatible — start a new run.

## License, contributing, security

- Released under the [MIT License](LICENSE).
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — design-first workflow, test
  conventions, commit style.
- [`SECURITY.md`](SECURITY.md) — how to report a vulnerability privately.
