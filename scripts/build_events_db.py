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
    "war": [
        "Q198",       # war
        "Q178561",    # battle
        "Q188055",    # siege
        "Q831663",    # military campaign
        "Q180684",    # military conflict
        "Q1261499",   # naval battle
        "Q1075241",   # crusade (military)
    ],
    "epidemic": [
        "Q170483",    # epidemic
        "Q3241045",   # disease outbreak
        "Q12184",     # pandemic
    ],
    "famine": [
        "Q168247",    # famine
        "Q1242856",   # food crisis
    ],
    "political": [
        "Q45382",     # coup d'état
        "Q217602",    # treaty
        "Q131558",    # annexation
        "Q209715",    # coronation
        "Q3882219",   # assassination
        "Q165950",    # abdication
        "Q2915731",   # succession crisis
        "Q6256",      # country (for state formation events)
    ],
    "religious": [
        "Q15893266",  # ecumenical council (variant)
        "Q51645",     # ecumenical council (Council of Florence is this class)
        "Q80117",     # schism
        "Q1047113",   # religious persecution
        "Q3966183",   # religious war
        "Q1128637",   # synod
        "Q189533",    # council (general)
    ],
    "economic": [
        "Q11032",     # trade route
        "Q721790",    # trade war
        "Q476068",    # economic crisis
        "Q2647820",   # blockade
    ],
    "natural_disaster": [
        "Q7944",      # earthquake
        "Q8068",      # flood
        "Q7692360",   # volcanic eruption
        "Q124757",    # tsunami
    ],
    "cultural": [
        "Q3030248",   # founding (of institutions)
        "Q2091629",   # council (general)
        "Q35127",     # university (founding)
    ],
}

# Region to Wikidata country/polity QIDs mapping.
# Used to filter SPARQL results by P17 (country). Much faster than
# coordinate filtering on the Wikidata endpoint.
REGION_COUNTRY_QIDS: dict[str, list[str]] = {
    "Roman Empire":       ["Q2277", "Q2669072"],       # Roman Empire, Western Roman Empire
    "Byzantine Empire":   [
        "Q12544",   # Byzantine Empire
        "Q12560",   # Ottoman Empire
        "Q4948",    # Republic of Venice
        "Q174306",  # Republic of Genoa
        "Q171150",  # Kingdom of Hungary
        "Q41",      # Greece (modern — catches events tagged with modern entity)
        "Q219",     # Bulgaria (modern — catches events tagged with modern entity)
        "Q403",     # Serbia (modern)
        "Q878319",  # Serbian Despotate
        "Q420759",  # Second Bulgarian Empire
        "Q178897",  # Latin Empire
        "Q389004",  # Principality of Wallachia
    ],
    "Ottoman Empire":     ["Q12560", "Q12544", "Q37806", "Q215", "Q219"],
    "Scandinavia":        ["Q34", "Q35", "Q33", "Q756617"],  # Sweden, Denmark, Norway, Viking settlement
    "Levant":             ["Q7462", "Q170895", "Q12560", "Q12544"],  # Crusader states, Kingdom of Jerusalem, Ottoman, Byzantine
    "Europe":             [],  # too broad, skip filtering
    "France":             ["Q142"],
    "England":            ["Q21", "Q174193"],  # England, Kingdom of England
    "Spain":              ["Q29", "Q179876", "Q12526"],  # Spain, Crown of Castile, Crown of Aragon
    "Central Asia":       ["Q7768", "Q487907"],  # Mongol Empire, Timurid Empire
    "China":              ["Q148", "Q9903", "Q6581823", "Q7462"],
    "India":              ["Q668", "Q1247618"],  # India, Mughal Empire
    "Japan":              ["Q17"],
    "Middle East":        ["Q12560", "Q6250", "Q4948"],
    "Arabian Peninsula":  ["Q6250", "Q12560"],  # Caliphate, Ottoman
    "West Africa":        ["Q837926"],  # Mali Empire
    "Africa":             [],  # too broad
    "North America":      ["Q30"],  # USA
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
    """Build a SPARQL query for events of a given type in a region/year range.

    If a bounding box exists for the region, adds a coordinate filter so
    only geographically relevant events are returned. Events without
    coordinates still pass through (the LLM classifies them later).
    """
    class_values = " ".join(f"wd:{qid}" for qid in q_classes)
    country_qids = REGION_COUNTRY_QIDS.get(region, [])

    country_filter = ""
    if country_qids:
        country_values = " ".join(f"wd:{qid}" for qid in country_qids)
        country_filter = f"""
  VALUES ?targetCountry {{ {country_values} }}
  ?event wdt:P17 ?targetCountry ."""

    return f"""
SELECT DISTINCT ?event ?eventLabel ?eventDescription ?date ?locationLabel ?countryLabel WHERE {{
  VALUES ?class {{ {class_values} }}
  ?event wdt:P31 ?class .
  {country_filter}

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


_RETRY_DELAYS = [5, 15, 30]
_CACHE_DIR = _PROJECT_ROOT / "cache"


_MAX_ATTEMPTS = 1 + len(_RETRY_DELAYS)  # 1 initial + 3 retries = 4


async def _query_sparql(query: str) -> list[dict]:
    """Execute a SPARQL query with retry logic for rate limiting.

    Makes up to 4 attempts (1 initial + 3 retries with 5s/15s/30s backoff).
    Returns [] on exhausted retries — never blocks indefinitely.
    """
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "CHRONOS-BuildScript/1.0 (historical-simulation-project)",
    }
    delays = [0] + _RETRY_DELAYS
    last_error = None

    for attempt_num in range(_MAX_ATTEMPTS):
        delay = delays[attempt_num]
        if delay:
            logger.info("  Retry %d/%d in %ds...", attempt_num, len(_RETRY_DELAYS), delay)
            await asyncio.sleep(delay)
        try:
            timeout = 30.0 if attempt_num > 0 else 60.0
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    WIKIDATA_SPARQL_URL,
                    params={"query": query},
                    headers=headers,
                )
                if resp.status_code in (429, 502, 503):
                    last_error = f"{resp.status_code} {resp.reason_phrase}"
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", {}).get("bindings", [])
        except httpx.TimeoutException:
            last_error = "Timeout"
            continue
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 502, 503):
                last_error = str(e)
                continue
            raise
        except Exception as e:
            last_error = str(e)
            continue

    logger.warning("  SPARQL query failed after %d retries: %s — skipping", len(_RETRY_DELAYS), last_error)
    return []


def _cache_key(era: str, event_type: str, win_start: int, win_end: int) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"wikidata_{era}_{event_type}_{win_start}_{win_end}.json"


def _load_cache(path: Path) -> list[dict] | None:
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def _save_cache(path: Path, data: list[dict]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


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
    """Fetch 2-3 sentence extract from MediaWiki API (more reliable than REST)."""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "exintro": "true",
        "explaintext": "true",
        "exsentences": "3",
        "format": "json",
    }
    headers = {"User-Agent": "CHRONOS-BuildScript/1.0 (historical-simulation-project)"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                for page in pages.values():
                    extract = page.get("extract", "")
                    if extract:
                        return extract[:500]
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
# Wikipedia year page parser
# ---------------------------------------------------------------------------

import re as _re


def _strip_wiki_markup(text: str) -> str:
    """Strip wiki markup to plain text. Lossy but fast."""
    text = _re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)  # [[link|display]] → display
    text = _re.sub(r"\{\{[^}]*\}\}", "", text)  # remove templates
    text = _re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=_re.DOTALL)  # remove refs
    text = _re.sub(r"<ref[^/]*/>", "", text)  # remove self-closing refs
    text = _re.sub(r"<[^>]+>", "", text)  # remove remaining HTML tags
    text = _re.sub(r"'{2,}", "", text)  # remove bold/italic markers
    text = _re.sub(r"\s+", " ", text).strip()
    return text


def _parse_events_section(wikitext: str) -> list[str]:
    """Extract event lines from a Wikipedia year page.

    Handles two formats:
    1. Classic: ==Events== section with bullet points (*)
    2. Modern: Geographic sections (==Europe==, ==Asia==, etc.) with prose paragraphs
    """
    lines = wikitext.split("\n")
    events = []

    # Try classic format first: ==Events== with bullet points
    in_events = False
    for line in lines:
        stripped = line.strip()
        if _re.match(r"^==\s*Events\s*==", stripped):
            in_events = True
            continue
        if in_events and _re.match(r"^==\s*[^=]", stripped):
            break
        if not in_events:
            continue
        if _re.match(r"^===", stripped):
            continue
        if stripped.startswith("*"):
            clean = _strip_wiki_markup(stripped.lstrip("* "))
            if len(clean) > 15:
                events.append(clean)

    if events:
        return events

    # Fallback: modern format with geographic sections and prose
    skip_sections = {"births", "deaths", "references", "notes", "see also",
                     "external links", "further reading", "bibliography"}
    in_content = False
    current_section = ""

    for line in lines:
        stripped = line.strip()
        h2_match = _re.match(r"^==\s*([^=]+?)\s*==\s*$", stripped)
        if h2_match:
            current_section = h2_match.group(1).lower().strip()
            in_content = current_section not in skip_sections
            continue
        if _re.match(r"^===", stripped):
            continue
        if not in_content:
            continue
        if stripped.startswith("{{") or stripped.startswith("|") or stripped.startswith("[[File:"):
            continue
        if not stripped or len(stripped) < 20:
            continue

        clean = _strip_wiki_markup(stripped)
        if len(clean) > 30:
            sentences = _re.split(r"(?<=[.!?])\s+", clean)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) > 30:
                    events.append(sent)

    return events


async def _fetch_wikipedia_year_page(year: int) -> list[str]:
    """Fetch and parse events from a Wikipedia year page. Returns plain-text event lines."""
    cache_path = _CACHE_DIR / f"wikipedia_year_{year}.json"
    cached = _load_cache(cache_path)
    if cached is not None:
        logger.info("  Using cached Wikipedia year page for %d (%d events)", year, len(cached))
        return cached

    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": str(year),
        "prop": "wikitext",
        "format": "json",
    }
    headers = {"User-Agent": "CHRONOS-BuildScript/1.0 (historical-simulation-project)"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning("  Wikipedia year page %d returned %d", year, resp.status_code)
                return []
            data = resp.json()
            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            if not wikitext:
                logger.warning("  Wikipedia year page %d has no wikitext", year)
                return []
    except Exception as e:
        logger.warning("  Failed to fetch Wikipedia year page %d: %s", year, e)
        return []

    events = _parse_events_section(wikitext)
    logger.info("  Parsed %d events from Wikipedia year page %d", len(events), year)
    _save_cache(cache_path, events)
    return events


async def fetch_wikipedia_year_events(
    year_start: int, year_end: int, region: str,
) -> list[dict]:
    """Fetch events from Wikipedia year pages for a year range.

    Returns raw event dicts ready for LLM structuring.
    """
    all_events: list[dict] = []

    for year in range(year_start, year_end + 1):
        event_lines = await _fetch_wikipedia_year_page(year)
        for line in event_lines:
            all_events.append({
                "qid": f"wiki_year_{year}_{hash(line) % 100000}",
                "label": line[:100],
                "description": line,
                "year": year,
                "location": "",
                "country": "",
                "source_type": "wikipedia_year_page",
                "wiki_extract": line,
            })
        await asyncio.sleep(1.0)

    logger.info("Total events from Wikipedia year pages: %d", len(all_events))
    return all_events


# ---------------------------------------------------------------------------
# LLM structuring
# ---------------------------------------------------------------------------

_STRUCTURE_PROMPT_TEMPLATE = """You are a historical data classifier for a simulation game.

The target era is: {era_region}, {year_start}-{year_end} AD.

Given these raw historical events, classify each one into the structured schema below.
For each event, return a JSON object with these fields:
- "year": integer (from the source data — do not guess)
- "region": string (broad region name like "Anatolia", "Byzantine Empire", "Balkans", "Mediterranean")
- "event": string (1-2 sentence factual description — plain, specific, no interpretation)
- "significance": one of "local", "regional", "civilizational"
- "type": one of "war", "epidemic", "famine", "political", "religious", "economic", "natural_disaster", "cultural"
- "affects": array of domain strings from: "trade", "population", "religion", "political_stability", "military", "agriculture", "culture", "infrastructure"
- "wikidata_qid": string (the Q-number provided)

Rules:
- Do NOT invent events. Only classify the events provided.
- REJECT events geographically irrelevant to the target era region. If a Scottish battle or Japanese earthquake appears, set that entry to null — do not include it in the output.
- Use the source_type hint but override it if the event clearly belongs to a different type.
- Significance: "civilizational" = affects multiple empires or changes the course of history. "regional" = affects a kingdom or large area. "local" = affects one city or settlement only.
- Affects: be CONSERVATIVE. Only list domains genuinely impacted. A battle affects "military". It does NOT automatically affect "trade", "population", "religion" unless the source explicitly says so.
- If you cannot confidently determine the year, region, or type from the source data, return null for that event rather than guessing.
- Return a JSON array of objects. Nothing else.

Events to classify:
{events_json}
"""


async def _structure_events_with_llm(
    raw_events: list[dict[str, Any]],
    era_region: str = "",
    year_start: int = 0,
    year_end: int = 0,
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
        era_region=era_region or "unknown region",
        year_start=year_start,
        year_end=year_end,
        events_json=json.dumps(events_for_prompt, indent=2),
    )

    try:
        raw_response = await chat(prompt, json_mode=True, model="llama3.1:8b")
        parsed = json.loads(raw_response)
        if isinstance(parsed, dict) and "events" in parsed:
            parsed = parsed["events"]
        if not isinstance(parsed, list):
            parsed = [parsed]

        validated = []
        for item in parsed:
            if item is None:
                continue
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("event"), list):
                for sub in item["event"]:
                    if isinstance(sub, dict):
                        validated.append(sub)
                continue
            validated.append(item)
        return validated
    except (json.JSONDecodeError, Exception) as e:
        logger.error("LLM structuring failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

_WINDOW_SIZE = 20


_SEEDS_DIR = _PROJECT_ROOT / "seeds"


async def _load_and_insert_seeds(era: str) -> int:
    """Load seed events from seeds/{era}.json and insert into DB.

    Seed events are backbone events that Wikidata may not return.
    Skips events whose QID already exists. Returns count inserted.
    """
    seed_file = _SEEDS_DIR / f"{era}.json"
    if not seed_file.exists():
        logger.info("No seed file found at %s", seed_file)
        return 0

    with open(seed_file) as f:
        seeds = json.load(f)

    inserted = 0
    for ev in seeds:
        qid = ev.get("wikidata_qid")
        if qid and await event_exists_by_qid(qid):
            logger.debug("Seed QID %s already exists, skipping", qid)
            continue

        try:
            await insert_historical_event(
                year=ev["year"],
                region=ev["region"],
                event=ev["event"],
                significance=ev["significance"],
                event_type=ev["type"],
                affects=ev.get("affects", []),
                canonical=True,
                wikidata_qid=qid,
            )
            inserted += 1
        except Exception as e:
            logger.error("Failed to insert seed event: %s — %s", ev.get("event", "?")[:80], e)

    logger.info("Inserted %d seed events from %s", inserted, seed_file.name)
    return inserted


async def build_era(era: str, year_start: int, year_end: int, region: str) -> dict:
    """Build events for one era. Returns coverage stats."""
    logger.info("=== Building era: %s (%d-%d, region: %s) ===", era, year_start, year_end, region)

    # Insert backbone seed events first
    seed_count = await _load_and_insert_seeds(era)
    if seed_count:
        logger.info("Seeded %d backbone events before Wikidata query", seed_count)

    all_raw_events: list[dict] = []

    for event_type, q_classes in EVENT_TYPE_CLASSES.items():
        win_start = year_start
        while win_start < year_end:
            win_end = min(win_start + _WINDOW_SIZE, year_end)

            cache_path = _cache_key(era, event_type, win_start, win_end)
            cached = _load_cache(cache_path)

            if cached is not None:
                logger.info("Using cached results for %s (%d-%d): %d events",
                            event_type, win_start, win_end, len(cached))
                for ev in cached:
                    all_raw_events.append(ev)
            else:
                query = _build_sparql_query(event_type, q_classes, win_start, win_end, region)
                logger.info("Querying Wikidata for %s events (%d-%d)...", event_type, win_start, win_end)

                results = await _query_sparql(query)
                logger.info("  Found %d raw results for %s (%d-%d)",
                            len(results), event_type, win_start, win_end)

                window_events = []
                for binding in results:
                    qid = _extract_qid(binding.get("event", {}).get("value", ""))
                    yr = _extract_year(binding)
                    if not qid or not yr:
                        continue
                    ev = {
                        "qid": qid,
                        "label": binding.get("eventLabel", {}).get("value", ""),
                        "description": binding.get("eventDescription", {}).get("value", ""),
                        "year": yr,
                        "location": binding.get("locationLabel", {}).get("value", ""),
                        "country": binding.get("countryLabel", {}).get("value", ""),
                        "source_type": event_type,
                    }
                    window_events.append(ev)
                    all_raw_events.append(ev)

                _save_cache(cache_path, window_events)
                await asyncio.sleep(2.0)

            win_start += _WINDOW_SIZE

    # Wikipedia year pages — non-war texture events
    logger.info("Fetching Wikipedia year pages for %d-%d...", year_start, year_end)
    wiki_year_events = await fetch_wikipedia_year_events(year_start, year_end, region)
    all_raw_events.extend(wiki_year_events)
    logger.info("Added %d events from Wikipedia year pages", len(wiki_year_events))

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

    # Fetch Wikipedia extracts for enrichment (Wikidata events only, not Wikipedia year page events)
    wikidata_events = [ev for ev in new_events if not ev["qid"].startswith("wiki_year_")]
    wiki_page_events = [ev for ev in new_events if ev["qid"].startswith("wiki_year_")]
    logger.info("Fetching Wikipedia summaries for %d Wikidata events (skipping %d Wikipedia year page events)...",
                len(wikidata_events), len(wiki_page_events))
    for ev in wikidata_events:
        wiki_title = await _get_wikipedia_title_for_qid(ev["qid"])
        if wiki_title:
            extract = await _fetch_wikipedia_summary(wiki_title)
            ev["wiki_extract"] = extract or ""
        else:
            ev["wiki_extract"] = ""
        await asyncio.sleep(0.1)

    # Pre-filter Wikipedia year page events by text relevance (before LLM)
    _RELEVANT_KEYWORDS = {
        "byzantine", "ottoman", "constantinople", "anatolia",
        "balkans", "balkan", "mediterranean", "serbia", "serbian",
        "bulgaria", "bulgarian", "hungary", "hungarian", "venice",
        "venetian", "genoa", "genoese", "wallachia", "wallachian",
        "moldavia", "moldavian", "albania", "albanian", "epirus",
        "morea", "peloponnese", "thessalonica", "thessaloniki",
        "adrianople", "gallipoli", "bosphorus", "dardanelles",
        "black sea", "aegean", "levant", "crusade", "varna",
        "kosovo", "nicopolis", "achaea", "athens", "murad",
        "mehmed", "bayezid", "sultan", "palaiologos", "palaeologus",
        "hunyadi", "skanderbeg", "despot", "patriarch",
    }
    pre_filtered = []
    for ev in new_events:
        if ev["qid"].startswith("wiki_year_"):
            raw_text = (ev.get("wiki_extract") or ev.get("description") or "").lower()
            if any(kw in raw_text for kw in _RELEVANT_KEYWORDS):
                pre_filtered.append(ev)
            else:
                logger.debug("Pre-filter: skipping '%s'", ev.get("label", "?")[:60])
        else:
            pre_filtered.append(ev)
    logger.info("Pre-filtered Wikipedia events: %d kept out of %d (removed %d irrelevant)",
                len([e for e in pre_filtered if e["qid"].startswith("wiki_year_")]),
                len([e for e in new_events if e["qid"].startswith("wiki_year_")]),
                len(new_events) - len(pre_filtered))
    new_events = pre_filtered

    # Process in batches of 10 through LLM
    inserted = 0
    batch_size = 10
    for i in range(0, len(new_events), batch_size):
        batch = new_events[i:i + batch_size]
        logger.info("Structuring batch %d-%d (%d events)...",
                     i + 1, min(i + batch_size, len(new_events)), len(batch))

        structured = await _structure_events_with_llm(batch, era_region=region, year_start=year_start, year_end=year_end)

        raw_by_qid = {ev["qid"]: ev for ev in batch}
        for item in structured:
            try:
                valid_types = {"war", "epidemic", "famine", "political",
                               "religious", "economic", "natural_disaster", "cultural"}
                valid_sig = {"local", "regional", "civilizational"}
                ev_type = item.get("type", "")
                if ev_type not in valid_types:
                    logger.debug("Skipping event with invalid type '%s': %s",
                                 ev_type, item.get("event", "?")[:60])
                    continue
                sig = item.get("significance", "regional")
                if sig not in valid_sig:
                    sig = "regional"

                item_region = (item.get("region") or "").lower()
                event_text_lower = (item.get("event") or "").lower()

                relevant_region_keywords = {
                    "byzantine", "ottoman", "constantinople", "anatolia",
                    "balkans", "balkan", "mediterranean", "serbia", "serbian",
                    "bulgaria", "bulgarian", "hungary", "hungarian", "venice",
                    "venetian", "genoa", "genoese", "wallachia", "wallachian",
                    "moldavia", "moldavian", "albania", "albanian", "epirus",
                    "morea", "peloponnese", "thessalonica", "thessaloniki",
                    "adrianople", "gallipoli", "bosphorus", "dardanelles",
                    "black sea", "aegean", "levant", "crusade", "varna",
                    "kosovo", "nicopolis", "achaea", "athens",
                }
                text_relevant = any(kw in event_text_lower for kw in relevant_region_keywords)

                if not text_relevant:
                    logger.debug("Skipping non-relevant event: %s (region: %s)",
                                 item.get("event", "?")[:60], item_region)
                    continue

                affects = item.get("affects", [])
                if not isinstance(affects, list):
                    affects = []

                qid = item.get("wikidata_qid", "")
                event_text = item.get("event", "")

                if not event_text or event_text == "Unknown event" or len(event_text) < 10:
                    raw = raw_by_qid.get(qid, {})
                    label = raw.get("label", "")
                    desc = raw.get("description", "")
                    wiki = raw.get("wiki_extract", "")
                    event_text = wiki[:300] if wiki else f"{label}. {desc}".strip(". ")
                    if not event_text or len(event_text) < 5:
                        logger.debug("Skipping event with no usable description: %s", qid)
                        continue

                if not isinstance(event_text, str):
                    event_text = str(event_text)[:300]

                year_val = item.get("year")
                if year_val is None:
                    raw = raw_by_qid.get(qid, {})
                    year_val = raw.get("year", year_start)

                await insert_historical_event(
                    year=int(year_val),
                    region=item.get("region", region),
                    event=event_text,
                    significance=sig,
                    event_type=ev_type,
                    affects=affects,
                    canonical=True,
                    wikidata_qid=qid,
                )
                inserted += 1
            except Exception as e:
                logger.error("Failed to insert event: %s — %s",
                             str(item)[:200], e)

    # Coverage report (query without region filter to count all inserted events)
    events = await query_historical_events(year_start, year_end)
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

    country_qids = REGION_COUNTRY_QIDS.get(region, [])
    if country_qids:
        print(f"Country filter: {len(country_qids)} Wikidata entities ({', '.join(country_qids[:5])}{'...' if len(country_qids) > 5 else ''})")
    else:
        print("WARNING: No country filter for this region — results will be global")

    seed_file = _SEEDS_DIR / f"{era}.json"
    if seed_file.exists():
        with open(seed_file) as f:
            seeds = json.load(f)
        print(f"Seed file: {seed_file.name} ({len(seeds)} backbone events)")
        for s in seeds[:5]:
            print(f"  - [{s['year']}] {s['event'][:80]}")
        if len(seeds) > 5:
            print(f"  ... and {len(seeds) - 5} more")
    else:
        print(f"No seed file at seeds/{era}.json")
    print()

    total_results = 0
    decade_counts: dict[int, int] = {}
    type_counts: dict[str, int] = {}

    for event_type, q_classes in EVENT_TYPE_CLASSES.items():
        query = _build_sparql_query(event_type, q_classes, year_start, year_end, region)
        print(f"--- {event_type} ({len(q_classes)} classes) ---")

        await asyncio.sleep(2.0)  # rate limit between queries
        try:
            results = await _query_sparql(query)
            print(f"Results: {len(results)} events found")
            for r in results[:5]:
                label = r.get("eventLabel", {}).get("value", "?")
                year = _extract_year(r)
                loc = r.get("locationLabel", {}).get("value", "?")
                country = r.get("countryLabel", {}).get("value", "?")
                print(f"  - [{year}] {label} (location: {loc}, country: {country})")
            if len(results) > 5:
                print(f"  ... and {len(results) - 5} more")
            total_results += len(results)
            type_counts[event_type] = len(results)
            for r in results:
                y = _extract_year(r)
                if y:
                    decade = (y // 10) * 10
                    decade_counts[decade] = decade_counts.get(decade, 0) + 1
        except Exception as e:
            print(f"  SPARQL query failed: {e}")
            type_counts[event_type] = 0
        print()

    # Wikipedia year pages
    print("--- Wikipedia year pages ---")
    wiki_total = 0
    for year in range(year_start, year_end + 1):
        events = await _fetch_wikipedia_year_page(year)
        wiki_total += len(events)
        for ev_text in events:
            decade = (year // 10) * 10
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
        await asyncio.sleep(1.0)
    print(f"Results: {wiki_total} raw event lines from {year_end - year_start + 1} year pages")
    total_results += wiki_total
    type_counts["wikipedia_year_pages"] = wiki_total
    print()

    # Seed events
    if seed_file.exists():
        with open(seed_file) as f:
            seeds = json.load(f)
        for s in seeds:
            decade = (s["year"] // 10) * 10
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
            total_results += 1

    print("=== COVERAGE REPORT ===")
    print(f"Total events (Wikidata + Wikipedia + seeds): {total_results}")
    print(f"Events by type: {type_counts}")
    print(f"Events per decade:")
    for decade in sorted(decade_counts.keys()):
        count = decade_counts[decade]
        flag = " *** SPARSE" if count < 3 else ""
        print(f"  {decade}s: {count}{flag}")
    sparse = [d for d, c in sorted(decade_counts.items()) if c < 3]
    if sparse:
        print(f"\nSPARSE DECADES (<3 events): {sparse}")
    else:
        print("\nNo sparse decades — all decades have 3+ events.")
    print("\n(Dry run — nothing written to DB. Remove --dry-run to execute.)")


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
