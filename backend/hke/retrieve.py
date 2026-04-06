"""Context retriever — fetches relevant historical chunks for prompts.

Wraps Chroma queries and formats results for injection into LLM prompts.
For Gutenberg texts, child chunks are retrieved first and parent context
is assembled for richer LLM input. For Wikipedia, section chunks preserve
structured information.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from backend.hke.store import query_collection, query_collection_with_metadata

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

    For hierarchical Gutenberg chunks, child matches trigger parent
    context retrieval, giving the LLM the broader narrative passage.
    """
    era_key = era_name_to_key(era_name)
    if not era_key:
        return ""

    chunks = query_collection(era_key, query, n_results=n_results)
    if not chunks:
        return ""

    seen = set()
    formatted = []
    for i, chunk in enumerate(chunks, 1):
        trimmed = chunk[:800].strip()
        if trimmed in seen:
            continue
        seen.add(trimmed)
        if len(chunk) > 800:
            trimmed += "..."
        formatted.append(f"[Source {i}]: {trimmed}")

    return "\n\n".join(formatted)


def retrieve_context_with_sources(
    era_name: str,
    query: str,
    n_results: int = 5,
) -> List[Dict]:
    """Retrieve context with metadata for attribution.

    Returns list of dicts: {"text": ..., "source": ..., "section": ...}
    """
    era_key = era_name_to_key(era_name)
    if not era_key:
        return []

    results = query_collection_with_metadata(era_key, query, n_results=n_results)
    output = []
    for r in results:
        meta = r.get("metadata", {})
        output.append({
            "text": r.get("text", ""),
            "source": meta.get("source", "unknown"),
            "title": meta.get("title", ""),
            "section": meta.get("section", ""),
            "chunk_type": meta.get("chunk_type", ""),
        })
    return output
