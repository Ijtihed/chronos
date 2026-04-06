"""Corpus ingestion pipeline — downloads, chunks, and embeds historical texts.

Gutenberg texts use hierarchical chunking (parent/child) to handle
long discursive prose. Wikipedia articles use section-based chunking
to preserve structured information.

Usage:
    python -m backend.hke.ingest --era roman_late_empire
    python -m backend.hke.ingest --all
    python -m backend.hke.ingest --all --reindex   # delete + re-embed

Model tier: nomic-embed-text (local, free) for embeddings.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from backend.hke.sources import ERA_SOURCES
from backend.hke.store import get_or_create_collection, add_chunks, delete_collection

# Hierarchical chunking for Gutenberg (token ~ word for estimation)
PARENT_CHUNK_SIZE = 1200
PARENT_CHUNK_OVERLAP = 150
CHILD_CHUNK_SIZE = 300
CHILD_CHUNK_OVERLAP = 50

# Section-based chunking cap for Wikipedia
WIKI_SECTION_MAX_TOKENS = 1000

GUTENBERG_MIRROR = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_HTML_API = "https://en.wikipedia.org/api/rest_v1/page/html/{title}"


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks by word count."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def hierarchical_chunk_gutenberg(
    text: str,
) -> List[Tuple[str, str, List[Tuple[str, str]]]]:
    """Hierarchical chunking for Gutenberg prose.

    Returns a list of (parent_id, parent_text, [(child_id, child_text), ...]).
    Parent chunks: 1200 tokens, 150 overlap.
    Child chunks: 300 tokens, 50 overlap — nested within each parent.
    """
    parent_chunks = chunk_text(text, PARENT_CHUNK_SIZE, PARENT_CHUNK_OVERLAP)
    result = []
    for parent_text in parent_chunks:
        parent_id = uuid.uuid4().hex[:16]
        child_chunks = chunk_text(parent_text, CHILD_CHUNK_SIZE, CHILD_CHUNK_OVERLAP)
        children = []
        for child_text in child_chunks:
            child_id = uuid.uuid4().hex[:16]
            children.append((child_id, child_text))
        result.append((parent_id, parent_text, children))
    return result


def section_chunk_wikipedia(html: str, title: str) -> List[Tuple[str, str, str]]:
    """Section-based chunking for Wikipedia HTML.

    Splits on H2/H3 headers. Each section is one chunk unless > 1000 tokens,
    in which case it's split with overlap.

    Returns a list of (chunk_id, section_title, text).
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["style", "script", "table", "sup", "span"]):
        if tag.name in ("style", "script", "sup"):
            tag.decompose()

    sections: List[Tuple[str, str]] = []
    current_title = title
    current_text_parts: List[str] = []

    for element in soup.find_all(["h2", "h3", "p", "ul", "ol"]):
        if element.name in ("h2", "h3"):
            if current_text_parts:
                sections.append((current_title, " ".join(current_text_parts)))
                current_text_parts = []
            heading_text = element.get_text(strip=True)
            heading_text = re.sub(r"\[edit\]$", "", heading_text).strip()
            current_title = heading_text or title
        else:
            text = element.get_text(separator=" ", strip=True)
            if text:
                current_text_parts.append(text)

    if current_text_parts:
        sections.append((current_title, " ".join(current_text_parts)))

    result = []
    for section_title, section_text in sections:
        words = section_text.split()
        if len(words) <= WIKI_SECTION_MAX_TOKENS:
            chunk_id = uuid.uuid4().hex[:16]
            result.append((chunk_id, section_title, section_text))
        else:
            sub_chunks = chunk_text(section_text, WIKI_SECTION_MAX_TOKENS, 50)
            for i, sub in enumerate(sub_chunks):
                chunk_id = uuid.uuid4().hex[:16]
                sub_title = f"{section_title} (part {i + 1})" if len(sub_chunks) > 1 else section_title
                result.append((chunk_id, sub_title, sub))

    return result


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_gutenberg(text_id: int) -> str:
    """Download a Gutenberg text by ID."""
    url = GUTENBERG_MIRROR.format(id=text_id)
    resp = httpx.get(url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def fetch_wikipedia_summary(title: str) -> str:
    """Fetch a Wikipedia article summary (short extract)."""
    url = WIKIPEDIA_SUMMARY_API.format(title=title.replace(" ", "_"))
    resp = httpx.get(url, follow_redirects=True, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    return data.get("extract", "")


def fetch_wikipedia_html(title: str) -> str:
    """Fetch full Wikipedia article as HTML for section-based chunking."""
    url = WIKIPEDIA_HTML_API.format(title=title.replace(" ", "_"))
    resp = httpx.get(url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

def ingest_era(era_key: str, reindex: bool = False) -> dict:
    """Download, chunk, and store all sources for one era. Returns stats."""
    if era_key not in ERA_SOURCES:
        raise ValueError(f"Unknown era: {era_key}. Available: {list(ERA_SOURCES.keys())}")

    if reindex:
        print(f"  Reindexing: deleting collection for {era_key}...")
        delete_collection(era_key)

    sources = ERA_SOURCES[era_key]
    collection = get_or_create_collection(era_key)
    total_chunks = 0
    errors = []

    # --- Gutenberg: hierarchical chunking ---
    for entry in sources.get("gutenberg", []):
        try:
            print(f"  Fetching Gutenberg #{entry['id']}: {entry['title']}...")
            text = fetch_gutenberg(entry["id"])
            hierarchy = hierarchical_chunk_gutenberg(text)

            for parent_id, parent_text, children in hierarchy:
                parent_meta = {
                    "source": "gutenberg",
                    "gutenberg_id": str(entry["id"]),
                    "title": entry["title"],
                    "chunk_type": "parent",
                    "parent_id": parent_id,
                }
                add_chunks(collection, [parent_text], [parent_meta], ids=[parent_id])

                child_texts = [c[1] for c in children]
                child_metas = [
                    {
                        "source": "gutenberg",
                        "gutenberg_id": str(entry["id"]),
                        "title": entry["title"],
                        "chunk_type": "child",
                        "parent_id": parent_id,
                    }
                    for _ in children
                ]
                child_ids = [c[0] for c in children]
                add_chunks(collection, child_texts, child_metas, ids=child_ids)
                total_chunks += 1 + len(children)

            print(f"    → {total_chunks} chunks (hierarchical)")
        except Exception as e:
            errors.append(f"Gutenberg #{entry['id']}: {e}")
            print(f"    ! Error: {e}")

    # --- Wikipedia: section-based chunking ---
    for title in sources.get("wikipedia", []):
        try:
            print(f"  Fetching Wikipedia: {title}...")
            try:
                html = fetch_wikipedia_html(title)
                sections = section_chunk_wikipedia(html, title)
            except Exception:
                summary = fetch_wikipedia_summary(title)
                sections = [(uuid.uuid4().hex[:16], title, f"{title}\n\n{summary}")]

            texts = [s[2] for s in sections]
            metas = [
                {
                    "source": "wikipedia",
                    "title": title,
                    "section": s[1],
                    "chunk_type": "section",
                }
                for s in sections
            ]
            ids = [s[0] for s in sections]
            add_chunks(collection, texts, metas, ids=ids)
            total_chunks += len(sections)
            print(f"    → {len(sections)} section chunks")
        except Exception as e:
            errors.append(f"Wikipedia '{title}': {e}")
            print(f"    ! Error: {e}")

    return {"era": era_key, "chunks": total_chunks, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Ingest historical corpus for CHRONOS HKE")
    parser.add_argument("--era", type=str, help="Era key to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all eras")
    parser.add_argument("--reindex", action="store_true",
                        help="Delete existing collection before re-ingesting")
    args = parser.parse_args()

    if args.all:
        for key in ERA_SOURCES:
            print(f"\n=== {key} ===")
            result = ingest_era(key, reindex=args.reindex)
            print(f"  Total: {result['chunks']} chunks, {len(result['errors'])} errors")
    elif args.era:
        print(f"\n=== {args.era} ===")
        result = ingest_era(args.era, reindex=args.reindex)
        print(f"  Total: {result['chunks']} chunks, {len(result['errors'])} errors")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
