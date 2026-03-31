"""Context retriever — fetches relevant historical chunks for prompts.

Wraps Chroma queries and formats results for injection into LLM prompts.
"""

from __future__ import annotations

from typing import Optional

from backend.hke.store import query_collection

# Maps era names to era keys used in Chroma collections
_ERA_NAME_TO_KEY = {
    "Roman Late Empire": "roman_late_empire",
    "Viking Age": "viking_age",
    "Crusader States": "crusader_states",
    "Black Death": "black_death",
    "Fall of Constantinople": "fall_of_constantinople",
}


def era_name_to_key(name: str) -> Optional[str]:
    return _ERA_NAME_TO_KEY.get(name)


def retrieve_context(
    era_name: str,
    query: str,
    n_results: int = 3,
) -> str:
    """Retrieve historical context for an era and query.

    Returns a formatted string ready for prompt injection,
    or an empty string if no corpus is available.
    """
    era_key = era_name_to_key(era_name)
    if not era_key:
        return ""

    chunks = query_collection(era_key, query, n_results=n_results)
    if not chunks:
        return ""

    formatted = []
    for i, chunk in enumerate(chunks, 1):
        trimmed = chunk[:600].strip()
        if len(chunk) > 600:
            trimmed += "..."
        formatted.append(f"[Source {i}]: {trimmed}")

    return "\n\n".join(formatted)
