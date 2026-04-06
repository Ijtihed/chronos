"""Offline build script: populate the historical_events table from Wikidata + Wikipedia.

Runs ONCE per era, not at game startup. Uses local Ollama for structuring.

Usage:
    python scripts/build_events_db.py \
        --era fall_of_constantinople --start 1400 --end 1470 \
        --region "Anatolia"

    python scripts/build_events_db.py --all   # runs all 5 starter eras
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

# Ensure the project root is on sys.path so `backend` is importable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.persistence import (
    DB_PATH,
    event_exists_by_qid,
    init_db,
    insert_historical_event,
    query_historical_events,
)
from backend.llm import chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("build_events_db")

# ---------------------------------------------------------------------------
# Wikidata SPARQL config
# ---------------------------------------------------------------------------

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Mapping from our event types to Wikidata class Q-IDs
EVENT_TYPE_CLASSES: dict[str, list[str]] = {
    "war": ["Q198", "Q178561", "Q188055"],         # war, battle, siege
    "epidemic": ["Q170483", "Q3241045"],            # epidemic, disease outbreak
    "famine": ["Q168247"],                          # famine
    "political": ["Q45382", "Q217602", "Q131558"],  # coup, treaty, annexation
    "natural_disaster": ["Q7944", "Q8068", "Q7692360"],  # earthquake, flood, volcanic eruption
    "cultural": ["Q3030248", "Q2091629"],           # founding, council (ecumenical/religious)
}

# Era definitions for --all mode.
# Covers 0-2000 AD across multiple regions. Overlapping windows are fine —
# deduplication by QID prevents duplicates. This list is intentionally broad;
# the game only needs ~20-40 events per 50-year window around each playable
# era, but having a dense spine across all of history means any future era
# config can draw from it immediately.
#
# TO EXPAND: add more entries here for underrepresented regions or periods.
# Each entry generates one batch of SPARQL queries + LLM structuring.
STARTER_ERAS = [
    # --- Classical antiquity (0-500 AD) ---
    {"era": "roman_peak",              "start": 0,    "end": 120,  "region": "Roman Empire"},
    {"era": "han_dynasty",             "start": 0,    "end": 220,  "region": "China"},
    {"era": "roman_crisis",            "start": 200,  "end": 300,  "region": "Roman Empire"},
    {"era": "three_kingdoms",          "start": 220,  "end": 280,  "region": "China"},
    {"era": "constantine",             "start": 300,  "end": 400,  "region": "Roman Empire"},
    {"era": "roman_late_empire",       "start": 360,  "end": 480,  "region": "Roman Empire"},
    {"era": "gupta_empire",            "start": 320,  "end": 550,  "region": "India"},

    # --- Early medieval (500-1000 AD) ---
    {"era": "justinian",               "start": 500,  "end": 600,  "region": "Byzantine Empire"},
    {"era": "rise_of_islam",           "start": 600,  "end": 750,  "region": "Arabian Peninsula"},
    {"era": "tang_dynasty",            "start": 618,  "end": 907,  "region": "China"},
    {"era": "carolingian",             "start": 750,  "end": 850,  "region": "France"},
    {"era": "abbasid_caliphate",       "start": 750,  "end": 950,  "region": "Middle East"},
    {"era": "viking_age",              "start": 790,  "end": 1000, "region": "Scandinavia"},
    {"era": "byzantine_resurgence",    "start": 950,  "end": 1050, "region": "Byzantine Empire"},

    # --- High medieval (1000-1300 AD) ---
    {"era": "norman_conquest",         "start": 1000, "end": 1100, "region": "England"},
    {"era": "first_crusade",           "start": 1050, "end": 1150, "region": "Levant"},
    {"era": "song_dynasty",            "start": 960,  "end": 1279, "region": "China"},
    {"era": "crusader_states",         "start": 1140, "end": 1250, "region": "Levant"},
    {"era": "mongol_empire",           "start": 1200, "end": 1300, "region": "Central Asia"},
    {"era": "mali_empire",             "start": 1230, "end": 1350, "region": "West Africa"},

    # --- Late medieval (1300-1500 AD) ---
    {"era": "black_death",             "start": 1300, "end": 1400, "region": "Europe"},
    {"era": "hundred_years_war",       "start": 1337, "end": 1453, "region": "France"},
    {"era": "timurids",                "start": 1370, "end": 1450, "region": "Central Asia"},
    {"era": "fall_of_constantinople",  "start": 1400, "end": 1470, "region": "Byzantine Empire"},
    {"era": "reconquista_end",         "start": 1450, "end": 1500, "region": "Spain"},

    # --- Early modern (1500-1750 AD) ---
    {"era": "reformation",             "start": 1500, "end": 1600, "region": "Europe"},
    {"era": "ottoman_peak",            "start": 1500, "end": 1600, "region": "Ottoman Empire"},
    {"era": "mughal_india",            "start": 1526, "end": 1700, "region": "India"},
    {"era": "ming_dynasty",            "start": 1368, "end": 1644, "region": "China"},
    {"era": "thirty_years_war",        "start": 1618, "end": 1660, "region": "Europe"},
    {"era": "edo_japan",               "start": 1600, "end": 1750, "region": "Japan"},

    # --- Revolutions and empire (1750-1900 AD) ---
    {"era": "american_revolution",     "start": 1760, "end": 1800, "region": "North America"},
    {"era": "french_revolution",       "start": 1789, "end": 1815, "region": "France"},
    {"era": "napoleonic_wars",         "start": 1800, "end": 1820, "region": "Europe"},
    {"era": "qing_decline",            "start": 1800, "end": 1900, "region": "China"},
    {"era": "scramble_for_africa",     "start": 1870, "end": 1914, "region": "Africa"},
    {"era": "meiji_japan",             "start": 1868, "end": 1912, "region": "Japan"},

    # --- Modern (1900-2000 AD) ---
    {"era": "world_war_one",           "start": 1910, "end": 1920, "region": "Europe"},
    {"era": "interwar",                "start": 1920, "end": 1939, "region": "Europe"},
    {"era": "world_war_two",           "start": 1939, "end": 1946, "region": "Europe"},
    {"era": "decolonization",          "start": 1945, "end": 1970, "region": "Africa"},
    {"era": "cold_war",                "start": 1947, "end": 1991, "region": "Europe"},
    {"era": "middle_east_modern",      "start": 1948, "end": 2000, "region": "Middle East"},
]


# ---------------------------------------------------------------------------
# SPARQL query builder
# ---------------------------------------------------------------------------

def _build_sparql_query(
    event_type: str,
    q_classes: list[str],
    year_start: int,
    year_end: int,
    region: str,
) -> str:
    """Build a SPARQL query for events of a given type in a region/year range."""
    class_values = " ".join(f"wd:{qid}" for qid in q_classes)

    return f"""
SELECT DISTINCT ?event ?eventLabel ?eventDescription ?date ?locationLabel ?countryLabel WHERE {{
  VALUES ?class {{ {class_values} }}
  ?event wdt:P31 ?class .

  OPTIONAL {{ ?event wdt:P585 ?date . }}
  OPTIONAL {{ ?event wdt:P580 ?startDate . }}
  BIND(COALESCE(?date, ?startDate) AS ?resolvedDate)

  FILTER(BOUND(?resolvedDate))
  FILTER(YEAR(?resolvedDate) >= {year_start} && YEAR(?resolvedDate) <= {year_end})

  OPTIONAL {{ ?event wdt:P276 ?location . }}
  OPTIONAL {{ ?event wdt:P17 ?country . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
ORDER BY ?resolvedDate
LIMIT 200
"""


async def _query_sparql(query: str) -> list[dict]:
    """Execute a SPARQL query against the Wikidata endpoint."""
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "CHRONOS-BuildScript/1.0 (historical-simulation-project)",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("bindings", [])


def _extract_qid(uri: str) -> str:
    """Extract Q-number from a Wikidata entity URI."""
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri


def _extract_year(binding: dict) -> int | None:
    """Extract the year from a SPARQL date binding."""
    for date_field in ("date", "startDate", "resolvedDate"):
        if date_field in binding:
            raw = binding[date_field]["value"]
            try:
                return int(raw[:4])
            except (ValueError, IndexError):
                pass
    return None


# ---------------------------------------------------------------------------
# Wikipedia description fetcher
# ---------------------------------------------------------------------------

async def _fetch_wikipedia_summary(title: str) -> str | None:
    """Fetch 2-3 sentence extract from Wikipedia REST API."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("extract", "")[:500]
        except Exception:
            pass
    return None


async def _get_wikipedia_title_for_qid(qid: str) -> str | None:
    """Get the English Wikipedia article title for a Wikidata entity."""
    url = f"https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "sitefilter": "enwiki",
        "format": "json",
    }
    headers = {"User-Agent": "CHRONOS-BuildScript/1.0 (historical-simulation-project)"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                entity = data.get("entities", {}).get(qid, {})
                sitelinks = entity.get("sitelinks", {})
                enwiki = sitelinks.get("enwiki", {})
                return enwiki.get("title")
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# LLM structuring
# ---------------------------------------------------------------------------

_STRUCTURE_PROMPT_TEMPLATE = """You are a historical data classifier for a simulation game.

Given these raw historical events, classify each one into the structured schema below.
For each event, return a JSON object with these fields:
- "year": integer
- "region": string (broad region name like "Anatolia", "Northern France", "Italia")
- "event": string (1-2 sentence factual description)
- "significance": one of "local", "regional", "civilizational"
- "type": one of "war", "epidemic", "famine", "political", "religious", "economic", "natural_disaster", "cultural"
- "affects": array of domain strings from: "trade", "population", "religion", "political_stability", "military", "agriculture", "culture", "infrastructure"
- "wikidata_qid": string (the Q-number provided)

Rules:
- Do NOT invent events. Only classify the events provided.
- Use the source_type hint but override it if the event clearly belongs to a different type.
- "civilizational" = affects multiple regions or has lasting historical impact. "regional" = affects a broad area. "local" = affects one city or settlement.
- Return a JSON array of objects. Nothing else.

Events to classify:
{events_json}
"""


async def _structure_events_with_llm(
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pass a batch of raw events to the local LLM for structuring."""
    if not raw_events:
        return []

    events_for_prompt = []
    for ev in raw_events:
        events_for_prompt.append({
            "wikidata_qid": ev["qid"],
            "label": ev["label"],
            "description": ev.get("description", ""),
            "year": ev.get("year"),
            "location": ev.get("location", ""),
            "country": ev.get("country", ""),
            "wikipedia_extract": ev.get("wiki_extract", ""),
            "source_type": ev.get("source_type", "unknown"),
        })

    prompt = _STRUCTURE_PROMPT_TEMPLATE.format(
        events_json=json.dumps(events_for_prompt, indent=2)
    )

    try:
        raw_response = await chat(prompt, json_mode=True, model="llama3.1:8b")
        parsed = json.loads(raw_response)
        if isinstance(parsed, dict) and "events" in parsed:
            parsed = parsed["events"]
        if not isinstance(parsed, list):
            parsed = [parsed]
        return parsed
    except (json.JSONDecodeError, Exception) as e:
        logger.error("LLM structuring failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def build_era(era: str, year_start: int, year_end: int, region: str) -> dict:
    """Build events for one era. Returns coverage stats."""
    logger.info("=== Building era: %s (%d-%d, region: %s) ===", era, year_start, year_end, region)

    all_raw_events: list[dict] = []

    for event_type, q_classes in EVENT_TYPE_CLASSES.items():
        query = _build_sparql_query(event_type, q_classes, year_start, year_end, region)
        logger.info("Querying Wikidata for %s events...", event_type)

        try:
            results = await _query_sparql(query)
            logger.info("  Found %d raw results for %s", len(results), event_type)
        except Exception as e:
            logger.error("  SPARQL query failed for %s: %s", event_type, e)
            results = []

        for binding in results:
            qid = _extract_qid(binding.get("event", {}).get("value", ""))
            year = _extract_year(binding)
            if not qid or not year:
                continue

            all_raw_events.append({
                "qid": qid,
                "label": binding.get("eventLabel", {}).get("value", ""),
                "description": binding.get("eventDescription", {}).get("value", ""),
                "year": year,
                "location": binding.get("locationLabel", {}).get("value", ""),
                "country": binding.get("countryLabel", {}).get("value", ""),
                "source_type": event_type,
            })

    # Deduplicate by QID
    seen_qids: set[str] = set()
    unique_events: list[dict] = []
    for ev in all_raw_events:
        if ev["qid"] not in seen_qids:
            seen_qids.add(ev["qid"])
            unique_events.append(ev)

    logger.info("Total unique events after dedup: %d", len(unique_events))

    # Check which QIDs already exist in DB
    new_events = []
    for ev in unique_events:
        if not await event_exists_by_qid(ev["qid"]):
            new_events.append(ev)
        else:
            logger.debug("  Skipping existing QID: %s", ev["qid"])

    logger.info("New events to process: %d (skipped %d existing)",
                len(new_events), len(unique_events) - len(new_events))

    # Fetch Wikipedia extracts for enrichment
    logger.info("Fetching Wikipedia summaries...")
    for ev in new_events:
        wiki_title = await _get_wikipedia_title_for_qid(ev["qid"])
        if wiki_title:
            extract = await _fetch_wikipedia_summary(wiki_title)
            ev["wiki_extract"] = extract or ""
        else:
            ev["wiki_extract"] = ""
        await asyncio.sleep(0.1)  # rate limiting

    # Process in batches of 10 through LLM
    inserted = 0
    batch_size = 10
    for i in range(0, len(new_events), batch_size):
        batch = new_events[i:i + batch_size]
        logger.info("Structuring batch %d-%d (%d events)...",
                     i + 1, min(i + batch_size, len(new_events)), len(batch))

        structured = await _structure_events_with_llm(batch)

        for item in structured:
            try:
                valid_types = {"war", "epidemic", "famine", "political",
                               "religious", "economic", "natural_disaster", "cultural"}
                valid_sig = {"local", "regional", "civilizational"}
                ev_type = item.get("type", "cultural")
                if ev_type not in valid_types:
                    ev_type = "cultural"
                sig = item.get("significance", "regional")
                if sig not in valid_sig:
                    sig = "regional"

                affects = item.get("affects", [])
                if not isinstance(affects, list):
                    affects = []

                await insert_historical_event(
                    year=int(item.get("year", year_start)),
                    region=item.get("region", region),
                    event=item.get("event", item.get("label", "Unknown event")),
                    significance=sig,
                    event_type=ev_type,
                    affects=affects,
                    canonical=True,
                    wikidata_qid=item.get("wikidata_qid"),
                )
                inserted += 1
            except Exception as e:
                logger.error("Failed to insert event: %s — %s", item, e)

    # Coverage report
    events = await query_historical_events(year_start, year_end, region)
    decades: dict[int, int] = {}
    type_counts: dict[str, int] = {}
    for ev in events:
        decade = (ev["year"] // 10) * 10
        decades[decade] = decades.get(decade, 0) + 1
        type_counts[ev["type"]] = type_counts.get(ev["type"], 0) + 1

    sparse = [d for d, c in sorted(decades.items()) if c < 2]

    report = {
        "era": era,
        "year_range": f"{year_start}-{year_end}",
        "total_events": len(events),
        "new_inserted": inserted,
        "events_per_decade": dict(sorted(decades.items())),
        "events_by_type": type_counts,
        "sparse_decades": sparse,
    }

    logger.info("--- Coverage Report for %s ---", era)
    logger.info("  Total events: %d (newly inserted: %d)", len(events), inserted)
    logger.info("  Events per decade: %s", dict(sorted(decades.items())))
    logger.info("  Events by type: %s", type_counts)
    if sparse:
        logger.warning("  SPARSE decades (< 2 events): %s", sparse)
    else:
        logger.info("  No sparse decades.")

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def dry_run_era(era: str, year_start: int, year_end: int, region: str) -> None:
    """Print SPARQL queries and expected shapes without touching DB or LLM."""
    print(f"\n=== DRY RUN: {era} ({year_start}-{year_end}, region: {region}) ===\n")

    total_results = 0
    for event_type, q_classes in EVENT_TYPE_CLASSES.items():
        query = _build_sparql_query(event_type, q_classes, year_start, year_end, region)
        print(f"--- {event_type} ---")
        print(f"Wikidata classes: {', '.join(f'wd:{q}' for q in q_classes)}")
        print(f"Year range: {year_start}-{year_end}")

        try:
            results = await _query_sparql(query)
            print(f"Results: {len(results)} events found")
            for r in results[:3]:
                label = r.get("eventLabel", {}).get("value", "?")
                year = _extract_year(r)
                loc = r.get("locationLabel", {}).get("value", "?")
                print(f"  - [{year}] {label} (location: {loc})")
            if len(results) > 3:
                print(f"  ... and {len(results) - 3} more")
            total_results += len(results)
        except Exception as e:
            print(f"  SPARQL query failed: {e}")
        print()

    print(f"=== TOTAL: {total_results} raw events across all types ===")
    print("(Dry run — nothing written to DB. Remove --dry-run to execute.)")


async def main():
    parser = argparse.ArgumentParser(
        description="Populate historical_events DB from Wikidata + Wikipedia"
    )
    parser.add_argument("--era", type=str, help="Era key name")
    parser.add_argument("--start", type=int, help="Start year")
    parser.add_argument("--end", type=int, help="End year")
    parser.add_argument("--region", type=str, help="Region name for SPARQL filtering")
    parser.add_argument("--all", action="store_true", help="Build all starter eras")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print SPARQL queries and results without writing to DB")
    args = parser.parse_args()

    if args.dry_run:
        if args.all:
            for era_def in STARTER_ERAS:
                await dry_run_era(
                    era_def["era"], era_def["start"], era_def["end"], era_def["region"]
                )
        elif all([args.era, args.start, args.end, args.region]):
            await dry_run_era(args.era, args.start, args.end, args.region)
        else:
            parser.error("Provide --era, --start, --end, --region (or use --all)")
        return

    await init_db()

    if args.all:
        reports = []
        for era_def in STARTER_ERAS:
            report = await build_era(
                era_def["era"], era_def["start"], era_def["end"], era_def["region"]
            )
            reports.append(report)
        logger.info("\n=== FINAL SUMMARY ===")
        for r in reports:
            logger.info(
                "  %s: %d events, sparse decades: %s",
                r["era"], r["total_events"], r["sparse_decades"] or "none",
            )
    else:
        if not all([args.era, args.start, args.end, args.region]):
            parser.error("Provide --era, --start, --end, --region (or use --all)")
        await build_era(args.era, args.start, args.end, args.region)


if __name__ == "__main__":
    asyncio.run(main())
