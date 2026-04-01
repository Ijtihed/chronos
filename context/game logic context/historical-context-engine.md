# Historical Context Engine (HCE)

> This document describes the design and purpose of the Historical Context Engine — a subsystem distinct from the Historical Knowledge Engine (HKE). The HKE answers "what plausibly follows from this action." The HCE answers "what was the world actually like at this moment, from the ground up, for a specific person in a specific place."

---

## What it is

The HCE is a two-layer system:

**Layer 1 — The Events DB (static, pre-built at build time)**
A flat database of canonical historical events, one record per event, indexed by year and region. This is the spine of historical truth the game knows about before any run starts. It is seeded from real sources and never changes at runtime unless a new era is added.

**Layer 2 — The Ground-Level Context Generator (dynamic, runtime)**
At run initialization, an agent takes the player's assigned character — their archetype, social class, location, and era — and uses the Events DB plus the existing RAG corpus to generate a ground-level picture of what life actually feels like at that moment. This is not a list of events. It is a lived experience synthesis: what does this person fear, what rumors have they heard, what does bread cost, what do they know about the war that is happening three regions away.

This generated context is injected into the world state at run start and continuously informs NPC voices and behavior throughout the run. It is cheap — generated once at initialization using a local model, not frontier.

---

## The Events DB

### Structure

Each record is a flat entry:

```json
{
  "year": 1347,
  "region": "Mediterranean",
  "event": "Plague arrives in Sicily via Genoese trading ships",
  "significance": "catastrophic",
  "type": "epidemic",
  "affects": ["trade", "population", "religion", "political_stability"],
  "canonical": true
}
```

### Fields

- `year` — the year the event occurs or begins
- `region` — broad geographic region (not a specific city, but a named area: "Anatolia", "Northern France", "Song Dynasty heartland")
- `event` — one sentence, factual, canonical description
- `significance` — one of: `local`, `regional`, `civilizational`
- `type` — category: `war`, `epidemic`, `famine`, `political`, `religious`, `economic`, `natural_disaster`, `cultural`
- `affects` — list of domains this event touches, used to filter relevance to a character's archetype
- `canonical` — always `true` in the base DB; `false` for game-generated events that diverge from history

### Sources

The Events DB is populated from two sources at build time:

- **Wikipedia API** — era and region summary articles, major event lists, parsed and structured by an LLM build script
- **Dedicated historical datasets** — conflict databases (e.g. UCDP), famine and epidemic records, political transition data where available in open formats

The build script is a one-time agent that: fetches source material for each era, extracts discrete events, structures them into the flat schema, deduplicates, and writes to a SQLite table alongside the existing world state DB.

### Coverage

One Events DB covers all eras. Events are filtered at runtime by year range and region relevance to the active run. The DB does not need to be exhaustive — it needs to be dense enough that any era has at least 20–40 relevant events within a 50-year window of the run's start year.

---

## The Ground-Level Context Generator

### When it runs

At run initialization, after the player character and starting region are assigned, before the first turn is rendered.

### What it produces

A `GroundContext` object attached to the world state:

```json
{
  "era_feel": "Constantinople is a city holding its breath. The Ottoman cannon have been audible for three weeks. Grain prices have doubled. Half the monasteries have sent their valuables away by ship.",
  "what_your_character_knows": "As a monastery librarian, you have heard from a Genoese merchant that the Sultan's army numbers in the tens of thousands. You do not know if this is true. The abbot has said nothing.",
  "local_rumors": [
    "The Venetian ships in the harbor are preparing to leave",
    "The Emperor has been seen praying at the Hagia Sophia every morning",
    "A soldier told someone in the market that the walls were breached last night — but the walls are still standing"
  ],
  "material_conditions": "Food is scarce but available. The monastery still has stores. Travel outside the walls is impossible.",
  "recent_events_known": ["Ottoman siege began 6 weeks ago", "Genoese reinforcements arrived but were fewer than hoped"],
  "recent_events_unknown": ["The Venetian relief fleet was turned back — your character does not know this yet"]
}
```

### How it is generated

1. Query Events DB for all events within 50 years of the run's start year, filtered to the run's region
2. Retrieve relevant RAG chunks from the existing HKE corpus (same vector DB, different query framing)
3. Pass to local LLM (llama3.1:8b) with a structured prompt:
   - Who the character is (archetype, social class, location)
   - The canonical events from the DB
   - Retrieved historical text chunks
   - Instruction: generate ground-level context as this specific person would experience it, with explicit information asymmetry — what they know, what they've heard as rumor, and what they cannot know
4. Store the result in world state as `ground_context`

### How it is used during the run

- **NPC prompts** inject the era_feel and material_conditions as background context on every turn — cheap, always present
- **Character backstory generation** uses the full GroundContext to make the backstory specific and grounded
- **NPC POV generation** uses `what_your_character_knows` and `local_rumors` to calibrate information asymmetry — an NPC who is geographically distant from an event knows less about it

---

## Game-Generated Events and Historical Divergence

The Events DB contains canonical history. As soon as the player acts, the world diverges. The game tracks this divergence explicitly.

When a player action creates a significant world event (a battle won, a ruler killed, a city abandoned), that event is written to the world state event log with `canonical: false`. These game-generated events:

- Are treated as equally real to canonical events for the purposes of NPC reactions and world state
- Can **override or contradict** canonical events — if the player prevents the fall of Constantinople, subsequent canonical events that depended on that fall are flagged as `superseded`
- Accumulate over the run and are passed alongside canonical events to the Ground Context Generator when NPCs need context

This means the further a run progresses, the more the world diverges from the canonical DB, and the more the HCE is working from game-generated history rather than real history. The system does not try to correct this — divergence is the point.

---

## Relationship to the HKE

| | HCE | HKE |
|---|---|---|
| **Question answered** | What is the world like right now for this person? | What plausibly follows from this action? |
| **When used** | Run initialization + NPC background context | Every turn, consequence generation |
| **Primary output** | Ground-level lived experience | Causal consequence suggestions |
| **Source material** | Events DB + RAG corpus | RAG corpus only |
| **Model** | Local (llama3.1:8b) | Local (llama3.1:8b) |
| **Timing** | Once at init, lightweight every turn | Every turn |

---

## Build-Time Agent

A dedicated build script (`scripts/build_events_db.py`) handles Events DB population. It is not run during gameplay — only when adding a new era or refreshing data.

The agent:

1. Takes an era name and year range as input
2. Fetches Wikipedia summary articles for the era and region
3. Queries any available structured datasets (conflict DB, etc.) for the period
4. Passes all source material to a local LLM with instructions to extract discrete events into the flat schema
5. Deduplicates against existing DB entries
6. Writes new entries to the SQLite `historical_events` table
7. Outputs a summary of what was added, what was skipped, and what years have sparse coverage

This script should be run for each new era before that era is added to the playable set. Sparse coverage (fewer than 20 events in a 50-year window) should be flagged and manually reviewed before the era ships.
