# CHRONOS — Phase 1 (Playable Text Loop)

Turn-based historical simulation. A complete run: random era, generated characters, travel, inaction, death by aging or consequence, memory decay to erasure.

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai) with `llama3.1:8b`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

ollama pull llama3.1:8b
```

## Commands

### Start the game

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

Open **http://localhost:8000**. Click "Begin" to start a new run.

### Ingest historical corpus (RAG)

```bash
source .venv/bin/activate

# Ingest one era
python -m backend.hke.ingest --era roman_late_empire

# Ingest all 5 eras
python -m backend.hke.ingest --all
```

### Run tests (no Ollama needed)

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/ --ignore=tests/test_live.py -v
```

### Run live tests (requires Ollama)

```bash
python -m pytest tests/test_live.py -v
```

### Full test suite

```bash
python -m pytest tests/ -v
```

## Project structure

```
backend/              Python server (FastAPI)
  main.py               API endpoints
  world_state.py         Data models, state mutation
  action_parser.py       NL -> structured action (LLM)
  npc_engine.py          NPC POV generation (LLM + RAG)
  character_gen.py       Character generation at run init (LLM)
  world_engine.py        World advancement, autonomous NPC actions
  death_engine.py        Death check, memory decay, erasure
  persistence.py         SQLite session storage
  eras/                  Era configs (5 eras)
  hke/                   Historical Knowledge Engine (RAG)
    ingest.py              Corpus download + chunking CLI
    store.py               Chroma vector DB
    retrieve.py            Context retrieval for prompts
frontend/             Browser UI (vanilla HTML/JS)
prompts/              LLM prompt templates
tests/                Test suite
context/              Game design docs
```

## Eras

| Era | Year | Region |
|-----|------|--------|
| Roman Late Empire | ~410 | Italia |
| Viking Age | ~870 | Scandinavia / North Sea |
| Crusader States | ~1190 | Levant |
| Black Death | ~1348 | Northern Italy / Southern France |
| Fall of Constantinople | ~1453 | Byzantine / Ottoman frontier |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/run` | Create new run (random era, LLM-generated characters) |
| GET | `/api/run/{id}` | Get run state |
| POST | `/api/run/{id}/turn` | Submit player action |
| POST | `/api/run/{id}/skip` | Skip turn (character acts autonomously) |
| POST | `/api/run/{id}/travel` | Travel to adjacent location |
| POST | `/api/run/{id}/reset` | Reset run |
| GET | `/api/runs` | List all runs |
| GET | `/api/health` | Health check |

## Model tier

All LLM calls are **local** (Ollama `llama3.1:8b`). Embeddings use Chroma's built-in model. No frontier API keys needed. See `prompts/` for all prompt templates.
