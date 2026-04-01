# CHRONOS

A turn-based historical simulation. You are assigned a random character in a random era. You type what you decide to do — anything, at any scale. The game interprets your decision, the world responds, and the only way to understand the consequences is to find the people you affected. When you die, they forget you. Then it's over.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.1:8b
```

## Run

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

Open **http://localhost:8000**.

## Ingest historical corpus (optional, improves quality)

```bash
python -m backend.hke.ingest --era roman_late_empire
python -m backend.hke.ingest --all    # all 5 eras
```

## Tests

```bash
pip install -r requirements-dev.txt

python -m pytest tests/ --ignore=tests/test_live.py -v   # no Ollama needed
python -m pytest tests/test_live.py -v                    # requires Ollama
python -m pytest tests/ -v                                # everything
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/run` | Start new run (random era) |
| GET | `/api/run/{id}` | Get state |
| POST | `/api/run/{id}/turn` | Player types anything — action, travel, or inaction |
| POST | `/api/run/{id}/reset` | Reset run |
| GET | `/api/runs` | List runs |
| GET | `/api/health` | Health check |

The turn endpoint handles everything. Type "go to Ravenna" and it routes to travel. Type "wait" and your character acts on their own. Type "start a revolt" and the simulation figures out what happens.

## Eras

Roman Late Empire (~410), Viking Age (~870), Crusader States (~1190), Black Death (~1348), Fall of Constantinople (~1453).

## Model tier

All local Ollama. No API keys needed.
