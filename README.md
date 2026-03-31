# CHRONOS — Phase 0 (Proof of Life)

Turn-based historical simulation. Phase 0 proves the core loop: player input -> structured action -> world state update -> NPC perspective generation -> UI.

**Era:** Roman Late Empire, ~410 AD — Ariminum on the Adriatic coast as Alaric's Visigoths march on Rome.

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai) with `llama3.1:8b`

## Setup (first time)

```bash
# Create virtual environment and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Make sure Ollama is running and has the model
ollama serve          # if not already running
ollama pull llama3.1:8b
```

## Commands

### Start the game

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

Then open **http://localhost:8000**.

### Run all tests (no Ollama needed)

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt    # first time only
python -m pytest tests/ -v --ignore=tests/test_live.py
```

### Run live tests (requires Ollama running with llama3.1:8b)

```bash
source .venv/bin/activate
python -m pytest tests/test_live.py -v
```

### Run the full test suite

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Live tests auto-skip if Ollama is unreachable.

### Reset the game (via API)

```bash
curl -X POST http://localhost:8000/api/reset
```

### Check health

```bash
curl http://localhost:8000/api/health
```

## Project structure

```
backend/          Python server (FastAPI)
  main.py           API endpoints
  world_state.py    Data models, initial state, mutation logic
  action_parser.py  Natural language -> structured action (LLM)
  npc_engine.py     NPC POV generation (LLM)
  llm.py            Shared Ollama client
frontend/         Browser UI (vanilla HTML/JS)
prompts/          LLM prompt templates (design artifacts, not code)
tests/            Test suite
context/          Game design docs (source of truth)
```

## Model tier (Phase 0)

All LLM calls are **local** (Ollama `llama3.1:8b`). No frontier API keys needed. The action parser is a frontier *stub* — designed to swap to haiku/mini-tier when enabled. See `prompts/` for prompt templates.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check + Ollama status |
| GET | `/api/state` | Current world state |
| POST | `/api/turn` | Submit player action, get response |
| POST | `/api/reset` | Reset to initial state |

## What's hardcoded (Phase 0 only)

Everything below gets replaced with generation in Phase 1:
- Era (Roman Late Empire, 410 AD)
- Player character (Marcus Aurelius Corvinus, grain merchant)
- NPCs (Lucius Gallus, centurion; Deacon Paulus)
- Location (Ariminum)
- World state mutation rules (simple disposition shifts, tension timer)
