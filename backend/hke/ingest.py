"""Corpus ingestion pipeline — downloads, chunks, and embeds historical texts.

Usage:
    python -m backend.hke.ingest --era roman_late_empire
    python -m backend.hke.ingest --all

Model tier: nomic-embed-text (local, free) for embeddings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import httpx

from backend.hke.sources import ERA_SOURCES
from backend.hke.store import get_or_create_collection, add_chunks

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
GUTENBERG_MIRROR = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
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


def fetch_gutenberg(text_id: int) -> str:
    """Download a Gutenberg text by ID."""
    url = GUTENBERG_MIRROR.format(id=text_id)
    resp = httpx.get(url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def fetch_wikipedia(title: str) -> str:
    """Fetch a Wikipedia article summary."""
    url = WIKIPEDIA_API.format(title=title.replace(" ", "_"))
    resp = httpx.get(url, follow_redirects=True, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    extract = data.get("extract", "")
    return f"{title}\n\n{extract}"


def ingest_era(era_key: str) -> dict:
    """Download, chunk, and store all sources for one era. Returns stats."""
    if era_key not in ERA_SOURCES:
        raise ValueError(f"Unknown era: {era_key}. Available: {list(ERA_SOURCES.keys())}")

    sources = ERA_SOURCES[era_key]
    collection = get_or_create_collection(era_key)
    total_chunks = 0
    errors = []

    for entry in sources.get("gutenberg", []):
        try:
            print(f"  Fetching Gutenberg #{entry['id']}: {entry['title']}...")
            text = fetch_gutenberg(entry["id"])
            chunks = chunk_text(text)
            metadatas = [
                {"source": "gutenberg", "id": entry["id"], "title": entry["title"]}
                for _ in chunks
            ]
            add_chunks(collection, chunks, metadatas)
            total_chunks += len(chunks)
            print(f"    → {len(chunks)} chunks")
        except Exception as e:
            errors.append(f"Gutenberg #{entry['id']}: {e}")
            print(f"    ! Error: {e}")

    for title in sources.get("wikipedia", []):
        try:
            print(f"  Fetching Wikipedia: {title}...")
            text = fetch_wikipedia(title)
            chunks = chunk_text(text)
            metadatas = [
                {"source": "wikipedia", "title": title}
                for _ in chunks
            ]
            add_chunks(collection, chunks, metadatas)
            total_chunks += len(chunks)
            print(f"    → {len(chunks)} chunks")
        except Exception as e:
            errors.append(f"Wikipedia '{title}': {e}")
            print(f"    ! Error: {e}")

    return {"era": era_key, "chunks": total_chunks, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Ingest historical corpus for CHRONOS HKE")
    parser.add_argument("--era", type=str, help="Era key to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all eras")
    args = parser.parse_args()

    if args.all:
        for key in ERA_SOURCES:
            print(f"\n=== {key} ===")
            result = ingest_era(key)
            print(f"  Total: {result['chunks']} chunks, {len(result['errors'])} errors")
    elif args.era:
        print(f"\n=== {args.era} ===")
        result = ingest_era(args.era)
        print(f"  Total: {result['chunks']} chunks, {len(result['errors'])} errors")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
