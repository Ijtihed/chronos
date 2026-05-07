# CHRONOS

A historical simulation you observe through one person's eyes. You're dropped into a random era as a random person. The world moves whether you act or not. NPCs have their own lives. Sometimes nobody cares what you do. When you die, people forget you. Then it's over.

## Requirements

- **macOS** (tested on M4 Max) or any machine with Python 3.11
- **Python 3.11**
- **Google Gemini API key** — required for all LLM calls. Get one at [ai.google.dev](https://ai.google.dev).

## Quick start

```bash
# 1. Clone and set up
git clone https://github.com/Ijtihed/Historicalsim.git
cd Historicalsim
python3.11 -m venv .venv      # or: uv venv --python 3.11 .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Set your Gemini API key (required for all LLM calls)
cp .env.example .env
# Edit .env and set: GEMINI_API_KEY=your_key_here

# 3. Run the game
uvicorn backend.main:app --reload

# 4. Open in browser
open http://localhost:8000
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required. All LLM calls route to Gemini. Loaded from `.env` or the shell. **Never commit this.** |
| `CHRONOS_GEMINI_MODEL` | Override the Gemini model ID. Default: `gemini-3-flash-preview`. |
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
| Toggle war-table (regional 3D terrain view) | Press T while map is open |
| NPC perception | Click green marker on map |
| Word definition | Highlight a word in the narrative |
| Menu | Hamburger icon (top right) |
| Connections (NPC interaction graph) | Menu → Connections |
| New run | Menu → New Run |
| Continue saved run | Start screen → Continue |
| Disable 3D substrate (manuscript depth + globe) | Append `?flat=1` to the URL — falls back to flat Leaflet + non-stacked manuscript |

## Ingest historical corpus (optional, improves NPC grounding)

```bash
source .venv/bin/activate

# One era
python -m backend.hke.ingest --era roman_late_empire

# All 5 eras
python -m backend.hke.ingest --all
```

## Run tests

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt

# All offline tests (no Ollama needed)
python -m pytest tests/ --ignore=tests/test_live.py -v

# Live tests (requires GEMINI_API_KEY set)
python -m pytest tests/test_live.py -v

# Everything
python -m pytest tests/ -v
```

## Eras

| Era | Year | Region |
|-----|------|--------|
| Roman Late Empire | ~410 | Italia |
| Viking Age | ~870 | Scandinavia / North Sea |
| Crusader States | ~1190 | Levant |
| Black Death | ~1348 | Northern Italy / Southern France |
| Fall of Constantinople | ~1453 | Byzantine / Ottoman frontier |

Modern eras (1800s, 1900s, 2000s) planned for future expansion.

## Project structure

```
backend/              Python server (FastAPI)
  main.py               API — unified turn endpoint, run management, map geo, NPC perception
  world_state.py         Data models, state mutation, consequence queue
  world_engine.py        Simulation engine — NPC autonomous actions, consequence processing
  npc_personality.py     Personality traits, needs system, decay, event-driven shifts
  action_parser.py       Player input → structured action (LLM)
  npc_engine.py          NPC POV generation (LLM + RAG)
  death_engine.py        Death check, memory decay, erasure
  character_gen.py       Character + NPC generation at run start (LLM)
  persistence.py         SQLite session storage (WAL mode, performance-tuned)
  llm_provider.py        All-Gemini LLM dispatcher -- Gemini + circuit breaker + NoOp fallback + cost accounting
  pin_classifier.py      Phase 2.9 — classifies pin source_confidence (observed/told_by/rumor/inferred) by reading turn_logs. No LLM.
  connection_proposal.py Phase 2.10 — Gemini Flash Lite proposer that writes one-sentence claims linking same-turn pin pairs.
  scene_director.py      Phase 3b — Gemini Flash Lite scene director that produces structured 3D diorama specs for major turns.
  config.py              Environment config — API keys, pricing constants, cost caps
  eras/                  5 era configs with locations, archetypes, coordinates
  hke/                   Historical Knowledge Engine (RAG — Chroma + Gutenberg/Wikipedia)
frontend/             Browser UI
  index.html              Manuscript-style UI (Tailwind)
  app.js                  Game loop, turn submission, narrative rendering, manuscript depth-stack (Pass 6)
  pinboard.js             Phase 2.9 pinboard — vanilla DOM + SVG; player highlights manuscript text and pins it as a curated node
  diorama.js              Phase 3b diorama renderer — stylized 3D vignettes inset in the manuscript (Three.js, procedural silhouette geometry, no external assets)
  globe.js                Three.js 3D globe — replaces flat Leaflet map (Phase 2.6)
  wartable.js             Three.js regional war-table view with real DEM terrain (Phase 2.6, T-key toggle)
  map.js                  Legacy Leaflet flat map. Kept as ?flat=1 fallback while the globe is being proven.
  graph.js                d3-force player-centric NPC interaction graph
  geo/                    GeoJSON border files + Natural Earth coastlines + per-era DEM heightmaps (terrain/)
prompts/              LLM prompt templates (design artifacts)
context/              Game design docs (source of truth)
tests/                ~820 automated tests
```

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
| POST | `/api/run/{id}/pin` | Phase 2.9 — create a single pin from a highlighted manuscript passage. Server classifies `source_confidence` (observed / told_by / rumor / inferred) by reading the source turn-log row. |
| POST | `/api/run/{id}/pinboard` | Phase 2.9 — bulk pinboard update (positions, deletes, connection upserts, cuts). Partial-update semantics. Phase 2.10 extended: `delete_connection_ids`, `tombstone_pin_pairs`, `meta_was_edited` for the agree/edit/reject flow. |
| POST | `/api/run/{id}/pinboard/propose_connections` | Phase 2.10 — auto-proposer. Walks same-turn pin pairs, skips already-connected and tombstoned, asks Gemini Flash Lite for one-sentence claims, writes them as `kind="auto_proposed"`. Frontend gates the call (≥3 unconnected pins, ≥2 turns since last). |
| POST | `/api/run/{id}/diorama/{turn_id}` | Phase 3b — mints a stylized 3D diorama for a major turn (significance ≥ 0.85). Server reads the turn-log row, asks Gemini Flash Lite for a structured spec (location_kind, characters, camera, mood), saves the Diorama. Idempotent per turn; capped at 30 per run; refuses on hard cost cap. |
| POST | `/api/run/{id}/board` | **410 Gone** — the deleted Phase 2.8 corridor endpoint. Use `/pinboard` instead. |
| POST | `/api/run/{id}/reset` | Reset run |
| GET | `/api/runs` | List all runs |
| GET | `/api/geo/{era_key}` | Historical border GeoJSON for an era |
| GET | `/api/geo/terrain/{era_key}` | DEM heightmap PNG for an era (war-table) |
| GET | `/api/health` | Health check |

The turn endpoint handles everything. Type "go to Ravenna" and it routes to travel. Type "wait" and your character acts on their own. Type "start a revolt" and the simulation figures out what happens.

## Model tier

All-Gemini dispatch (see `.cursor/rules/chronos-model-tier.mdc` for the full policy).

**All calls route to Gemini** (`CHRONOS_GEMINI_MODEL`, default `gemini-3-flash-preview`).
The historic fast/quality tier split is retired -- Ollama is no longer used at runtime.

**NoOp fallback** -- when `GEMINI_API_KEY` is missing or the circuit breaker is open
(3 failures in 60s -> 5 min), calls return `"..."` and turns continue with degraded
prose. Prevents cascading failures on transient API issues.

**Per-run cost** -- ~EUR 0.022 median per 10-turn run. EUR 1.00 soft cap (banner,
dismissible). EUR 2.00 hard cap (turn submission blocked). Cost displayed in the top
bar, persisted in `turn_logs.turn_cost_usd`.

## Architecture

7-stage autonomous pipeline (stages 1-4 run without the player):

```
1. Structural drift — tension, dispositions, needs decay, rumors (no LLM)
2. Scheduled consequences — delayed effects from past actions fire (no LLM)
3. World events — probabilistic skirmishes, unrest, trade disruption (no LLM)
4. NPC autonomous actions — utility-scored decisions, LLM narration for nearby NPCs
5. Player action parsed (if they typed something)
6. Narrative assembled — what the player sees
7. State saved to database
```

The player is not the center. They are one person in a living world.

### NPC autonomy

Every NPC has personality traits (ambition, compassion, courage, piety, pragmatism) and 17 inner needs (survival, safety, duty, faith, trade, etc.) that decay each turn. When needs go critical, they override normal behavior. A merchant who normally chases profit will flee if survival spikes during a siege. Events permanently shift traits — prolonged hunger makes NPCs more pragmatic and less compassionate.

### Consequence queue

Significant actions schedule delayed effects. A betrayal on turn 5 might spread as a rumor on turn 7, shift NPC dispositions on turn 9, and increase tension on turn 12. Consequences are validated when they fire — if the world has diverged (the target NPC died, the location was destroyed), obsolete consequences are cancelled.

## After pulling / updating

If you already have the repo and are pulling new changes:

```bash
source .venv/bin/activate
pip install -r requirements.txt

# Delete old database (schema may have changed)
rm -f data/chronos.db

# Run tests to verify
python -m pytest tests/ --ignore=tests/test_live.py -q
```

The database is recreated automatically on first run. Existing save games from before the schema change are not compatible — start a new run.
