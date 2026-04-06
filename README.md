# CHRONOS

A historical simulation you observe through one person's eyes. You're dropped into a random era as a random person. The world moves whether you act or not. NPCs have their own lives. Sometimes nobody cares what you do. When you die, people forget you. Then it's over.

## Requirements

- **macOS** (tested on M4 Max) or any machine with 48GB+ RAM
- **Python 3.9+**
- **Ollama** — runs the LLM locally, no API keys needed

## Quick start

```bash
# 1. Install Ollama (if you haven't)
# Download from https://ollama.ai or:
brew install ollama

# 2. Pull the model (pick one based on your hardware)
ollama pull llama3.1:70b    # Best quality. Needs 48GB RAM. ~42GB download.
ollama pull llama3.1:8b     # Lighter. Works on 16GB. ~5GB download.
# The game auto-detects the best available model at startup.

# 3. Make sure Ollama is running
ollama serve    # skip if it's already running as a service

# 4. Clone and set up
git clone https://github.com/Ijtihed/Historicalsim.git
cd Historicalsim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. Run the game
uvicorn backend.main:app --reload

# 6. Open in browser
open http://localhost:8000
```

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
| New run | Menu → New Run |
| Continue saved run | Start screen → Continue |

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

# Live tests (requires Ollama running)
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
  llm.py                 Ollama client — auto-selects best model
  eras/                  5 era configs with locations, archetypes, coordinates
  hke/                   Historical Knowledge Engine (RAG — Chroma + Gutenberg/Wikipedia)
frontend/             Browser UI
  index.html              Manuscript-style UI (Tailwind)
  app.js                  Game loop, turn submission, narrative rendering
  map.js                  Leaflet map with historical borders + NPC markers
  geo/                    GeoJSON border files + Natural Earth coastlines
prompts/              LLM prompt templates (design artifacts)
context/              Game design docs (source of truth)
tests/                493 automated tests
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
| POST | `/api/run/{id}/reset` | Reset run |
| GET | `/api/runs` | List all runs |
| GET | `/api/geo/{era_key}` | Historical border GeoJSON for an era |
| GET | `/api/health` | Health check |

The turn endpoint handles everything. Type "go to Ravenna" and it routes to travel. Type "wait" and your character acts on their own. Type "start a revolt" and the simulation figures out what happens.

## Model tier

All LLM calls are local via Ollama. No API keys. No cost.

- **Preferred:** `llama3.1:70b` — best quality, needs 48GB RAM
- **Fallback:** `llama3.1:8b` — lighter, works on 16GB
- Auto-detected at startup. Logged in the terminal.

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
