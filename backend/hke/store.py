"""Chroma vector DB storage for the Historical Knowledge Engine.

Uses the default Chroma embedding function (all-MiniLM-L6-v2) for Phase 1.
When nomic-embed-text via Ollama is confirmed working with Chroma's
OllamaEmbeddingFunction, swap in — but default works out of the box.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

import chromadb

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"

_client: Optional[chromadb.ClientAPI] = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        DB_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(DB_PATH))
    return _client


def get_or_create_collection(era_key: str) -> chromadb.Collection:
    client = _get_client()
    return client.get_or_create_collection(
        name=f"era_{era_key}",
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    collection: chromadb.Collection,
    texts: List[str],
    metadatas: List[dict],
) -> None:
    """Add text chunks to a Chroma collection in batches."""
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        ids = [uuid.uuid4().hex[:16] for _ in batch_texts]
        collection.add(
            documents=batch_texts,
            metadatas=batch_meta,
            ids=ids,
        )


def query_collection(
    era_key: str,
    query_text: str,
    n_results: int = 5,
) -> List[str]:
    """Retrieve the top-k most relevant chunks for a query."""
    try:
        client = _get_client()
        collection = client.get_collection(f"era_{era_key}")
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        docs = results.get("documents", [[]])[0]
        return docs
    except Exception:
        return []
